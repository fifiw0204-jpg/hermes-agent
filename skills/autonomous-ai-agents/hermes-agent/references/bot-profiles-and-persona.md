# Dedicated Bot Profiles (persona + scoped capabilities)

A "bot with its own soul and its own skills" is not a new primitive: it is a
**Hermes profile**. A profile is a separate Hermes home (`$HERMES_HOME`), so
identity, skills, memory, sessions, cron jobs and credentials are all
per-bot by construction. Bot Mode in the desktop app is only a roster UI over
this primitive — everything visible there is visible from the CLI.

## The four layers of a dedicated bot

| Layer | File inside the profile | Controls |
|---|---|---|
| Identity / tone | `SOUL.md` | system-prompt slot #1 — the agent's persona and voice |
| Capabilities | `skills/<name>/SKILL.md` | the only skills that auto-load for this bot |
| Capability boundary | `config.yaml` | model, provider, toolsets, `agent.personalities` |
| Credentials | `.env` | API keys + messaging bot tokens |

`SOUL.md` is loaded **only** from `$HERMES_HOME` (never from cwd), is scanned
for prompt injection, and replaces the built-in identity outright — it is not
an additive layer. Project-level rules belong in `AGENTS.md`, not `SOUL.md`.

## Procedure

1. **Create the profile.**
   ```bash
   hermes profile create <name> --description "what this bot is good at"
   ```
   The `--description` is what the kanban orchestrator routes on, so write it
   as role, not name. A command alias `<name>` is created automatically;
   `hermes -p <name> <command>` works for every command.
   Flags that matter: `--clone` (copies config/.env/SOUL.md/skills from the
   active profile, **not** messaging tokens), `--clone-all` (also memories,
   plugins, cron), `--no-skills` (empty skill set, opts out of bundled-seed
   sync).

2. **Write the persona** at `~/.hermes/profiles/<name>/SOUL.md`. Keep it to
   identity/voice/style/uncertainty handling — no file paths, no temporary
   workflow detail. A later `/personality <preset>` is a *session overlay*;
   `SOUL.md` remains the durable default.

3. **Scope the capabilities.** Options, in order of preference:
   - copy/install the skill into `~/.hermes/profiles/<name>/skills/`
   - point that profile's `config.yaml` at a shared tree:
     ```yaml
     skills:
       external_dirs:
         - ~/some/repo/skills
     ```
     `external_dirs` is read-only and lowest precedence (project > local >
     create_dir > external_dirs), so a local copy shadows an external one of
     the same name. Two external dirs exposing the same `name:` are refused
     outright ("Ambiguous skill name"), not resolved.
   - a skill that lives only in another profile's `skills/` is invisible here —
     profile isolation means no implicit sharing.

   There is **no allow-list key** for a profile's skill scope. Three
   mechanisms decide it, and they are not interchangeable:
   - the contents of `$HERMES_HOME/skills/` (directories or symlinks) — the
     only mechanism that can *narrow* scope;
   - `skills.external_dirs` — read-only, lowest precedence, adds scope;
   - `skills.disabled` — a **deny-list**, not an allow-list, so it can only
     subtract from what is already visible.

   To narrow an existing profile, run the opt-out **against that profile**:
   ```bash
   hermes -p <name> skills opt-out --remove --yes
   ```
   It drops the pristine (unmodified) bundled skills from that profile's
   `skills/` tree and writes a `.no-bundled-skills` marker into that
   profile's home so a later `hermes update` does not re-seed them. Link in
   the intended skills afterwards; `hermes-agent` itself is essential and
   cannot be disabled.

   Three things this leaves behind, each of which makes the profile *look*
   narrowed when it is not: the marker and the removal act on the ACTIVE
   Hermes home, so the bare `hermes skills opt-out --remove` (no `-p`)
   strips the default profile instead of the one you meant; skills edited by
   hand are kept as user-modified and stay visible; and every bundled
   category directory keeps its `DESCRIPTION.md` after its skills are
   deleted, so the tree still reads like the full library — delete the
   category directories that hold nothing else.

   Verify a narrowed profile on four surfaces: `hermes -p <name> skills
   list` (count against the source profile — a count that matches the source
   means the scope leaked), every symlink under the profile's `skills/`
   resolving to an existing target, the profile's own prompt snapshot
   carrying the new skill count, and a live one-shot
   (`hermes -p <name> -z "<trivial prompt>"`) proving the profile still loads
   its model, skills and identity. Grep the profile's `SOUL.md` and
   `config.yaml` for the skills you removed — a persona that names a removed
   skill now points at nothing.

   **Three different layers mount skills, and they are easily confused.** The
   *bot's* `settings.json` (`skills: [...]`) mounts what that one execution
   instance loads; the *profile's* `skills/` tree scopes what the agent can
   see at all; a *card's* `skills:` field pins what the card's **assignee**
   loads — the foreman, not the worker. Pinning a worker's skill on the card
   fails at launch with a skill-unavailable error; putting the foreman's
   routing skill in the worker's `settings.json` gives the worker judgement
   it should not make. Mount the worker's skills in the worker's own
   settings, and pin only the foreman's own routing skill on the card.

