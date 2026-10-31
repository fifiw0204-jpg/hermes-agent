#!/usr/bin/env bash
# Verify a Hermes install matches its native baseline.
# Usage: bash verify-native-state.sh
# Non-zero exit if any check fails.
set -uo pipefail

H="${HERMES_HOME:-$HOME/.hermes}"
REPO="$H/hermes-agent"
FAIL=0
ok(){ printf '  OK   %s\n' "$1"; }
bad(){ printf '  FAIL %s\n' "$1"; FAIL=1; }

echo "== installed vs repo skills =="
python3 - "$H" "$REPO" <<'PY'
import os, subprocess, sys
h, repo = sys.argv[1], sys.argv[2]
def names(root):
    out = subprocess.run(['find', root, '-name', 'SKILL.md'], capture_output=True, text=True).stdout.split()
    return {os.path.basename(os.path.dirname(p)) for p in out}
inst, rep = names(os.path.join(h, 'skills')), names(os.path.join(repo, 'skills'))
extra, missing = sorted(inst - rep), sorted(rep - inst)
print('  installed:', len(inst), ' repo:', len(rep))
print('  extra (non-native):', extra or 'none')
print('  missing vs repo:', missing or 'none')
sys.exit(1 if extra else 0)
PY
[ $? -eq 0 ] || bad "non-native skills present"

echo "== bundled_manifest dir_hash match =="
python3 - "$H" "$REPO" <<'PY'
import sys
sys.path.insert(0, sys.argv[2])
try:
    from tools.skills_sync import dir_hash
except Exception as e:
    print('  SKIP dir_hash unavailable:', e); sys.exit(0)
from pathlib import Path
inst = Path(sys.argv[1]) / 'skills'
man = {}
for line in (inst / '.bundled_manifest').read_text().split('\n'):
    if ':' in line:
        k, v = line.split(':', 1); man[k.strip()] = v.strip()
bad = []
for p in inst.rglob('SKILL.md'):
    d = p.parent
    if man.get(d.name) != dir_hash(d):
        bad.append(d.name)
print('  mismatched skills:', bad or 'none')
sys.exit(1 if bad else 0)
PY
[ $? -eq 0 ] || bad "bundled_manifest hash mismatch"

echo "== plugins =="
hermes plugins list --plain --no-bundled 2>&1 | sed 's/^/  /'

echo "== mcp =="
hermes mcp list 2>&1 | sed 's/^/  /'

echo "== config =="
hermes config check >/dev/null 2>&1 && ok "hermes config check exit 0" || bad "hermes config check"

echo "== curator =="
hermes curator status 2>&1 | grep -iE 'curator:|skill' | sed 's/^/  /'

echo "== cron =="
hermes cron list 2>&1 | tail -3 | sed 's/^/  /'

echo "== gateway =="
hermes gateway status 2>&1 | grep -E 'Main PID|Active:' | sed 's/^/  /'

echo "== conversation records =="
python3 - "$H" <<'PY'
import sqlite3, sys, os
db = os.path.join(sys.argv[1], 'state.db')
c = sqlite3.connect(db)
print('  sessions:', c.execute('select count(*) from sessions').fetchone()[0],
      ' messages:', c.execute('select count(*) from messages').fetchone()[0])
PY

if [ $FAIL -ne 0 ]; then echo "RESULT: FAILED"; exit 1; fi
echo "RESULT: OK"
