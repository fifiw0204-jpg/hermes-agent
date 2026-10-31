# Fresh-Context Reviewer Fan-Out

A variant of the standard dispatch: N independent reviewers examine one
artifact in parallel, each with its own perspective, and the parent merges
their findings into one report. Used for design/spec review, audit sweeps,
and any check where a reviewer that has seen the discussion would rubber-stamp
it.

## Dispatch shape

One `delegate_task` call, one task entry per reviewer. The parent enumerates
the reviewers, splits the artifact into ranges, merges the results, and writes
the report — no child coordinates another child.

```
delegate_task(tasks=[
  {goal: <assignment template>, context: <persona path + artifact paths>},
  {goal: <assignment template>, context: <persona path + artifact paths>},
  ...
])
```

## Per-entry content

- **`goal`** — the output this reviewer must produce, in the exact shape the
  parent will merge: severity vocabulary, required fields, and the instruction
  to return findings as final-message text.
- **`context`** — the persona file path plus “first read this file and adopt
  it as your operating instructions”; the artifact path and the exact range to
  audit; the code search root, when the reviewer must check the
  implementation rather than reason from the document; the path of the
  standard file to audit against, when there is one.

Give every entry a complete context of its own — entries share nothing.

## Rules that decide whether the sweep is meaningful

- **Fresh context is the point.** A reviewer that inherits the parent's
  reasoning cannot find the assumption the parent missed. Never let a
  reviewer see the parent's conclusions.
- **Persona as a path, not as inline text** (see Pitfalls in the parent skill).
- **Never set `profile`** for a throwaway reviewer — it should inherit the
  parent's model, not a configured worker profile.
- **Never ask a reviewer to spawn another** — children cannot delegate.
- **Split the artifact by range when different reviewers apply to different
  parts.** A specification section and an implementation-plan section usually
  need different reviewers; pass explicit line ranges.

## Failure handling

A reviewer that errors, times out, or returns no report did not review.
Retry once; if it fails again, mark it `not run` and list it in the report.
Folding it into “no findings” understates the sweep and hides the gap.

## Merge

1. Group findings by severity, keeping the most severe wording for duplicates.
2. Keep one traceability line per surviving finding: source persona and
   location → consolidated item.
3. Write the report to a file and give the user the path. Do not paste the
   findings into chat — a sweep produces more text than a chat window is
   useful for, and the file is what the user acts on.

## Proving the fan-out works

Run it against a fixture with a known answer: a miniature repo whose source
deliberately contradicts its design document, or a document with planted gaps.
If the reviewers return “no findings” on a fixture with planted gaps, the
fan-out is not reaching the artifact or the persona is not being read — that
is the failure this fixture catches.