4. **Give it its own credentials.** Each profile carries its own `.env`. Two
   profiles holding the same messaging bot token collide: the second gateway
   is refused with a message naming the conflicting profile (enforced for
   Telegram, Discord, Slack, WhatsApp, Signal). Messaging channels are never
   inherited by `--clone` unless `--clone-channels` is passed.

5. **Give it its own schedule.** Cron jobs are per-profile:
   `hermes -p <name> cron list`. In Bot Mode the same jobs appear as
   "routines" next to the bot's chat.

6. **Run it.** `hermes -p <name> chat` for the CLI, `<name> gateway start`
   for a messaging platform, or add the profile to the desktop Bot Mode
   roster for a named bot with an avatar and a persistent bot chat.

## Splitting one domain into several bots

A single skill is often the core of a *family* of capabilities (a solver core
plus its ingest stages, plus a report writer). Splitting that family across
profiles is a design decision, not a mechanical one.

**Split on these three axes only:**

| Axis | Example | Why it forces a split |
|---|---|---|
| Toolchain / dependencies | one stage needs numpy+scipy, another needs pdfplumber+xlsx | per-profile venv and `terminal.cwd` differ; a shared env cannot satisfy both |
| Trust boundary | one stage's numbers must come from a script, another's prose is model-written | merging them lets the model "explain" a number it was supposed to compute |
| Memory contamination | measurements vs. design decisions | one profile's memory silently rewrites the other's facts |

**Do not split per skill.** A profile costs its own config, memory, sessions,
credentials and cron. Splitting N skills into N profiles buys no capability
boundary; group skills that share an artifact contract (same JSON in/out) into
one bot. Three is usually the ceiling for one domain: intake, compute, report.

**Hand off across bots on disk, never through shared memory.** Profiles are
isolated by design and a shared memory provider is a deliberate exception —
prefer each stage writing a JSON artifact that the next stage reads. This is
usually the pipeline's existing artifact contract already.

**Recommend one bot plus subagents when the work is CLI-only.** Profiles earn
their cost when a bot needs its own identity, channel, schedule or dependency
set. If the only consumer is one CLI session, one profile plus `delegate_task`
gives the same context isolation for free.

## A fleet: one dispatcher bot plus N worker bots

When the goal is "one bot that dispatches to other bots", the primitives already
exist: a **profile** is a bot, and the **kanban board** is the durable work
queue with its own dispatcher. Do not write a new dispatcher daemon, a second
task database, or a routing engine — those duplicate machinery the board
already owns (assignee profiles, dependency links, claim/lease, retry with
circuit breaker, worker lifecycle injection, audit rows).

Procedure:

1. **Prove the skill tree is loaded before designing bots.** A bot whose
   profile has no skills looks exactly like a broken bot. Check the count
   that matters: `hermes skills list | grep -c external` for an exposed
   external tree, and `hermes -p <worker> skills list` for the worker's
   scope.
2. **Group skills into families** along the axes above (artifact contract /
   dependency set / trust boundary), not one bot per skill. A skill library
   that ships its own registry file (ID, name, trigger, maturity) gives the
   grouping for free — its rows are already the natural families.
