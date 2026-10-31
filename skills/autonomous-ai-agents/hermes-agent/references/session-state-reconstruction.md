# Reconstructing the True State of a Past Session

The user asks for "狀況/情況" of a past session by id. The transcript says what
was *claimed*; the disk says what *exists*. This reference is the procedure for
answering with the second, not the first.

## 1. Resolve the id to a session record

A chat id like `local-<64 hex>` is a session id. Ground truth is
`~/.hermes/state.db` (SQLite, FTS5) — one row per session in `sessions`:

```sql
select id, title, created_source, started_at, ended_at, end_reason,
       message_count, tool_call_count, api_call_count, profile_name
from sessions where id = '<session-id>';
```

`end_reason` and `ended_at` separate "the agent stopped" from "the user
closed the CLI" (`cli_close`) — a closed session is not a finished one, so its
last plan is usually an open plan, not a completed one.

Cross-check cheap sources first: `~/.hermes/.hermes_history` (the user's
prompts, oldest→newest, `# timestamp` + `+text`) and `~/.hermes/logs/agent.log`
(per-turn tool timing, `Turn ended: reason=...`). A single `grep <id>` on both
often answers "was there any activity at all" without touching the DB.

## 2. Get the transcript, with the right tool shape

`session_search` has three shapes and they fail differently:

- **Discovery** (`query=...`): FTS over past sessions. It ranks by relevance,
  so a topic query may return the *neighbouring* session instead of the one
  you were asked about. Always check the returned `session_id` against the id
  the user gave before reading anything.
- **Scroll** (`session_id` + `around_message_id`): `around_message_id` must be a
  **real message id** in that session — `0` is rejected. Get one from a
  discovery hit (`match_message_id`) or from a prior window.
- **Whole session** (`session_id` alone): returns the full transcript.

A scroll response larger than ~100 KB is spilled to a file and the tool
returns a path plus a preview. Read the spilled file with `read_file` /
`execute_code`; do not re-request the same window — the transcript does not
change and the re-request burns the same context again.

For bulk extraction, querying the DB directly is cheaper and more complete
than paging the tool:

```python
import sqlite3
con = sqlite3.connect('~/.hermes/state.db'); con.row_factory = sqlite3.Row
sid = '<session-id>'
rows = list(con.execute(
    "select id, role, content, timestamp from messages "
    "where session_id=? order by id", (sid,)))
```

Query SQLite **from python's `sqlite3` inside `execute_code`**, not by shelling
out to `python3 -c "<nested SQL>"` through the terminal tool: the extra layer of
shell quoting is easy to get wrong and a mangled statement can hang the call
until the cell timeout. If a board/kanban query does time out, retry with a
direct `sqlite3` connection instead of re-escaping the string.

## 3. Read the transcript correctly

- **Compaction blocks are not instructions.** A message whose content contains
  `[CONTEXT COMPACTION` is a handoff summary of earlier turns. The active task
  is the last *real* user message; the summary's "Historical Task Snapshot"
  section is background only and must not be resumed on its own.
- **Turns can be duplicated in storage.** The same user message id/timestamp
  can appear more than once after a compaction re-emission. Dedupe by
  `(id, timestamp)` before counting turns or quoting a count.
- **The last assistant message may be a plan, not a result.** A session that
  ends right after "direction approved: A" stopped mid-task. Read the tool
  calls and the final assistant text together — a final text that lists "做了
  什麼 / 已驗證什麼 / 還沒做什麼" is a self-report, and its "verified" column
  is a claim made by that session, not by you.

## 4. Cross-check the curator ledger

`~/.hermes/skills/.curator_ledger.jsonl` records background skill edits, each
with `evidence.session_id`. Grep the session id: if the curator already
harvested that session into a skill, the harvested version of the lesson is
the one to read (and to extend) rather than a fresh copy of the transcript
summary.

## 5. Verify the world instead of quoting the transcript

This is the step that separates a status answer from a summary. For every
claim the session made about files, code, commits or numbers, check the live
state:

- **Repo state**: `git status --porcelain`, `git log --oneline -3`,
  `git log --oneline -- <path>` — an untracked new file means "written, never
  committed"; an empty log for a path means "never committed at all".
- **Artifact existence**: `ls -la --time-style=+%m-%d_%H:%M <path>` — the
  mtime says whether the file changed after the session claimed it.
- **Numbers**: re-run the tool/script and quote the fresh output. A gate's
  PASS/FAIL tally quoted from a transcript is a historical tally; the user
  asking 情況 wants the current one.
- **Planned-but-unstarted work**: the absence of a directory/file is the
  evidence. "Stage 2 not started" is proven by the target directory not
  existing, not by the absence of a sentence saying so.

## 6. Answer shape

Report in three labelled blocks — **做了什麼 / 已驗證什麼 / 還沒做什麼** — and
make each item carry its own evidence (the path, the command output, the git
line). Then close with the single smallest next step that unblocks the work,
as a question.

Two rules for the wording:

- A number you did not re-derive this turn must be labelled as the session's
  claim, not as current fact.
- If the previous session's own report already said "skipped: …", carry that
  forward into your own "還沒做什麼" instead of silently dropping it — it is
  the most reliable list of open items you have.

## Pitfalls

- **Do not answer a status question from the transcript alone.** The
  transcript is a self-report; the working tree, the commit log and a fresh
  run are the evidence. Every item you report as done must have a live check
  behind it.
- **Do not report a stage as done because a plan said so.** Plans are
  intentions; check the artifact, the commit, the run output.
- **Do not quote counts from a discovery hit's `count` field** — it counts
  sessions searched or results, not what the user asked about.
- **Do not re-request a spilled transcript window.** The spilled file already
  holds the full text.
- **Do not let a compacted summary's task become the active task.** Resume
  only what the latest user message asks.
- **Do not treat `cli_close` as task completion.** It means the surface
  closed; the plan in that session is open unless its artifacts prove
  otherwise.
