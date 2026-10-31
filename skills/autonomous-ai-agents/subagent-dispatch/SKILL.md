---
name: subagent-dispatch
description: "Dispatch (派工) work to subagents; verify every output."
version: 1.0.0
author: fifiw0204-jpg, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Delegation, Subagents, Orchestration, Verification, Workflow]
    related_skills: [hermes-agent, subagent-driven-development, systematic-debugging]
---

# Subagent Dispatch

Delegate work to subagents through `delegate_task` with a written brief, an explicit
budget, and an artifact check before you report success. This skill covers the
decision to delegate, the brief contract, and post-run verification. It does not
cover nested fan-out (see `subagent-driven-development`) or non-Hermes agent CLIs
(see `claude-code`, `codex`, `opencode`).

## When to Use

Use this skill when a task must be handed to a subagent via `delegate_task`:
multi-file edits, a self-contained investigation, parallel workstreams, or a
second opinion on a risky change.

## Prerequisites

- The `delegation` toolset enabled (it ships by default; confirm with `hermes tools`).
- A writable scratch directory for the brief and artifact manifest.

## How to Run

1. Decide with the rubric below. Delegating a two-line edit costs more than it saves.
2. Write the brief to a file and pass its content as `context`.
3. Dispatch with `delegate_task`, naming the skill the child should load.
4. When the child returns, verify the artifacts it claims, then report.

## Quick Reference

| Step | Tool | Artifact |
|---|---|---|
| Rubric | read this skill | — |
| Brief | `write_file` | `<scratch>/brief-<slug>.md` |
| Manifest | `write_file` | `<scratch>/artifacts-<slug>.txt` |
| Dispatch | `delegate_task` | — |
| Verify | `terminal` | manifest → PASS/FAIL table |
| Steer / stop | `delegate_task` (`action=steer` / `action=stop`) | — |
| Card path (board budget) | `references/kanban-card-dispatch.md` | board rows + run row + worker turn count |
| External leaf CLI (pi/claude/codex) | `references/external-leaf-workers.md` | per-worker `out.json` + grader table |

## Procedure

### 1. Decide whether to delegate

Delegate only when all three hold:

- **Scope**: more than ~3 files touched, or a task that is multi-stage (research then edit, or edit then verify).
- **Self-containment**: the child can finish without asking the user anything. Children have no `clarify` and no `memory` tool.
- **Verifiability**: the result can be checked against a file, a command exit code, or a URL. A task whose only output is a prose opinion is cheaper to do inline.

Do not delegate when the task needs the live conversation state (a decision the user has already made), when it is a couple of edits you can finish yourself, or when it would need a second round of clarification.

### 2. Write the brief

The brief is the child's whole world. It gets a fresh context, so anything you omit is gone. Include, in this order:

```
GOAL
<one sentence: the outcome, not the steps>

CONTEXT
<paths, conventions, constraints, why this matters>

DELIVERABLES
<named artifacts, one per line, each a real path>

VERIFY
<the exact command or check that proves the work landed>

SKILL TO LOAD
<skill name, if the child should call skill_view on one>

IN SCOPE
<the slice of work the child owns>

OUT OF SCOPE
<adjacent areas the child must not touch, read, or investigate>

CONSTRAINTS
<what not to touch, what "done" excludes>

STOP WHEN
<the condition that ends the work, and what "enough to answer it" looks like>
```

Read `references/brief-contract.md` for the annotated template and the field
list the child is expected to see.

Keep the brief in the session scratch directory, not `/tmp` — the path is
recorded in the conversation and a scratch path survives the session.

### 3. Dispatch

Read the brief file back and pass its exact text as `context`, with the
one-sentence outcome as `goal`.
Keep `goal` and the brief's GOAL line identical, so a parent reading only the
result entry can still tell what was asked.

Name a skill for the child when the task matches one — the child inherits the
skills index and can call `skill_view` itself:

```
SKILL TO LOAD
systematic-debugging
```