3. **Create one worker profile per family**, scoped to that family's skills
   (start from `--no-skills`, then copy in the family; a `--clone` brings the
   whole tree and leaks scope). Set `model.default` + `model.provider` on the
   new profile, and write its role as `--description` — that string is what
   the dispatcher/orchestrator routes on.
4. **Use the registry as the routing table.** The dispatcher bot reads the
   library's own index to decide which worker owns a request; it does not
   re-derive skill selection, and it does not hardcode a copy of the index
   (a copied table drifts the moment a skill is added).
5. **Queue through the board.** The dispatcher bot creates cards with
   `assignee=<worker profile>` and the family's skills attached
   (`skills=[...]`), links parents for dependencies, and then does nothing
   else. The board's dispatcher spawns the worker; the worker completes or
   blocks; the dispatcher bot verifies and reports.
6. **Give the dispatcher bot the orchestrator surface only** (board routing
   tools, no implementation tools). A dispatcher that can also do the work
   will do the work, and the fleet quietly becomes one bot. Concretely,
   disable the `delegation` toolset on that profile: a card with an
   assignee is already claimed and executed by the dispatcher, so a
   dispatcher that can also delegate runs the same job twice and both
   runs write the same output path.
   The `kanban` toolset itself is **off by default** and must be turned on
   for the dispatcher profile before it can open any card:
   `hermes -p <dispatcher> tools enable kanban --platform cli`. A dispatcher
   whose `kanban_create` is missing has no board surface at all, which reads
   as "the board is not working" rather than "this profile lacks a tool".
7. **Scope each worker's skills by linking the source repo's directories
   into that worker's profile.** A symlink per skill directory (or per
   family directory) under `~/.hermes/profiles/<worker>/skills/` keeps the
   repo the single source of truth while the worker's own scope stays
   narrow. Mounting the whole repo through `external_dirs` on every
   profile gives every worker every skill and deletes the boundary.
   The dispatcher profile needs the same treatment: a dispatcher cloned
   from the default profile inherits the whole bundled tree, pays for it
   in prompt tokens on every dispatch, and looks scoped when it is not.
   Narrow it with `hermes -p <dispatcher> skills opt-out --remove --yes`
   (the `-p` is what keeps the removal inside that profile), keep the
   routing skill's symlink, delete the emptied category directories, and
   prove the result with `hermes -p <dispatcher> skills list` plus a
   one-shot prompt — a dispatcher that lists fewer skills but cannot
   answer is broken, not narrowed.
8. **Add one worker at a time, and prove the loop on an existing worker
   before creating a new one.** The first end-to-end hop must land on a
   worker that already exists, or the dispatcher marks the card
   `skipped_nonspawnable` and nothing ever runs. A fleet that is wired but
   unproven is indistinguishable from a fleet that is broken.
9. **Give each worker its own working directory and its own description.**
   `terminal.cwd` per profile decides what relative paths in that worker's
   skills resolve to, and the profile description is what the dispatcher
   routes on. Both are per-profile, and both are invisible from the
   default profile.
10. **Drive a bot from the CLI as a background process.** A real bot turn
    (`hermes -p <bot> chat -q "..."`) runs for minutes and outlives any
    foreground tool timeout. Run it in the background and collect the
    result when it finishes; a foreground call that times out loses the
    transcript and may leave the abandoned attempt's side effects behind,
    so check the board and the working tree before retrying.
11. **Give every fleet member a launcher name.** `hermes profile create
    --no-alias` (and any create that skips aliasing) leaves no wrapper
    script, so typing the profile's bare name does nothing while
    `hermes -p <name>` still works — which looks like a broken bot rather
    than a missing launcher. Create one explicitly per profile:
    ```bash
    hermes profile alias <name>        # writes ~/.local/bin/<name>
    hermes profile alias <name> --remove
    ```
    Then `pm chat -q "..."` and `pm` (TUI) work like any other command.
    Check what actually landed: `which <name>` and read the wrapper — it is
    `exec hermes -p <name> "$@"`. Note that `hermes <name>` is NOT the same
    thing: `hermes` dispatches subcommands, and a profile whose name
    collides with a built-in subcommand (e.g. `hermes pm`, the package
    manager) will run that subcommand instead of the profile.

### Every fleet member needs a launcher name

