# Reclaiming disk space on a Hermes host

Use when the user asks what can be deleted at the root/home level to free space,
or asks to shrink a Hermes install that has grown past its footprint. Distinct
from `references/environment-audit-and-pruning.md` (that one is about *what is
native*, this one is about *what is big and rebuildable*).

## Order of attack (biggest, safest, native-official first)

**Inventory, then act only on the unambiguous tier.** When the user asks "what
can be deleted at the root/home level", show the inventory with sizes and a
one-line safety verdict per item, then remove the unambiguously rebuildable
tier (package caches, stale tool versions, dead editor servers, tmp scratch)
and report it. Hold anything holding user data, credentials, conversation
history, or backups for explicit approval.

Once approved, work in this order:

1. **Stale tool-store versions — use `hermes pm gc`, never `rm`.**

```bash
hermes pm gc
```

The tool store (`~/.hermes/tools/`) keeps one directory per downloaded binary,
versioned (`node-26.7.0-…`, `python-3.14.7-…`, `uv-0.12.3-…`) plus
content-addressed archives (`fetch-<sha256>`). `~/.hermes/tools/facts.json` lists
what is currently registered; anything else is a leftover from an earlier
install. `hermes pm gc` cross-checks `facts.json` and the active
`installs/<id>/facts.json`, removes the unreferenced directories, and also
collects dead dependency generations and PM runtime generations.

Do **not** hand-delete `~/.hermes/tools/*` — an active venv symlinks into the
tool directory (`venv/bin/python -> ~/.hermes/tools/python-<ver>/bin/python3`),
and a stale `pyvenv.cfg` in `installs/<id>/pm-runtime/generations/*/` still
points at an old tool version.

Inspect before running:

```bash
python3 - <<'EOF'
import json, os
f = json.load(open(os.path.expanduser('~/.hermes/tools/facts.json')))
cur = {v.get('entry') for v in f['packages'].values()}
for e in sorted(os.listdir(os.path.expanduser('~/.hermes/tools'))):
    print('KEEP ' if e in cur else 'STALE', e)
EOF
```

2. **Build caches** — all rebuildable, none hold state:

```bash
~/.hermes/tools/uv-0.13.5-linux-arm64/uv cache prune --cache-dir ~/.hermes/cache/uv --ci
python3 -m pip cache purge
npm cache clean --force
sudo rm -rf /var/cache/apt/archives/*.deb
```

Use each cache's own purge command, not `rm -rf` on a subdirectory: pip's
cache spreads across `http-v2/`, `wheels/` and a top-level blob store, so
deleting only `http-v2` leaves most of the gigabytes behind. `pip cache purge`
reports what it removed (`Files removed: N (X MB)` / `Directories removed: N`) —
keep that line for the report, it is the receipt for the claimed reclaim.

`uv cache prune` without `--ci` leaves `archive-v0` mostly intact (~280 MB);
`--ci` drops it to ~12 KB. Verify the install still works afterwards:

```bash
~/.hermes/installs/*/environments/*/venv/bin/python -c "import hermes_cli; print('venv OK')"
```

3. **Editor/IDE servers.** `.vscode-server/cli/servers/Stable-<sha>/` holds one
   full server per VS Code client version (~600 MB each). Check which are live
   before deleting:

```bash
for d in ~/.vscode-server/cli/servers/*/; do
  n=$(basename "$d"); echo "$n running=$(pgrep -af "servers/$n" | grep -vc 'bash -c') size=$(du -sh "$d" | cut -f1)"
done
```

Delete only versions with no live process. A version listed in
`cli/servers/lru.json` is still the client's cached fallback and will simply
be re-downloaded on next connect.

   `pgrep` under-reports: a server can be live with no matching command line.
   Prove liveness the hard way — a mapped path in a running process means the
   files are in use right now:

```bash
grep -l "servers/Stable-<sha>" /proc/[0-9]*/maps 2>/dev/null
```

   The same probe decides whether a big directory is deletable at all. Before
   deleting anything under `~/.hermes/installs/*/environments/*/venv`, check
   whether the running agent has that venv mapped:

```bash
grep -o "/home/[^ ]*/environments/[^ ]*venv[^ ]*" /proc/$(pgrep -f "gateway run" | head -1)/maps | sort -u
```

   A venv whose `site-packages` appears in the live process's maps is the
   running interpreter's environment — deleting it breaks the agent that is
   answering you, and the size of the directory is irrelevant to that.

4. **GPU wheels in a CPU-only venv — the largest single dead weight on a
   small VPS.** A shared venv often carries `nvidia-*`, `torch` and `triton`
   pulled in by an optional ML dependency (voice cloning, TTS, diffusion).
   On a host with no GPU those wheels are never executed but still occupy
   gigabytes:

