#!/usr/bin/env bash
# Report (and optionally reclaim) rebuildable disk space on a Hermes host.
#
#   bash scripts/reclaim-disk-space.sh          # report only, no deletion
#   bash scripts/reclaim-disk-space.sh --apply  # prune the rebuildable tier
#
# The --apply tier is limited to caches and stale tool-store versions:
# package caches, the uv cache, dead ~/.hermes/tools entries (via `hermes pm gc`),
# apt lists/debs, and /tmp scratch. It never touches state.db, sessions/,
# logs/, the agent source .git, backup archives, or home-dir user files.
set -uo pipefail

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
say() { printf '%s\n' "$*"; }

say "== disk usage =="
df -h / "$HOME" | sed 's/^/  /'

say ""
say "== rebuildable caches =="
for p in "$HOME/.cache/pip/http-v2" "$HOME/.npm/_cacache" "$HERMES_HOME/cache/uv" \
         /var/cache/apt/archives /var/lib/apt/lists /tmp; do
  [[ -e "$p" ]] || continue
  say "  $(du -sh "$p" 2>/dev/null | cut -f1)  $p"
done

say ""
say "== tool store (registered vs stale) =="
python3 - <<'EOF'
import json, os
home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
f = os.path.join(home, "tools", "facts.json")
tools = os.path.join(home, "tools")
if not os.path.isdir(tools):
    raise SystemExit
cur = set()
if os.path.exists(f):
    try:
        data = json.load(open(f))
        for v in data.get("packages", {}).values():
            if isinstance(v, dict) and v.get("entry"):
                cur.add(v["entry"])
    except Exception:
        pass
for e in sorted(os.listdir(tools)):
    print("  %-5s %s" % ("KEEP" if e in cur else "STALE", e))
EOF

say ""
say "== active venv (never delete) =="
for v in "$HERMES_HOME"/installs/*/environments/*/venv; do
  [[ -d "$v" ]] && say "  $v"
done

say ""
say "== editor servers: delete only versions with no live process =="
for d in "$HOME"/.vscode-server/cli/servers/*/; do
  [[ -d "$d" ]] || continue
  n=$(basename "$d")
  live=$(grep -l "servers/$n" /proc/[0-9]*/maps 2>/dev/null | head -1)
  say "  $(du -sh "$d" 2>/dev/null | cut -f1)  $n  live=${live:-no}"
done

if [[ $APPLY -eq 0 ]]; then
  say ""
  say "(report only — re-run with --apply to prune the rebuildable tier)"
  exit 0
fi

say ""
say "== applying =="
python3 -m pip cache purge 2>/dev/null | tail -2
command -v npm >/dev/null && npm cache clean --force >/dev/null 2>&1
[[ -d /var/cache/apt/archives ]] && rm -f /var/cache/apt/archives/*.deb
command -v hermes >/dev/null && hermes pm gc
UV=$(ls -d "$HERMES_HOME"/tools/uv-*-linux-arm64 2>/dev/null | sort -V | tail -1)
[[ -n "$UV" ]] && "$UV/uv" cache prune --cache-dir "$HERMES_HOME/cache/uv" --ci

say ""
say "== re-verify =="
hermes config check && say "  config OK"
hermes skills list | tail -n +1 | head -5
for v in "$HERMES_HOME"/installs/*/environments/*/venv/bin/python; do
  [[ -x "$v" ]] && "$v" -c "import hermes_cli; print('  venv OK')" 2>/dev/null
done
hermes chat -q "reply with one word: ok" >/dev/null 2>&1 \
  && say "  chat smoke test OK" || say "  chat smoke test FAILED"
df -h / "$HOME" | sed 's/^/  /'