A worker that can only be reached as `hermes -p <name>` reads as broken to
anyone typing `<name>`. Make the bare name work for every member —
dispatcher and workers alike — and verify it with an actual invocation
(`<name> chat -q "ping"`) rather than by inspecting the wrapper file.

### Verification is the dispatcher's job, and it is not the worker's word

The dispatcher bot must not accept a card's completion on the worker's
say-so. It re-reads the artifact and re-derives the load-bearing numbers
itself — re-running the producing script and recomputing the key
quantities independently — and compares. "The worker says the file is
there" and "the file is there and its numbers recompute" are different
levels of proof, and only the second one is worth reporting.

Two corollaries that cost real debugging time when missed:

- **A card marked done is not a verified result.** The board's `done`
  state records that the worker stopped claiming the card; it says
  nothing about the artifact. Verify the artifact.
- **Read upstream files with `git show`, not by checking out a branch.**
  A dispatcher that needs a value from another branch reads it in place
  and leaves the tree untouched, so the repo's working state stays clean
  and provably so (`git status --porcelain` empty afterwards).

### Deliverable directories hold deliverables

A worker that writes its intermediate output next to the artifact
destroys the deliverable set: a `results/` directory holding both the
report and `_tmp_*.json` scratch dumps gives the next consumer no way to
tell which file is the deliverable. Keep intermediates in a scratch path,
and move any that land in the deliverable directory out during
acceptance.

## Pitfalls

- **Unassigned cards are never dispatched.** A board full of
  `(unassigned)` cards with `running 0` means the fleet is not wired, not
  that the board is idle: the dispatcher claims cards by assignee, so every
  card needs an assignee profile that actually exists on this host.
- **A single-profile delegation pin collapses the fleet.** A delegation
  backend configured with one profile (and that profile as the default) sends
  every spawned child to that one profile's scope, no matter what the
  board says. Multiple routes, or no pin.
- **Skill names resolve from frontmatter, not from the directory.** A skill
  exposed through `skills.external_dirs` is registered under its
  frontmatter `name:` (kebab-case), so a helper that emits directory-style
  ids (`SKILL-064_x`) or plugin-style prefixes (`pkb:SKILL-064_x`) hands the
  caller a name that will not load. Any suggestion/lookup script must be
  checked against the loader's real naming rule before its output is trusted.
- **Splitting profiles breaks cross-profile dispatch scripts.** A relay
  runner that shells out to `hermes chat` targets the *default* profile; once
  the stage skills live in different profiles the subagent no longer sees
  them. Cross-profile dispatch must pass `-p <profile>`, and that is a script
  edit, not a setting.
- **A skill's relative paths bind to the profile's cwd.** A SKILL.md whose
  commands read `skills/<ID>_<name>/bin/foo.py` assumes cwd is the repo root.
  Set that profile's `terminal.cwd` accordingly, or every documented command
  fails with a path error that looks like a missing file.
- **Per-profile dependency installs are not shared.** Each profile resolves
  Python imports from its own environment; check which stage's scripts import
  third-party packages before promising a pipeline runs.
- **Two agents on one profile corrupt each other's memory.** Never point two
  processes at the same `HERMES_HOME`; use a second profile, or an external
  memory provider when shared memory is actually wanted.
- **`--clone` does not copy messaging tokens.** A clone that needs its own
  Telegram/Discord identity must be configured separately; blindly copying
  the token produces a lock error at gateway start, not at clone time.
- **A profile's skills are not inherited from `default`.** If the bot must
  have a skill that only exists in the default profile, copy or expose it
  explicitly — a silently missing skill looks like a broken skill.
- **`config.yaml` is never hand-edited** for the user: `hermes -p <name>
  config set KEY VAL`. A stray indent corrupts the file and breaks that
  profile's gateway.
- **SOUL.md is identity, AGENTS.md is project context.** Putting task
  instructions in SOUL.md makes them follow the bot everywhere, including
  into unrelated work.
- **The roster entry is presentation only.** A profile becomes a visible Bot
  only when Bot Mode stores its title/avatar/section and pins its canonical
  bot chat; a profile driven purely from the CLI stays a plain profile and
  that is fine.