Budgets come from config, not from the call: `delegate_task` ignores a
caller-supplied `max_iterations` and always uses `delegation.max_iterations`
from the config file (default 250). To change the ceiling, edit config; do not
pass the argument and expect it to apply.

The config file is `$HERMES_HOME/config.yaml` — normally `~/.hermes/config.yaml`,
but a named profile repoints `HERMES_HOME`, so under a profile the profile's own
`config.yaml` wins. Check which one you are editing.

**Check where a child will actually run before you write the brief.**
`delegate_task` routes by `delegation.backend`; under the `profile_routes`
backend, `delegation.backends.profile_routes.default` decides the profile for
any task that names none — and that default is often a foreman/router profile
whose job is to open board cards. A child sent there re-routes the work
instead of doing it, so the dispatch looks successful and nothing lands. Read it
with `hermes config get delegation.backends.profile_routes.default`; when the
default is a routing profile, unset it so children run on the parent's own
route: `hermes config unset delegation.backends.profile_routes.default`. The
Hermes config file is guarded against file edits — `patch`/`write_file` on it
is refused — so make every config change through `hermes config set|unset`.

Dispatch parallel workstreams as separate entries in one `delegate_task` call.
Give each entry a complete brief of its own — children share nothing.

#### Parallel work lines that share one working tree

Several children editing the same checkout is workable only when their file
sets are disjoint and every generated artifact has exactly one owner.

- **Give each child a path allow-list, not a topic.** "Fix the frontmatter"
  lets two children open the same file; "exactly these N paths, and no other
  file in the tree" cannot collide. Repeat the list in the brief and the goal.
- **One owner per generated file.** If a script writes both a registry and a
  README, exactly one child may edit or run it — a second child running it
  rewrites the first child's output, a lost-update race that reads as a flaky
  tool.
- **Tell non-owners to report, not edit.** When a child finds a reference it
  must change in a file another child owns, the brief should instruct it to
  report file + line + old string + new string and let the parent apply it
  once both land.
- **Gate the generator run on the move it depends on.** A child that must wait
  for another child's file move should poll for that move's completion (the
  old path's absence) instead of running the generator speculatively and
  recreating the file someone is moving.
- **Sequence the writer-last line.** The child that commits and pushes waits
  for the tree to go quiet: `git status --porcelain` unchanged across two
  consecutive checks, plus the other children's acceptance conditions (audit
  clean, counts reconciled), before staging. Give it a timeout and an
  instruction to report which condition failed rather than commit a
  half-finished tree.
- **A quiet tree is not a finished tree.** A child between edits leaves the
  working tree unchanged for minutes, so "nothing changed in two checks"
  proves nothing about the other children's progress. Gate the commit on
  each sibling's *reported* completion, and prefer dispatching the commit
  line only after the sibling lines have reported — not in parallel with
  them. When the commit line must run in parallel, the parent still sweeps
  for leftovers after the last sibling reports: re-run `git status` and
  commit or fix whatever arrived after the commit, because a late edit
  silently lands outside the pushed history.
- **Keep the brief on disk and patch it in place.** Put the full brief in a
  scratch file, point the goal at its path, and repeat the load-bearing facts
  in `context` so a child that skips the file still has them. Patching the
  file mid-flight does not need a re-dispatch.
- **Gate a dependent line on a marker file, not on a quiet tree.** When line B
  must not start until line A stops editing the files line B will commit, tell
  line A to write a completion marker (`DONE-<slug>`) as its LAST action, and
  tell line B to poll for that file and to abort if the sibling instead wrote
  `FAILED-<slug>`. A tree-level quiet check cannot tell "still editing" from
  "done"; the marker can. A second line started too early commits a
  half-finished tree and the late edit lands outside the pushed history.

