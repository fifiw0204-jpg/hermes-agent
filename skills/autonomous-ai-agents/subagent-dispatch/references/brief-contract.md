# Brief Contract

The brief is the child's entire input. It starts with a fresh context and a
focused system prompt — no conversation history, no memory, no user preferences.
Anything not written in the brief does not exist for the child.

## Annotated template

```
GOAL
Rewrite the paragraph in docs/intro.md so it states the v2 pricing in one
sentence. Do not touch any other file.

CONTEXT
docs/intro.md currently prices the product at v1. The v2 price is 29 USD per
month, billed yearly. The surrounding paragraphs use plain prose, no tables.
The repo is a git checkout; the working tree is clean.

DELIVERABLES
docs/intro.md

VERIFY
python3 scripts/check_docs.py docs/intro.md

SKILL TO LOAD
humanizer

CONSTRAINTS
Do not reformat other paragraphs. Do not add headings. Keep the file's
existing line wrapping.
```

## Field rules

| Field | Required | Rule |
|---|---|---|
| GOAL | yes | One sentence, outcome not steps. Repeat it verbatim as `goal` in the `delegate_task` call. |
| CONTEXT | yes | Paths, conventions, constraints. Point at files; do not paste them. |
| DELIVERABLES | yes | One real path per line. These become the manifest you verify afterwards. |
| VERIFY | yes | The exact command that proves the work landed. The child runs it; you re-run it. |
| SKILL TO LOAD | no | A skill name. The child calls `skill_view` on it. Omit when no skill matches. |
| CONSTRAINTS | no | What not to touch, and what "done" excludes. |

## Rules

- **Same goal in both places.** `delegate_task(goal=...)` and the brief's GOAL
  line must match. A parent reading only the result entry then knows what was
  asked.
- **DELIVERABLES is the manifest.** Write the same paths, one per line, into a
  separate manifest file. That file is what `scripts/verify_artifacts.py` reads.
- **VERIFY must be runnable as-is.** A command the child can paste and execute
  without guessing paths. "Check that it works" is not a VERIFY line.
- **One brief per child.** Children share no context. When dispatching parallel
  workstreams, each entry carries its own complete brief — do not write "same
  as above".
- **No secrets.** The brief lands in the child's transcript and in the
  session log. Pass a path to a credential file, not the credential.

## Common failures

| Failure | Symptom | Fix |
|---|---|---|
| Missing CONTEXT | Child guesses conventions, edits the wrong style | Name the paths and the rule to follow |
| Vague DELIVERABLES | Child writes a report instead of the artifact | One concrete path per line |
| No VERIFY | Child claims success on an unrun command | Give the exact command |
| Whole-file paste | Context budget blown before work starts | Point at paths, don't paste |
| Unanswered questions | Child invents an answer (no `clarify` tool) | Resolve ambiguity in the brief first |