- **Opting out without `-p <name>` narrows the wrong profile.** The
  `.no-bundled-skills` marker and the removal both act on the active Hermes
  home, so the bare `hermes skills opt-out --remove` strips the default
  profile's bundled skills and leaves the profile you meant to scope fully
  loaded. Always pass `-p <name>`.
- **Opt-out removes only pristine bundled skills.** A bundled skill whose
  files were edited by hand is reported as user-modified and kept, so a
  profile that inherited edited skills from a clone stays wide. Read the
  kept list before reporting the scope.
- **Removing bundled skills leaves empty category directories behind.**
  Each category keeps its `DESCRIPTION.md` after its skills are deleted, so
  the tree still looks like the full library and a `skills/` listing still
  shows the empty categories. Remove the directories that hold nothing else.
- **Verify a narrowed profile with a live one-shot, not only a count.**
  `hermes -p <name> skills list` proves the scope; a one-shot prompt proves
  the profile still loads its model, skills and identity after the edit, and
  a profile that loads but cannot answer is not narrowed, it is broken.
- **`--clone` copies the WHOLE skills tree, so a clone is not scoped.** The
  clone lands every skill directory of the source profile; adding three
  symlinks afterwards ADDS to that set, it does not replace it. Verify the
  boundary instead of assuming it:
  ```bash
  hermes skills list | awk -F'│' 'NF>2{print $2}' | sort > /tmp/d.txt
  hermes -p <name> skills list | awk -F'│' 'NF>2{print $2}' | sort > /tmp/p.txt
  diff /tmp/d.txt /tmp/p.txt          # rows that remain = leaked scope
  du -sh ~/.hermes/profiles/<name>/skills   # ~= source size => everything came along
  ```
  To actually scope a bot, start from `--no-skills` (or delete the copied
  directories) and then link/copy only the intended skills. The bot's SOUL.md
  is then the only thing enforcing the boundary — self-discipline, not a
  capability wall.
- **A dispatcher profile that still has the delegation toolset will run
  every carded task twice.** The board dispatcher claims the card and
  spawns the assignee while the delegate runs the same computation in
  parallel; both write the same output file and the last write wins, so
  the artifact you verify may be from either run. Disable the toolset on
  that profile rather than relying on the dispatcher to remember not to
  delegate.
- **`find <profile>/skills -name SKILL.md` reports zero for a symlinked
  tree.** `find` does not follow symlinks, so a profile whose skills are
  all symlinks into a repo looks empty. Use `find -L` or, better,
  `hermes -p <profile> skills list` — treating the zero as "no skills"
  makes you delete a working setup.
- **A cloned profile without `model.default` fails every turn with
  `storage_unavailable`.** `--clone` copies the source `config.yaml` as-is; if
  that file has no `model:` block, the stored session policy carries
  `model=None` and the gateway rejects it
  (`gateway/session_policy.py:restore_policy` → `invalid policy`). The symptom
  is a refusal before any token is spent: "couldn't start the model
  connection: storage_unavailable". Fix with `hermes -p <name> config set
  model.default <model>` and `model.provider <provider>`. The same check
  applies to the source profile: `hermes chat -q "hi" --oneshot` is the
  cheapest way to prove the model block is present.

## Does a dedicated bot run faster than an agent calling the skill?

No. A profile changes *scope and identity*, not speed. Measure before
answering, and measure the three drivers separately, because only the first
two are fixed by scoping:

| Driver | Effect on latency | Fixed by a dedicated profile? |
|---|---|---|
| Toolset count | Fewer tool schemas → shorter prompt → faster first token | Yes — scope `toolsets` in the profile |
| Skill index size | Index is prompt text; every skill row costs tokens | Yes — scope `skills/` |
| Output volume | The model's own verbosity dominates wall clock | No — set it in SOUL.md ("report path + exit code + one sentence") |
| Process startup | ~5–8 s of process boot per invocation | No — identical for every profile |

A persona that asks for judgement and risk disclosure (a "PASS/FAIL plus
what was not checked" contract) makes that bot *slower* than a terse agent on
the same task, by design. Cheap comparative measurement: run the same prompt
once per profile with `-t terminal,file,skills`, time it, and compare input
and output tokens for the two sessions (`session_model_usage` in the profile's
`state.db`) — wall clock alone hides that a slower bot used fewer input
tokens.
