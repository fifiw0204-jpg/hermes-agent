# Durable & Background Systems

Four systems run alongside the main conversation loop. Quick reference
here; full developer notes live in `AGENTS.md`, user-facing docs under
`website/docs/user-guide/features/`.

### Delegation (`delegate_task`)

Spawn a subagent with an isolated context + terminal session.

- **Single:** `delegate_task(goal, context)`.
- **Batch:** `delegate_task(tasks=[{goal, ...}, ...])` runs children in
  parallel, capped by `delegation.max_concurrent_children` (default 3).
- **Background:** `delegate_task(background=true)` returns a handle
  immediately and keeps the parent loop going; the child's result
  re-enters the conversation as a new turn when it finishes.
- **Roles:** `leaf` (default; cannot re-delegate) vs `orchestrator`
  (can spawn its own workers, bounded by `delegation.max_spawn_depth`).
- **Not durable.** A backgrounded child is still process-local — if the
  parent process exits, the child is lost. For work that must outlive
  the process, use `cronjob` or
  `terminal(background=True, notify_on_complete=True)`.

- **The delegation default route decides where an unnamed child runs.**
  Under the `profile_routes` backend, `delegation.backends.profile_routes.default`
  picks the profile for any `delegate_task` entry that names none. Pointing it
  at a foreman/orchestrator profile makes every child re-route its work onto
  the kanban board instead of executing it — the dispatch reports success and
  no work lands. Check it with `hermes config get delegation.backends.profile_routes.default`
  and unset it with `hermes config unset delegation.backends.profile_routes.default`
  when the default is a routing profile. Change config through the
  `hermes config set|unset` CLI: the config file is guarded against direct
  file writes.

Config: `delegation.*` in `config.yaml`.

### Cron (scheduled jobs)

Durable scheduler — `cron/jobs.py` + `cron/scheduler.py`. Drive it via
the `cronjob` tool, the `hermes cron` CLI (`list`, `add`, `edit`,
`pause`, `resume`, `run`, `remove`), or the `/cron` slash command.

- **Schedules:** duration (`"30m"`, `"2h"`), "every" phrase
  (`"every monday 9am"`), 5-field cron (`"0 9 * * *"`), or ISO timestamp.
