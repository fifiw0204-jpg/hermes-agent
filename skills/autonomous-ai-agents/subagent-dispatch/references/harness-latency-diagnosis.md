# Diagnosing "everything is slow": attribute latency per layer

A user reporting "every dispatch and every conversation drags" is describing a
latency problem, not a token problem. Before changing context size, split the
wall clock into layers and measure each one. The layer that dominates decides
the fix, and the layers above it are usually where the intuition goes wrong.

## The layer stack

Measure from the bottom up. Each step up adds one harness layer.

| Layer | How to measure it | What it tells you |
|---|---|---|
| Raw model API | POST the same message straight to the provider endpoint, no agent harness | The provider floor. Nothing above this can beat it. |
| Provider with large context | repeat with a tens-of-thousands-of-tokens system message | Whether context size itself costs latency, or only tokens |
| CLI startup | time a subcommand that exits before any model call (`--help`) | Fixed process/bootstrap cost paid on every invocation |
| Prompt assembly | time a command that builds the system prompt but never calls the model (`prompt-size --json`) | Startup + prompt build, isolated from inference |
| One agent turn | time a oneshot that answers a trivial question | The whole per-invocation bill |
| Delegated child | parent session row minus the child's session row | The orchestration overhead a delegation adds |

Rules that fall out of this stack:

- **A fixed startup cost is paid once per process, not once per turn.** If the
  startup floor is several seconds, then every "dispatch" and every fresh
  oneshot pays it again, and no amount of context trimming will remove it.
  This is the single most common misdiagnosis: people shrink the prompt
  because the complaint is about speed, when the prompt was never the cost.
- **Context size is not latency.** A cached tens-of-thousands-of-tokens context
  that returns in about the same time as an empty one means prompt *volume*
  drives cost, prompt *length* drives latency only weakly. Verify with the
  provider-with-large-context row before blaming the skills index.
- **Skill count barely moves startup.** Compare prompt-assembly time across
  profiles with very different skill counts. If a profile with many skills
  assembles no slower than one with few, the skills index is not the latency
  driver no matter how large its byte count looks.
- **Measure the child and the parent separately.** A delegation's total cost is
  the parent's own turn cost plus the child's turn cost plus the parent's
  orchestration overhead. Reading the child's numbers alone understates the
  bill by the parent's share.
- **Raw API latency is the floor for every worker.** If the provider responds in
  about a second, a multi-second agent turn is harness overhead, and the lever
  is the harness, not the model or the prompt.

## Attributing harness startup

Split the process into phases and time each one: interpreter/bootstrap import,
config load, toolset resolution, tool-schema materialisation, skills import,
system-prompt build. Import cost and config load dominate when they are
measured, and import cost usually includes network-capable modules that are
merely imported, not called — so a startup that touches the network on import
shows up as an unexplained several-second tax.

Do not assume the biggest byte count in the prompt is the biggest time cost.
Schema bytes, skills-index bytes, and prompt-assembly seconds are different
quantities; measure seconds separately.

## Deciding the fix from the numbers

- Startup-dominated → reduce process churn. Keep a long-lived session or a
  persistent worker runtime, or route the leaf work to a harness whose startup
  is cheap. Prompt trimming will not help.
- Prompt-dominated → shrink tools and skills, and prefer the worker that ships
  tool descriptions as prose instead of full JSON schema.
- Model-turn-dominated → the work itself is expensive; budget turns and time
  out the run rather than restructuring context.
- Orchestration-dominated → a delegation layer is adding parent-side turns;
  count parent turns and decide whether the dispatch is worth its overhead.

## Confirming against upstream and community

Local measurement answers "how slow is it here". It does not answer "is this a
known shape of problem, and is there a fix someone already landed". When the
complaint is about a harness feeling slow, check two places before proposing a
fix:

- The harness's own issue tracker and discussions, for reports describing the
  same symptom. An upstream report often names the mechanism (which toolset,
  which cache, which executor) and points at the code path to change.
- Community projects that wrap the same harness, for the patterns people
  converged on (per-purpose bot directories, role files with tool allowlists
  and turn budgets, lazy skill selection).

Rules for using those sources:

- A search-result snippet is not a source. Extract the issue or README body.
- An upstream report is evidence about a mechanism, not a measurement of your
  host. Re-derive the numbers locally before quoting figures.
- Community consensus on a concept ("is this the same idea as X?") is
  answered by comparing the two definitions feature by feature — isolation
  primitive, tool restriction, budget control, dispatch path — and stating
  where they coincide and where one is a superset of the other.
- Prefer the fix that removes the cost where it is spent. If upstream proposes
  a narrow API change, note it as a lever but do not present it as the only
  option when moving the work to a cheaper harness removes the cost entirely.

## Cache-hit percentage is a bad efficiency metric

A harness with a large static prefix can show an excellent cache-hit rate and
still process far more tokens than a minimal one. Rank harnesses by total
traffic and by wall clock per invocation, not by hit rate. Report the
uncached-input share alongside the hit rate so the two are not conflated.

## Reporting a latency diagnosis

State the layer table with the measured seconds, name the dominant layer, and
say what was NOT measured (turn-by-turn timing inside a live conversation is
separate from oneshot startup; do not present one as the other). A latency
claim without its layer is not actionable.
