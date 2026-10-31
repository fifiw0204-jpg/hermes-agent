# Dispatching to a non-Hermes leaf worker CLI

Depth note for handing work to an external agent CLI (pi, claude, codex, opencode)
from a Hermes session. The external CLI has no session DB, no memory, no kanban and
no self-verification, so the parent must supply every one of those.

## Preconditions before the first run

Prove the CLI is on PATH and prints a version:

```bash
command -v pi && pi --version
```

If it lives outside PATH, export the absolute path in the runner rather than
installing a symlink into a shared bin dir — the runner script is the artifact
that gets versioned.

Each worker needs its own state directory (config, auth, session logs) and that
directory must be mode 600 on the auth file. Point the CLI at it with its own
env var per worker; workers sharing a home directory overwrite each other's
sessions and auth.

## The brief shape that does not drift

Imperative, single-purpose, one entry point, one output path:

```
Run <command> with <params-file>.
Write the result JSON to <output-path>.
If the command fails, run it once more unchanged and report the second exit code.
```

Rules that follow from this shape:

- **Name the exact entry point.** Two entry points in the same repo can return
  different numbers for the same parameters; the brief must not leave the choice
  open.
- **Include the golden/variant flag.** A golden dataset that needs a non-default
  variant will exit with a validation error if the brief omits it.
- **Say "run it once more unchanged" on failure.** Tool-call success rates below
  100% are normal; one retry is cheap, a silent failure is not.
- **Do not let the worker choose scope.** No "investigate", no "also check" —
  the brief states the one thing to produce.
- **Ask for a file, not prose.** A worker that reports "found 7 issues" in chat
  gives you an unverifiable number; a worker that writes `out.json` gives you
  something a script can grade.

## Wrapping the run

Always bound it:

```bash
timeout 300 <cli> ... -p "$(cat brief.txt)" > run.jsonl 2> run.err
echo "exit_code=$?" > run-exit.txt
```

Record wall time and exit code next to the output. A worker with no wall-clock
ceiling is a worker that can hang forever, and an agent that hangs does not fail
loudly — it just stops producing artifacts.

## Grading the output externally

The worker's own report is a claim. Write a separate grader that recomputes the
expected values and prints one row per item:

```
item | correct | wrong | numeric delta
```

Then quote the grader's table, never the worker's summary. Two independent
implementations disagreeing on a count is normal; only the external recompute
tells you which is right.

## Fan-out

Once one worker passes end to end, scale it:

- one CLI invocation per item, each with its own state dir and its own output path
- concurrency capped by RAM and CPU (8 workers is fine on a 2 vCPU / 4 GB box
  when each worker is a short script)
- the grader runs after the fan-out completes, over all outputs at once
- a per-worker failure must not abort the batch: capture exit codes per worker
  and let the grader mark the failures as failures

## Where this fits the Hermes fleet

Two execution paths for the same item race on the same output file. Pick one:

- the card path — a Hermes worker profile runs the CLI and writes the artifact,
  so the board holds the budget and the trail
- the script path — a runner script fans out to the CLI directly; the card only
  triggers it and reports the result

The recommendation is to put all real logic in the runner (one artifact, rerunnable,
testable) and use the card for budget and tracking. Whatever you choose, the
routing decision must name it, and the other path must not also be available.