- **Per-job knobs:** `skills`, `model`/`provider` override, `script`
  (pre-run data collection; `no_agent=True` makes the script the whole
  job), `context_from` (chain job A's output into job B), `workdir`
  (run in a specific dir with its `AGENTS.md` / `CLAUDE.md` loaded),
  multi-platform delivery.
- **Invariants:** 3-minute hard interrupt per run, `.tick.lock` file
  prevents duplicate ticks across processes, cron sessions pass
  `skip_memory=True` by default, and cron deliveries are framed with a
  header/footer instead of being mirrored into the target gateway
  session (keeps role alternation intact).

User docs: https://hermes-agent.nousresearch.com/docs/user-guide/features/cron

### Curator (skill lifecycle)

Background maintenance for agent-created skills. Tracks usage, marks
idle skills stale, archives stale ones, keeps a pre-run tar.gz backup
so nothing is lost.

- **CLI:** `hermes curator <verb>` — `status`, `usage`, `run`, `pause`,
  `resume`, `pin`, `unpin`, `archive`, `restore`, `list-archived`, `prune`,
  `backup`, `rollback`.
- **Slash:** `/curator <subcommand>` mirrors the CLI.
- **Scope:** only touches skills with `created_by: "agent"` provenance.
  Bundled + hub-installed skills are off-limits. **Never deletes** —
  max destructive action is archive. Pinned skills are exempt from
  every auto-transition and every LLM review pass.
- **Cost:** the deterministic inactivity/prune sweep runs for free. The
  aux-model "consolidate overlapping skills into umbrellas" pass is
  **off by default** — opt in with `curator.consolidate: true` or
  `hermes curator run --consolidate`. Routine background curation costs
  zero tokens.
- **Telemetry:** sidecar at `~/.hermes/skills/.usage.json` holds
  per-skill `use_count`, `view_count`, `patch_count`,
  `last_activity_at`, `state`, `pinned`.

Config: `curator.*` (`enabled`, `interval_hours`, `min_idle_hours`,
`stale_after_days`, `archive_after_days`, `backup.*`).
User docs: https://hermes-agent.nousresearch.com/docs/user-guide/features/curator

### Kanban (multi-agent work queue)

Durable SQLite board for multi-profile / multi-worker collaboration.
Users drive it via `hermes kanban <verb>`; dispatcher-spawned workers
see a focused `kanban_*` toolset gated by `HERMES_KANBAN_TASK`, and
orchestrator profiles can opt into the broader `kanban` toolset. Normal
sessions still have zero `kanban_*` schema footprint unless configured.

- **CLI verbs (common):** `init`, `create`, `list` (alias `ls`),
  `show`, `assign`, `link`, `unlink`, `comment`, `complete`, `block`,
  `unblock`, `archive`, `tail`. Less common: `watch`, `stats`, `runs`,
  `log`, `dispatch`, `daemon`, `gc`.
- **Worker/orchestrator toolset:** `kanban_show`, `kanban_complete`,
  `kanban_block`, `kanban_heartbeat`, `kanban_comment`, `kanban_create`,
  `kanban_link`; profiles that explicitly enable the `kanban` toolset
  outside a dispatcher-spawned task also get `kanban_list` and
  `kanban_unblock` for board routing.
- **Dispatcher** runs inside the gateway by default
  (`kanban.dispatch_in_gateway: true`) — reclaims stale claims,
  promotes ready tasks, atomically claims, spawns assigned profiles.
  Auto-blocks a task after `failure_limit` consecutive spawn failures
  (default 2; configurable via `kanban.failure_limit` or per-task
  `max_retries`).
- **Isolation:** board is the hard boundary (workers get
  `HERMES_KANBAN_BOARD` pinned in env); tenant is a soft namespace
  within a board for workspace-path + memory-key isolation.

#### Standing up an orchestrator ("PM bot") profile

To make one profile hand work to other profiles, use the board rather than
writing a router. The pieces, in the order they bite:

1. **The `kanban` toolset is default-OFF on the CLI.** It lives in
   `_DEFAULT_OFF_TOOLSETS`, so a plain profile sees zero `kanban_*` tools
   and cannot create a card. Enable it for that profile only:
   `hermes -p <profile> tools enable kanban --platform cli`. The gate is
   checked per-profile against `platform_toolsets` / `toolsets`, so one
   profile can be the orchestrator while the others stay worker-only.
2. **An assignee must already exist as a profile.** The dispatcher spawns
   `hermes -p <assignee>`; if that profile does not exist the card is
   marked `skipped_nonspawnable` and no worker ever runs it. Build the
   orchestrator first and point its first card at an already-existing
   profile — a card assigned to a not-yet-created worker is a silent
   no-op, not an error. The same trap catches a worker profile that was
   retired: once its directory is gone, every card still naming it as
   assignee is silently skipped, and the board shows a card that looks
   ready forever. So retire a worker in this order — rewrite the routing
   table so it no longer names the profile, re-point the cards that did
   name it, and only then remove the profile directory.
3. **Routing keys are the profile name plus its description.** The
   built-in decomposer splits a goal into child cards by matching each
   profile's description, so the description *is* the routing table:
   `hermes profile describe <profile> --text "<what this bot owns>"`.
   Write it in the bot's domain terms, not generic adjectives. When the
   worker set is generated or replaced wholesale, keep one authoritative
   routing table and derive the worker list from it — a second, hand-maintained
   list of workers drifts, and the orchestrator then dispatches to a worker
   that no longer exists.
4. **Card-level skills must be installed on the assignee, not on the
   orchestrator.** `kanban_create(skills=[...])` passes `--skills` to the
   spawned worker, which resolves them in that profile's own skill tree
   (its own `skills/` plus its own `skills.external_dirs`). A skill the
   orchestrator can see but the worker cannot is a card that runs and
   then cannot do the work.
5. **Skill names resolve from frontmatter `name:`**, not the directory
   name, whenever the tree is loaded through `external_dirs`. A routing
   table listing directory names dispatches to nothing.
6. The dispatcher runs in the gateway, so `kanban.dispatch_in_gateway`
   must be on and the gateway restarted after changing kanban config —
   a long-running gateway caches the loaded config.
7. **Reclaiming a running card does not stop it.** `hermes kanban reclaim <id>`
   releases the claim, and the dispatcher may spawn a fresh worker for the
   still-runnable card within seconds — a new `kanban_worker_client` pid that
   must also be killed. To stop a card for good: kill the pid in the card's
   `task_runs` row, reclaim it, then `hermes kanban block <id>`, then confirm
   `ps -eo pid,cmd | grep kanban_worker_client` is empty and the card row
   reads `blocked`. Kill the worker before reclaiming, or the respawn lands
   after your check.
8. **Give the orchestrator exactly one way to execute work.** An
   orchestrator holding both the `kanban` and the `delegation` toolset can
   open a card *and* delegate the same request, while the dispatcher
   independently claims that card and spawns a worker for it: two runs of
   one computation, two writes to one output path, and the second write
   wins. Remove the tool rather than instructing against it —
   `hermes -p <orchestrator> tools disable delegation --platform cli`. An
   absent tool is a stronger guarantee than a rule the orchestrator's own
   skill states, because the rule only binds a session that loaded it.
9. **The orchestrator's job ends at `kanban_create`.** Once a card has an
   assignee, the dispatcher claims it and spawns the worker; what remains
   for the orchestrator is to read the artifact back and verify it. A card
   the orchestrator also executes inline is the same second execution
   path in a different costume — and a read-only card with no assignee is
   the opposite failure, since nobody runs it at all.
10. **Keep the deliverable directory to deliverables only.** Workers write
   intermediates next to the artifact they produce. A results directory
   that also holds `_tmp_*` scratch dumps has no clean file set, and the
   next consumer cannot tell which file is the deliverable. Send
   intermediates to a scratch path, and move any that land in the
   deliverable directory out during acceptance.
11. **Give every profile a launcher name, or "the bot is broken" is the
    only symptom the user can report.** A profile created with
    `--no-alias` (or otherwise without one) has no wrapper script, so
    typing the profile's bare name does nothing while `hermes -p <name>`
    still works — which reads as a dead bot, not a missing launcher. Fix
    it per profile: `hermes profile alias <name>`, which writes
    `~/.local/bin/<name>` containing `exec hermes -p <name> "$@"`.
    Do it for the orchestrator AND every worker, then confirm with a real
    invocation (`<name> chat -q "ping"`). Beware the name collision:
    `hermes <name>` dispatches a *subcommand*, so a profile named after a
    built-in (e.g. `hermes pm`, the package manager) runs that subcommand
    instead of the profile — the profile is reached as `hermes -p <name>`
    or as the bare `<name>` wrapper, never as `hermes <name>`.

Drive the orchestrator as a background process:
`hermes -p <orchestrator> chat -q "<request>"` opens a card and then waits
for the worker, so it routinely outlasts a foreground tool timeout. Launch
it in the background and poll the board — the board is the durable record
of what happened, the orchestrator's stdout is not.

#### Card bodies and dispatch evidence

- **Put a long card body in a file.** A body carrying commands, paths and
  quotes gets mangled when it is passed as an inline shell argument: the
  newlines break the string and the quotes inside it get eaten, so the
  worker receives a body that no longer contains the command it was supposed
  to run. Write the body to a file, confirm the path exists before creating
  the card, and pass that path (`--body-file` on the CLI).
- **Creating a card is not dispatching it.** A create call that returns a card
  id proves the card exists; nothing proves a worker picked it up. The board
  is the evidence — the run's events must show the claim, the spawn and the
  worker bound to the assignee profile, and the dispatch output must name the
  card, the assignee and the workspace. Report the card id together with
  that evidence.
- **A run that has started writes its results late.** A worker that is still
  executing produces an empty or partial output area, which is indistinguishable
  from a failed run if you only look at the files. Judge an in-flight run by
  the process, the board state and the elapsed time against its declared
  timeout, not by the absence of a result file.
- **Do not point a card's workspace at the directory the work produces.** The
  worker's cwd then lands inside its own output tree, so a worker that edits
  or tidies files can damage the inputs and the artifacts of its siblings.
  Give the card a scratch or repo path and let the worker write to absolute
  paths outside it.

A completion notification for a background job is not automatically a new
event. Before re-reporting its output, check whether that run was already
covered in an earlier report; if it was, the useful answer is a one-line
"already reported, state unchanged" plus whatever genuinely changed
(board state, git state) — re-quoting the same numbers reads as if
something new happened. Re-verify the cheap invariants (no leftover
processes, board counters, working tree clean) and report the delta.

Verify each hop with the agent's own surfaces: `hermes -p <profile>
config get platform_toolsets`, `hermes profile list`, `hermes kanban list`,
`hermes kanban log <id>`.

User docs: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban
