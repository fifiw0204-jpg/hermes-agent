# Comparing worker costs: run a trivial probe, not a real task

To compare two worker harnesses (Hermes profile vs dispatched child vs pi vs a pi
bot), do NOT run the real work item. A real brief produces a long, drifting,
hard-to-attribute run, and its wall clock measures the worker's wandering rather
than its context overhead.

Use a **trivial read-and-report probe**: read one known file, return one exact
line from it. Then every number you collect is attributable and the run is
seconds long.

## The probe

```
Read /path/to/KNOWN_FILE and reply with ONLY the exact
markdown table header line you find at the top of the table (the row
starting with "| ID |"). Do not add any commentary. Do not read any other file.
```

The answer must be a line you can verify yourself by grepping the source, so a
wrong or hallucinated answer is detectable — a probe whose output you cannot
check tells you nothing.

## Run matrix

Same probe, one config per row, each run fresh:

| Row | Command |
|---|---|
| Hermes profile, default toolsets | `hermes chat --query-file <probe> --in <dir> --run-budget 240 --max-turns 12 -Q --oneshot` |
| Hermes profile, narrow | same + `-t file,terminal` |
| Hermes dispatched child, wide parent | same + no `-t`, brief asks for `delegate_task` with the profile |
| Hermes dispatched child, narrow parent | same + `-t delegation,file,terminal` |
| pi | `pi --provider <p> --model <m> --mode json --tools read,grep,find -p "$(cat <probe>)" --no-session` |
| pi bot | same + `PI_CODING_AGENT_DIR=<bot dir>` |

## Numbers to collect per row

- Wall clock (`time` around the command).
- Final answer text, checked character-for-character against the source line.
- Token accounting, from the profile's `state.db` (see below) for Hermes rows and
  from the `message_end` events' `message.usage` for pi rows.

## Where the numbers live

Hermes rows: the profile's `state.db` — `sessions.input_tokens`,
`output_tokens`, `cache_read_tokens`, `api_call_count`, `tool_call_count`. A
dispatched child's session row lives in the **parent's** `state.db` with
`profile_name` set to the routed profile and `parent_session_id` pointing at the
dispatching session.

pi rows: in `--mode json` output, accumulate `message.usage` from the events whose
`type` is `message_end` and whose `message.role` is `assistant`. Do not read
`usage` off `message_start` or `turn_end` — those carry zeroes.

## Offline schema bytes, no model call

Tool-schema bytes predict context cost and can be computed before running
anything. `resolve_toolset` expands through `includes`, so pass toolset *names*:

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

Run it with the Hermes-bundled interpreter, not the system `python` — the bundled
one has the dependencies (`ruamel` and friends). A plain `python3 -c "import
..."` fails on missing modules; that is an environment detail, not a rule.

## Reporting a comparison

Give a table with a row per configuration and columns for tools, schema bytes,
input/output/cache tokens, wall clock, and whether the answer was verified. Then
state which column decides the choice for the class of work, and where the
remaining gap comes from (schema format, system-prompt length, or parent-side
cost) — a bare "X is cheaper" is not actionable.

Say explicitly what was NOT measured: rows you did not run, and the parent-side
dispatch cost that sits outside the worker numbers. Comparing a pi run (no parent
cost) against a dispatched child (2 extra parent API calls) without saying so
misleads the reader.