Put a stopping condition in the brief: the question to answer and what "enough
to answer it" looks like. A child left open-ended will keep widening the
investigation — reading adjacent code, running the repo's whole test suite,
going down a second research thread — and the batch will not converge on
its own. When you see that happening, steer it: name the scope to collapse to
and the questions to stop chasing. Steer on the live transcript, not on the
summary, which arrives only at the end.

### 3b. Dispatch through a kanban card (the card path)

When the work goes to a worker profile on the Hermes board, the dispatcher owns
execution and the budget lives on the card, not in a brief. A card created
without a ceiling has no ceiling: the worker runs until it decides it is done.
Set the budget knobs at creation time, on every card.

| Knob | Where | What it stops |
|---|---|---|
| `max_runtime_seconds` | card (`kanban_create` arg; CLI `--max-runtime`) | wall clock — the dispatcher SIGTERMs, then SIGKILLs, the worker and re-queues the card as `timed_out` |
| `goal_mode` + `goal_max_turns` | card (`--goal`, `--goal-max-turns`) | turns — when the budget is spent the card is blocked for review instead of looping (default 20 turns) |
| `max_retries` | CLI `hermes kanban create --max-retries N` only — `kanban_create` does not expose it | consecutive failures (spawn_failed / timed_out / crashed) trip the breaker and the card is parked `blocked`; otherwise the dispatcher-level `kanban.failure_limit` applies (default 2) |
| acceptance criteria in the card body | card body | the review checkpoint — `kanban_request_review` / `kanban_request_changes` move the card without the worker declaring itself done |

Estimate first, then set the ceiling from the estimate. State the estimate in
the card body too: the ceiling alone tells the worker nothing about how much
work is expected.

| Estimated work | `max_runtime_seconds` | `goal_max_turns` |
|---|---|---|
| ≤ 5 min | 300 | 5 |
| 5–15 min | 900 | 10 |
| 15–60 min | 1800–3600 | 20 |
| > 60 min | split the card | — |

Above an hour, split the card rather than raising the ceiling: a timeout counts
as a failure, so one over-long card spends its whole retry budget on a single
timeout and ends up parked instead of retried.

Progress signals the dispatcher already maintains: `last_heartbeat_at` is
written by the worker while it is making progress (auto-heartbeat, roughly once
a minute), and `dispatch_stale_timeout_seconds` reclaims a running card with no
heartbeat. That is a *no-progress* ceiling, not a runtime ceiling — a worker
that keeps heartbeating while looping still runs indefinitely, which is why
`max_runtime_seconds` is the real stop.

Audit existing cards for missing ceilings with
`scripts/audit_card_budgets.py`; the field semantics and the CLI/tool split are
in `references/kanban-card-dispatch.md`.