```bash
ls /dev/nvidia* 2>/dev/null || echo "no GPU device nodes"
du -sh ~/.hermes/installs/*/environments/*/venv/lib/python*/site-packages/{nvidia,torch,triton} 2>/dev/null
```

   **Do not treat "no GPU on this host" as "the wheels are deletable".** The
   wheels are dead *weight*, but they may be a live *dependency*: on a
   CPU-only host the CUDA wheels are never executed, yet `torch` itself is
   what a CPU-only ML tool imports. Trace the chain before touching anything:

```bash
# who requires torch / triton / nvidia-*, from installed metadata
~/.hermes/installs/*/environments/*/venv/bin/python - <<'EOF'
import importlib.metadata as md
for d in md.distributions():
    hits = [r for r in (d.requires or []) if any(k in r.lower() for k in ("torch","triton","nvidia"))]
    if hits:
        print(d.metadata["Name"], "->", hits)
EOF

# does a live consumer exist?  (CLI probe + skill gates + model cache)
which whisper                      # a venv/bin/<tool> on PATH means the skill gate passes
ls ~/.cache/whisper/               # a downloaded model means it actually ran
grep -rn "import torch" <skills-root>
```

   Then choose between two shapes — **deletion** only when no consumer exists,
   otherwise a **CPU-build swap**:

   - *Deletion* (nothing imports it): remove the wheel directories and the
     owning package; the consuming skill then needs a reinstall on a machine
     with a GPU.
   - *CPU-build swap* (a consumer exists): install the CPU-only wheel from the
     vendor index (`download.pytorch.org/whl/cpu` publishes `+cpu` builds for
     `linux_aarch64` — check the exact cpXY tag matches the venv's Python),
     then uninstall the CUDA packages (`nvidia-*`, `triton`, `cuda-toolkit`,
     `cuda-bindings`). Net reclaim is slightly smaller than the raw wheel
     size, because the CPU wheel stays resident, but every consumer keeps
     working.

   Do not delete `torch`/`nvidia` while a skill that imports them is in use:
   the failure appears as a late ImportError, not at cleanup time.

   **The venv is uv-managed — check `uv.lock` before promising durability.**
   The environment's `uv.lock` (under the install's `workspace/`) records the
   CUDA wheels as resolved dependencies of `torch`, so a Hermes env repair or
   `uv sync --locked` re-installs everything you deleted. Check it:

```bash
grep -n "^name = \"torch\"" -A8 ~/.hermes/installs/*/environments/*/workspace/uv.lock
```

   A local deletion is therefore a temporary reclaim unless the upstream
   `pyproject.toml` extra stops pulling the CUDA build; say so explicitly
   instead of presenting the reclaim as permanent.

5. **Per-profile duplicated caches.** Every profile keeps its own copy of
   large read-only caches (`models_dev_cache.json` is several MB per
   profile). If the profiles share a filesystem, replace the copies with
   symlinks to one canonical file:

```bash
for p in ~/.hermes/profiles/*/; do
  f="$p/models_dev_cache.json"
  [ -f "$f" ] && [ ! -L "$f" ] && ln -sf "$(readlink -f "$f")" "$f.tmp" && mv "$f.tmp" "$f"
done
```

   Verify the running profile still resolves it (`hermes model list`) before
   replacing the last original copy.

6. **System logs and package lists** (root-owned):

```bash
sudo rm -rf /var/lib/apt/lists/*        # apt update re-fetches
sudo journalctl --vacuum-time=7d
```

`/var/log/journal` under ~50 MB usually has nothing to vacuum.

7. **Your own scratch dirs.** `/tmp` on many hosts is a tmpfs (RAM), so clearing
it frees memory, not disk — check `df -h /tmp` first. Hermes keeps its own
scratch under `~/.hermes/cache/scratch/`; do not delete that while the agent is
running.

## "Can this host host one more thing?" — the capacity question

A request like "can I install/run <another OS or service> here" is a capacity
verdict, not a cleanup job. Answer it from three probes in one batch, then
state the binding constraint:

```bash
df -h / ; free -h ; nproc
ls -l /dev/kvm 2>/dev/null || echo "no KVM"   # nested virtualisation?
command -v docker podman lxc qemu-system-x86_64
```

The shapes, in order of cost:

- **In-place, no money** — a container/rootfs on the same host. Costs disk and
  RAM out of the *current* budget; nothing is billed.
- **In-place virtual machine** — only if `/dev/kvm` exists. Without it, QEMU
  falls back to software emulation and is unusably slow, and the RAM and disk
  cost is the real blocker.
- **Separate cloud instance** — a new bill (a new server's plan plus its own
  IPv4), and its own disk budget, so it does not compete with the host's
  free space.

