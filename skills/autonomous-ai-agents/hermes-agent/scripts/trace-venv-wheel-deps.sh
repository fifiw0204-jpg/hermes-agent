#!/usr/bin/env bash
# Trace which installed distributions require the heavy ML wheels
# (torch / triton / nvidia-* / cuda-*), and whether a live consumer exists.
#
# Usage:  bash trace-venv-wheel-deps.sh [venv-python]
# Default: the venv pointed at by the newest Hermes install facts.json.
#
# Read-only. Prints the reverse dependency chain so a cleanup can decide
# between deleting a wheel and swapping it for a CPU-only build.
set -uo pipefail

PY="${1:-}"
if [[ -z "$PY" ]]; then
  PY=$(python3 - <<'EOF'
import glob, json, os
cands = glob.glob(os.path.expanduser("~/.hermes/installs/*/environments/*/venv/bin/python"))
print(sorted(cands)[-1] if cands else "")
EOF
)
fi
if [[ -z "$PY" || ! -x "$PY" ]]; then
  echo "no Hermes venv python found; pass one explicitly" >&2
  exit 1
fi
echo "venv python: $PY"
echo

echo "== reverse dependencies of the heavy wheels =="
"$PY" - <<'EOF'
import importlib.metadata as md
for d in sorted(md.distributions(), key=lambda x: (x.metadata["Name"] or "").lower()):
    try:
        reqs = d.requires or []
    except Exception:
        continue
    hits = [r for r in reqs if any(k in r.lower() for k in ("torch", "triton", "nvidia", "cuda-"))]
    if hits:
        print(f"{d.metadata['Name']} -> {hits}")
EOF

echo
echo "== sizes =="
SP=$("$PY" -c 'import sysconfig;print(sysconfig.get_paths()["purelib"])')
du -sh "$SP"/{nvidia,torch,triton,cuda} "$SP"/nvidia_* "$SP"/cuda_* 2>/dev/null | sort -h

echo
echo "== live consumers on this host =="
command -v whisper whisper-cli 2>/dev/null || echo "no whisper CLI on PATH"
ls -la "${HOME}/.cache/whisper" 2>/dev/null || echo "no ~/.cache/whisper (model never downloaded?)"
echo
echo "== uv.lock durability check =="
for L in "${HOME}"/.hermes/installs/*/environments/*/workspace/uv.lock; do
  [[ -e "$L" ]] || continue
  echo "-- $L"
  grep -n '^name = "torch"' -A8 "$L" | head -20
done