**A card outlives the session that opened it.** A foreman session that closed
(`end_reason` set, chat stopped) says nothing about the card: the worker is a
separate process with its own ceiling and the board keeps running it. When
someone asks for the state of that work, answer from the board (`tasks.status`
plus the `task_runs` row plus the worker pid's liveness), not from the parent
session's last message. Each profile keeps its own session store, so a session
id belonging to another profile has to be looked up in that profile's
`state.db` — the default profile's session tool reports "not found" for it.
The lookup and the board queries are in `references/kanban-card-dispatch.md`.

**A worker that keeps re-reading its card is looping, and a survey request
keeps it looping.** Turn count climbing while the same card id is re-fetched
and no production file's mtime moves is a worker burning model turns, not
computing. Answer it with one mechanical instruction — what you verified and
how, the exact remaining edit, the exact command, the exact file to commit —
and then leave it a long interval instead of polling. Copy any already
validated artifact out of the worktree before the card's ceiling hits, because
a timeout can discard uncommitted work.

### 4. Verify before you report

A child's summary is a self-report, not a fact. Check the artifacts yourself.

Write one expected artifact path per line to a manifest file, then run the
bundled script:

```bash
python3 skills/autonomous-ai-agents/subagent-dispatch/scripts/verify_artifacts.py <scratch>/artifacts-<slug>.txt
```

It prints one PASS/FAIL row per path and exits non-zero when anything is
missing or empty. A child that reports "done" while leaving the deliverable
missing is a failure, regardless of the wording in its summary.

The manifest proves existence, not content. If the brief carried a constraint
— a line limit, a size cap, a required heading — check that too, with the
child's own `VERIFY` command. Existence plus a self-report is not
verification.

Read the artifact only after the child's final summary. A child that iterates
on its deliverable rewrites the file several times, so a read taken mid-run
captures an intermediate revision — a line count or byte size that disagrees
with the child's report is usually a timing artifact, not a false claim. When
they disagree, grep the child's live transcript for each write and the size it
measured before concluding the child misreported.

Close the child's open questions yourself. A summary ending in "Not checked: X"
hands you the remaining work; X is not done until you resolve it.

If the child is still running, steer it instead of waiting:

```
delegate_task(action="steer", subagent_id="sa-0-...", message="...")
```

### 5. When the user asks for dispatch, the parent dispatches

"Dispatch it" / "派工" is not a request for a recommendation about how to do the
work. It means the child does the work.

- **The parent writes the brief and verifies the result; it does not make the
  edit.** The parent's job is the independent check — re-derive the child's
  load-bearing numbers, run the release gate, read the artifact back. Editing
  the files yourself while nominally dispatching means no fresh context ever
  checked the work.
- **If you already made the edits, revert them and re-dispatch.** Presenting
  your own edits as the dispatched result is the failure this mode exists to
  prevent.
- **Enumerated items each get their own brief.** "Dispatch all three" means
  three entries with three scopes — not one merged child and not the easiest
  one alone, so a failure in one does not block the others.
- **One named step is one step.** "Open the branch" or "start the next step"
  is the deliverable — branch, dispatch, verify. Expanding it into
  implementation, tests, changelog and PR is scope the user did not ask for.
- **A read-only brief must forbid writes explicitly, and you prove it.** Say
  the child must not write, commit, push, check out, or comment, and must read
  remote refs with `git show`/`git grep`/`git ls-tree` instead of switching
  branches. Afterwards check `git status --short` is empty and the branch list
  is unchanged in every repo the child could reach — children leave registered
  worktrees and stray test processes behind.
- **When another agent already owns a scope, verify coverage read-only and
  report.** Two agents editing the same module is a conflict you create.
- **"This is taking too long — stop and report what you have" is an abort
  instruction.** Stop the children, mine their partial transcripts and scratch
  output for the findings they already gathered, report those. Do not
  re-dispatch to complete the sweep.

## Pitfalls

- **Do not delegate trivia.** Two files and a one-line fix cost more to hand off than to do.
- **Do not write an open-ended brief.** Without a stopping condition, a child widens scope until the batch stops converging.
- **Do not put the whole repository in `context`.** Point at paths; the child has its own file tools.
- **Do not expect the child to ask you anything.** No `clarify`, no `memory`, no `delegate_task` — anything unstated is assumed finished.
- **Do not trust "done".** Run the manifest check; this is the entire point of the skill.
- **Do not verify mid-flight.** Wait for the child's final summary, then read the artifact once — an early read catches a revision the child is about to replace.
- **Do not inherit the child's open questions.** Anything it marked "Not checked" is yours to close before you report.
- **Do not pass `max_iterations` to `delegate_task`.** It is logged and ignored; config is authoritative.
- **Do not let a child report success for an external side effect.** Require a verifiable handle — a path, an ID, a URL — and read it back yourself.
- **Do not leave template markers in the goal.** A goal containing an unexpanded placeholder (e.g. a literal `<skill-name>`) is rejected before dispatch; substitute the concrete example.
- **Do not let two children own the same file or the same generator.** Concurrent writes lose one side's edit, and a second run of a generating script silently overwrites the first child's output.
- **Do not run one task through two execution paths.** A kanban card with an assignee is already claimed and executed by the Hermes dispatcher. Delegating the same task in parallel produces two runs of the same computation racing on the same output file, and the second write wins. Pick the card path or the delegate path, never both. If both already ran, say so and check which write survived. Fix the mechanism, not just the rule: if the offending toolset is available to the session, remove it (`hermes -p <profile> tools disable delegation --platform cli`) — a rule written in a skill only binds the sessions that loaded that skill, while an absent tool binds every session.
- **Do not let a worker's scratch files land in the deliverable directory.** A worker that writes its intermediate output next to the artifact it produces leaves a results directory where the next consumer cannot tell which file is the deliverable. Send intermediates to a scratch path, and move any that land in the deliverable directory out during acceptance. A rule written only in a skill or a prompt is not enough — the model can ignore it — so remove the ability: disable the `delegation` toolset on the dispatching profile (`hermes -p <profile> tools disable delegation --platform cli`). Text says what to do; a missing tool makes the wrong path impossible.
- **Do not treat a pushed branch as the finished state.** The commit line and the sibling lines can land in either order; after the last sibling reports, re-check `git status` and the remote ref, and fold in whatever the commit line missed.
- **Do not re-dispatch a failed child before checking what it already wrote.** "Failed — no reply: the turn stopped while a tool result was pending" and "interrupted" mean the SUMMARY was lost, not that the work was. List the child's expected output paths on disk first; a child that wrote every deliverable and died on its last reply needs no re-run, only verification. Re-dispatch only the missing or unusable slice.
- **Do not let a child keep writing files you have already consumed.** A still-running sibling that owns a spec dir, a writer module, or any input to a finished build will silently invalidate it. Stop those children (action="stop") once you have shipped a build that depends on their files, and say in the report that they were stopped, so the user knows the work was cut short rather than completed.
- **Do not treat a background process failure notification as current state.** A job that died reading a file mid-rewrite reports a parse error against a file that has since been regenerated. Re-verify the current file before reacting; the stale error is noise.
- **Do not let a background-process notice become a reply to nobody.** A
  completion notification arrives in the transcript as a user-role message and
  is marked gateway-generated; answering it as a request produces a message
  addressed to no one. Read the payload, use it as evidence if it is, and do
  not treat it as a fresh instruction.
- **Do not let an external agent CLI's own summary stand in for verification.** A leaf worker CLI (pi, claude, codex) has no session DB, no memory and no self-check, so nothing it says about its own output counts until a separate grader recomputes it. Wrap the run in a wall-clock ceiling, give each worker its own state directory, and have it emit one file instead of prose.
- **Do not let two execution paths reach the same leaf artifact.** A runner script that fans out to the CLI and a worker profile that calls the CLI both produce the same output file; the second write wins. Put all real logic in one runnable artifact and let the other layer only trigger it and report.

## Verification

Before reporting the delegated work as done:

1. The manifest script exits 0 (every artifact exists and is non-empty).
2. The child's own `VERIFY` command passed — re-run it if it is cheap.
3. Any external side effect (upload, published page, remote record) was read
   back at its source, not taken from the child's summary.
4. Every "Not checked" item in the child's summary is closed by you, not left dangling.
5. The child's numbers were recomputed independently — a reported line count,
   byte size, or citation you did not re-derive yourself is still a claim.
6. For parallel lines over one tree: each child's file set was disjoint, and the
   commit was made only after the tree stopped changing and every line's
   acceptance condition passed.
7. Any child that reported failure or was interrupted was checked against the
   filesystem: its expected outputs either exist and pass the gate, or the missing
   slice was re-dispatched. No failed child is reported as either done or lost
   without that check.
8. Any still-running child whose files a shipped artifact depends on was stopped,
   and the report says so.
9. A card that was converted into delegate briefs had its worker stopped first:
   the card is blocked, no `kanban_worker_client` process is left running for it,
   and the worktree's uncommitted files were preserved for the briefs to inherit.