Report RAM and swap next to disk in every capacity answer: on a small VPS the
memory headroom, not the disk, decides whether the second workload fits. Say
which shape costs money and where the money lands, in the same breath as the
feasibility verdict.

## Loose files at the home root

A cluttered home root is usually not a size problem but an ownership one.
Triage each loose file by what it is, not by its name:

- **Backup tarballs** (e.g. `hermes-native-backup-*.tar.gz`) — move them into
  a single `~/backups/` (or off-host) directory rather than leaving them in the
  root; they contain credentials, so keep them `chmod 600` and ask before
  deleting or moving anything the user may still need to restore from.
- **Setup scripts and SSH config snippets** for a *client* machine (bootstrap
  scripts, `ssh_config` snippets) — they belong in a project or dotfiles
  directory (`~/Projects/`, `~/dotfiles/`), not in the root. Moving them is a
  relocation, not a deletion.
- **One-off analysis notes** — move next to the project they describe.
- **Empty leftover dirs** — safe to remove.
- **Zero-byte marker files** — verify nothing reads them, then remove.

Never propose deleting a loose file the user authored without first checking
whether a script, README, or skill references it by name (`grep -rn "filename" ~/`).

## When the user approves one item, execute it — do not re-derive the inventory

An audit answer is not a licence to keep auditing. When the user picks one line
from the reclaim list ("do this one first"), switch to execution mode: run the
item's commands, verify the affected surface still works, report bytes
reclaimed and anything you skipped. Re-running the whole `du` sweep and
re-litigating the other items burns the tool budget and leaves the approved
step undone.

Budget the probes for the execution itself:

- **One command for the change** (install/uninstall/delete), not a per-package
  loop that re-derives the list.
- **One verification** of the consumer that justified keeping it (`which
  whisper`, `hermes chat -q`, `venv/bin/python -c "import <pkg>"`).
- **One size check** afterwards (`df -h /`) to report the real reclaim.
- Reserve the deep dependency trace for the items where a wrong delete breaks
  a skill — not for every package in the tree.

If the trace reveals the approved plan is wrong (e.g. the wheels are a live
dependency, not dead weight), say so in one line, present the corrected shape
as a two-option choice with a recommendation, and stop — do not silently
substitute a different plan for the one the user approved.

**Report the measured reclaim, never the estimate.** `df -h /` before and after
is the only honest number: directory sizes double-count hardlinks, sparse
files and files still held open by a running process, so a sum of `du` sizes
predicts a reclaim the filesystem will not deliver. If the measured number is
smaller than the estimate, say so plainly and name what blocked the rest
(a directory still mapped by a live process) instead of restating the
estimate as if it happened.

**Disk is not memory.** Reclaiming gigabytes of disk does nothing for a
host whose RAM is the constraint. When the user's real question is "can this
host run another thing", check `free -h`, `nproc` and the swap usage alongside
`df` and report the binding constraint by name — a cleanup that leaves the
real bottleneck untouched has not answered the question.

## Report shape for an audit-and-advise request

When the user asks to "盤一下" (inventory) and give suggestions, the deliverable
is a ranked reclaim list, not a directory tour:

- Lead with the disk headline (filesystem size, used %, biggest three consumers).
- Then a numbered list ordered by **bytes recoverable**, each item carrying the
  exact command, the expected reclaim, and one clause on what could break.
- Close with the single biggest safe win and the checks that must run before
  the riskier items.
- State plainly that nothing was deleted when the request was read-only.

Keep the probe count bounded: batch the `du` calls (one call per level, not one
per directory) and stop descending once the top consumers are identified. A
deep dive into a multi-GB tree burns the tool budget that should go to
verifying the verdicts.

## What NOT to delete

- `~/.hermes/hermes-agent/.git` (~260 MB) — the agent source's git history;
  `hermes update` depends on it.
- `~/.hermes/tools/` entries listed in `facts.json` — current binaries.
- `~/.hermes/state.db`, `~/.hermes/sessions/`, `~/.hermes/logs/` — conversation
  history.
- `~/.hermes/installs/*/environments/<active-id>/` — the venv
  `facts.json` points at. Delete only the *other* environment ids.
- Backup tarballs — ask first; they contain credentials.

## Re-verify after every step

`hermes pm gc` and cache prunes can flip a gated skill back on or off. After
reclaiming space, re-run the native inventory:

```bash
hermes status
hermes skills list          # count can legitimately change
hermes plugins list --plain --no-bundled
hermes mcp list
hermes config check
hermes chat -q "reply with one word: ok"   # end-to-end smoke test
```

A skill count that *increases* after `hermes pm gc` is not a regression: gc
removed a dead PM runtime generation, so a toolset-gated skill
(`requires_toolsets: [kanban]`) re-registered. Check frontmatter before
calling any count change a bug.
