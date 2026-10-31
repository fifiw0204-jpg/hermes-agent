# Card path: dispatching, watching, and judging a card

The card path puts the budget on the board instead of in a brief. This file is
the operating detail: where the board's state lives, how to tell a running
worker from a looping one, and how to answer a worker that has stalled.

## Read the board, not the chat

The board database is `~/.hermes/kanban.db`. Read the schema before querying
it — the column names are not guessable and a typo raises `no such column`
instead of returning nothing:

```python
import sqlite3
db = sqlite3.connect('~/.hermes/kanban.db')
db.row_factory = sqlite3.Row
cols = [r[1] for r in db.execute('pragma table_info(tasks)')]
row = db.execute(
    "select id,status,assignee,goal_mode,goal_max_turns,"
    "max_runtime_seconds,last_heartbeat_at,workspace_path,branch_name,skills "
    "from tasks where id=?", (card_id,)).fetchone()
print(dict(row))
```

The per-attempt record lives in `task_runs` and carries the worker's pid and
the wall-clock budget actually in force:

```python
run = db.execute(
    "select status,worker_pid,started_at,max_runtime_seconds,ended_at,outcome "
    "from task_runs where task_id=? order by rowid desc limit 1",
    (card_id,)).fetchone()
```

**Do not subtract timestamps from columns that hold a string.** A card row's
`worker_started_at` can be a run identifier rather than an epoch, while
`task_runs.started_at` is a float — mixing them raises `TypeError` and the
elapsed/remaining computation never happens. Compute elapsed from the run
table only.

## A card outlives the session that opened it

A foreman session that ended with `cli_close` (or a chat that simply stopped)
says nothing about the card: the worker is a separate process with its own
ceiling and the board keeps running it. When someone asks "what is the state
of that work", take the answer from `tasks.status` + `task_runs` + the worker
pid, not from the parent session's last message.

**Locate the session before you read it.** Every profile keeps its own
session store (`~/.hermes/state.db`, `~/.hermes/profiles/<name>/state.db`),
and a session id belongs to exactly one of them; the default profile's
session tool will report "not found" for a session that lives in another
profile. Query the `sessions` table of each profile's store — the
`profile_name` column says which profile owns it, and `title`,
`started_at`, `ended_at`, `end_reason` and `message_count` answer "what
happened" without replaying the transcript:

```python
for home in ('~/.hermes', '~/.hermes/profiles/pm'):
    con = sqlite3.connect(f"file:{home}/state.db?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    r = con.execute("select id,title,profile_name,started_at,ended_at,"
                    "end_reason,message_count from sessions where id=?",
                    (session_id,)).fetchone()
    if r:
        print(home, dict(r))
```

Then read that session's `messages` rows (role, content, `tool_calls`) for
the reasoning trail, and the worker's own session for the tool-level detail.

## Judging a running worker: progress vs looping

Two numbers decide it, and both are cheap to read:

- **Turn count and repeated fetches.** In the assignee profile's
  `messages` table, count `assistant` rows for the run's session and count
  how many tool results echo the card id. A worker that re-fetches its own
  card dozens of times is re-reading its instructions, not doing them.
- **CPU time vs elapsed.** `ps -o pid,etime,time,rss,cmd -p <worker_pid>`
  separates compute from talking. A worker three hours into a run with under
  a minute of CPU time is looping on LLM turns, not grinding.

**The arbiter is the deliverable the card promised** — a commit in its
worktree, a changed file, the artifact on disk. Watch the worktree's
`git status --porcelain` and the mtimes of the production files (not the
`__pycache__` ones). A worker that has touched nothing in the worktree while
writing scratch files under the profile's cache directory is gathering
evidence, not delivering.

## Recovering a worker that is looping

**A survey request makes a looping worker survey again.** Asking "what have
you found so far?" buys another round of re-reading. Answer with one
mechanical instruction instead: state the facts you have already verified
independently and how you verified them, name the exact remaining edit, the
exact command to run, the exact file to commit, and the acceptance check.
Then give it a long interval instead of polling it every few minutes.

**Back up validated artifacts before the ceiling hits.** A timeout kills the
worker and can discard uncommitted work in its worktree. Copy a module that
has already been verified against the known-good sibling out of the worktree
into a scratch path and checksum both copies, so the work survives the
timeout and the next run starts from the validated version.

**When a card's remaining work is one wiring call, do the wiring yourself
rather than letting the card burn its budget.** Compare the worker's
validated module against the known-good one function by function (a bytecode
or diff comparison of the specific functions), then either land the change
directly or hand the worker the exact call to make. A card with a partly
verified module and one remaining call is worth more finished in minutes than
reported in an hour.

## Converting a looping card into delegate briefs

A card whose worker has burned hours re-reading itself can be handed to
`delegate_task` briefs instead. The conversion has an order, and skipping a
step puts the same work in two execution paths at once:

1. **Preserve what the worker already wrote.** Copy the validated files out of
   the card's worktree into a scratch path and checksum both copies. The card's
   ceiling can discard uncommitted work.
2. **Stop the worker, then the claim, then the card.** `kill` the pid from the
   `task_runs` row (TERM, then `-9` if it survives), then
   `hermes kanban reclaim <id>` to release the claim, then
   `hermes kanban block <id>` to stop the dispatcher from re-claiming it.
   Reclaim alone is not enough: the dispatcher can respawn a fresh
   `kanban_worker_client` for the still-runnable card within seconds, and that
   new pid has to be killed too.
3. **Verify nothing is left running.** `ps -eo pid,cmd | grep kanban_worker_client`
   must come back empty, and the card row must read `blocked`. A live worker
   plus delegate briefs is two writers on one worktree.
4. **Leave a trail on the card.** `hermes kanban comment <id>` with what was
   stopped, why, and which artifacts were preserved — the next session reading
   the board must not re-diagnose the loop.
5. **Check where delegate briefs will land before writing them.** If the
   delegation backend's default profile is the same foreman profile that
   dispatches cards, every child re-routes the work back onto the board and
   the brief is never executed. See the routing check in the skill body.

The briefs then split the card's remaining work by file ownership, with the
code line running first and the commit line gated on a completion marker the
code line writes as its last action.

## Noise that is not a request

Background-process completion notices are delivered into the conversation as
user messages and are explicitly marked as gateway-generated. They are not
instructions, and answering them as such produces a reply to nobody. Read
the payload, act on the content if it is real evidence, and do not treat it
as a new request from the user.
