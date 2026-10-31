# Controlling the Context a Dispatched Worker Receives

How to make a dispatched worker carry a small context, how to prove what it actually
carries, and what the arithmetic says is worth shrinking.

## The rule that decides everything

**A `delegate_task` child inherits the toolset of the parent session that spawned it.
Nothing else narrows it.**

- The spawn path passes `toolsets=None` on every call — the Hermes source says so
  explicitly in the comment beside the argument.
- `tools/delegate_tool_toolsets.py::_resolve_child_toolsets` then resolves the child as
  the parent's `enabled_toolsets` minus a small deny list (`delegate_task`, `clarify`,
  `memory`, `send_message`, `cronjob_manage`, plus the `delegation` and `kanban`
  composites).
- There is **no model-facing `toolsets` argument** on the `delegate_task` schema. A task
  cannot name its own toolset.

Two consequences that are easy to get wrong:

1. The **worker profile's own `config.yaml` does not constrain the child.** A profile
   routed to via `delegation.backends.profile_routes` binds its own model, credentials,
   skills and SOUL.md — but its `platform_toolsets` is not what the child runs with. The
   child runs with the *parent's* toolsets.
2. The only lever is the **parent's launch flags**. To give a worker a small context,
   start the parent with a narrow `-t` set:

   ```bash
   hermes chat -t delegation,file,terminal --query-file /tmp/<task>_brief.txt \
     --in <workdir> --run-budget 300 --max-turns 12 -Q --oneshot
   ```

   `delegation` must be in the set — without it the parent has no `delegate_task` tool
   and will improvise the work itself instead of dispatching.

## Pitfall: a parent without `delegation` silently does the work

Observed: a parent launched with a broad toolset but no `delegation` produced a plausible
answer that was **wrong** (`| ID | Name | Description |` where the real line was
`| ID | Skill Name | Trigger | Maturity | Invocation | Description |`). It never
dispatched, and the wrong answer was only caught by grepping the source file and
comparing character-for-character.

Rule: after any dispatch, compare the child's answer against the source line it claims
to quote. A child that answered a table header from memory will get the column names
wrong, and a plausible-looking wrong answer is the failure mode, not an exception.

## Probing what a child actually has

Decisive probe: ask the child to call one specific tool and report success/failure by
name.

```
goal: "Call your todo_list tool to create one todo item titled PROBE_TOOLSET and then
       reply with exactly TOOL_OK if the call succeeded, or TOOL_MISSING if the tool does
       not exist for you. Do nothing else."
```

Run it once with the parent toolset lacking the tool and once with it included. The
child's answer tracks the **parent's** flag, never the worker's profile — that is the
proof the inheritance rule holds.

## Measuring toolset cost without running a model

Schema bytes are the number that matters, and they are computable offline:

```python
import os, sys, json
os.environ.pop('PYTHONHOME', None); os.environ.pop('PYTHONPATH', None)
os.environ.pop('VIRTUAL_ENV', None)
sys.path.insert(0, '~/.hermes/hermes-agent')
sys._hermes_pin_default_home = True
import hermes_bootstrap
from tools.registry import registry
from toolsets import resolve_toolset

def schema_bytes(toolset_names):
    names = set()
    for t in toolset_names:
        names.update(resolve_toolset(t))
    out = [{'type': 'function', 'function': registry.get_schema(n)}
           for n in sorted(names) if registry.get_schema(n)]
    return len(json.dumps(out, separators=(',', ':'))), len(out)
```

Run it with the Hermes-bundled interpreter, not the system `python` — the bundled one
has the dependencies (`ruamel` and friends). A plain `python3 -c "import ..."` fails on
missing modules; that is an environment detail, not a rule.

`resolve_toolset` expands a toolset through its `includes` chain, so pass toolset
*names*, not tool names.

## Reading the real numbers back out of the session DB

Token accounting lives in the profile's `state.db`, not in the transcript:

- `sessions` — `input_tokens`, `output_tokens`, `cache_read_tokens`, `api_call_count`,
  `tool_call_count`, `system_prompt_hash`, `profile_name`, `parent_session_id`.
- `session_model_usage` — per-model breakdown plus `estimated_cost_usd`.
- `system_prompts` — the stored system prompt text, keyed by hash. Join
  `sessions.system_prompt_hash` to `system_prompts.hash`; the prompt is plain text
  (not JSON) and does **not** contain the tool schemas, so its length is only the
  instruction part of the payload.

Child sessions appear in the **parent's** `state.db` (the child runs in-process), with
`profile_name` set to the routed profile and `parent_session_id` pointing at the
dispatching session. Look there, not in the worker profile's own DB, or you will miss
every delegated run.

## Measured comparison (MiniMax-M2.7, one trivial read-and-report task)

Same task each time: read one markdown file and return one table header line.

| Configuration | tools | schema bytes | input | output | cache-read | wall |
|---|---|---|---|---|---|---|
| Worker profile run directly, default toolsets | 37 | 68,518 | 19,881 | 58 | 14,592 | 9s |
| Worker profile run directly, `-t file,terminal` | 6 | 9,710 | 13,143 | 56 | 8,448 | 13s |
| PM dispatches, parent default toolsets | 33 | 53,749 | 12,361 | 103 | 11,904 | 22.7s |
| PM dispatches, parent `-t delegation,file,terminal` | 6 | 9,710 | 11,927 | 63 | 6,400 | 22.9s |
| pi, `--tools read,grep,find` | 4 | 5,512 | 2,984 | 69 | 2,560 | 2.8s |

How to read it:

- **A dispatched child is already cheaper than the same profile run directly.** The
  child gets an ephemeral system prompt built for the goal (not the profile's full
  prompt), with context files and memory skipped. Instruction bytes for the child were
  ~10.5 KB against ~23 KB for the direct run.
- **Narrowing the parent's toolsets barely moves the child's token count** in the
  dispatched case (12,361 → 11,927, about 3.5%) while the schema payload drops 44 KB.
  Prompt caching absorbs most of the difference. The same narrowing on a *direct*
  profile run is worth ~34% of input tokens.
- **pi is still ~4x cheaper on input than the narrowest Hermes child.** The gap is not
  mostly tool schemas: pi ships tool descriptions as a few lines of text, Hermes ships
  full JSON schema, and pi's system message is shorter. Getting Hermes to pi's level
  would need a per-child toolset option and a text-only tool description format — core
  changes, not configuration.
- **Parent-side cost is separate.** The PM's own 2 API calls (~10–15k input) sit
  outside the child numbers. Pi has no parent-side cost at all, so compare like with
  like when quoting totals.

## The shape to use

1. Give the parent the narrowest toolset the work actually needs, plus `delegation`.
2. Put the work in a brief file; pass `--query-file`.
3. Keep `--run-budget` and `--max-turns` tight; these are cheap workers.
4. Verify the child's answer against the source, character-for-character when it quotes.
5. Reach for pi when the task is pure code reasoning on one or two files and needs no
   Hermes state; reach for a Hermes worker profile when the task touches skills,
   profiles, memory, kanban, git, or a relay.
