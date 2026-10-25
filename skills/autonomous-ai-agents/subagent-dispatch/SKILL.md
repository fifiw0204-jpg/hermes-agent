---
name: subagent-dispatch
description: "Delegate to subagents with briefs and verified outputs."
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

CONSTRAINTS
<what not to touch, what "done" excludes>
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

Dispatch parallel workstreams as separate entries in one `delegate_task` call.
Give each entry a complete brief of its own — children share nothing.

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

If the child is still running, steer it instead of waiting:

```
delegate_task(action="steer", subagent_id="sa-0-...", message="...")
```

## Pitfalls

- **Do not delegate trivia.** Two files and a one-line fix cost more to hand off than to do.
- **Do not put the whole repository in `context`.** Point at paths; the child has its own file tools.
- **Do not expect the child to ask you anything.** No `clarify`, no `memory`, no `delegate_task` — anything unstated is assumed finished.
- **Do not trust "done".** Run the manifest check; this is the entire point of the skill.
- **Do not pass `max_iterations` to `delegate_task`.** It is logged and ignored; config is authoritative.
- **Do not let a child report success for an external side effect.** Require a verifiable handle — a path, an ID, a URL — and read it back yourself.

## Verification

Before reporting the delegated work as done:

1. The manifest script exits 0 (every artifact exists and is non-empty).
2. The child's own `VERIFY` command passed — re-run it if it is cheap.
3. Any external side effect (upload, published page, remote record) was read
   back at its source, not taken from the child's summary.
