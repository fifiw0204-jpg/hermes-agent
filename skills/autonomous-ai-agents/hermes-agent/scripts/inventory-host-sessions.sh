#!/usr/bin/env bash
# Read-only inventory of host login sessions, editor servers and Hermes processes.
# Use before any session cleanup so you can tell the live session from stale ones.
set -u

echo "=== uptime ==="
uptime
who -b

echo
echo "=== who -a / w ==="
who -a
w -h

echo
echo "=== login sessions with client IP ==="
for p in $(ps -eo pid,args --no-headers | grep -E 'sshd-session|login --' | grep -v grep | awk '{print $1}'); do
  ip=$(tr '\0' '\n' < "/proc/$p/environ" 2>/dev/null | grep -E '^SSH_CLIENT=' | head -1)
  ps -o pid,ppid,user,etime,tty,args --no-headers -p "$p" | cut -c1-140
  echo "    ${ip:-<no SSH_CLIENT (console/local)>}"
done

echo
echo "=== editor servers (VS Code Remote) ==="
ps -eo pid,ppid,user,etime,args --no-headers | grep 'vscode-server' | grep -v grep | cut -c1-160 || echo "none"

echo
echo "=== editor server builds on disk ==="
for d in "$HOME"/.vscode-server/cli/servers/*/; do
  [ -d "$d" ] || continue
  n=$(basename "$d")
  echo "$n running=$(pgrep -af "servers/$n" 2>/dev/null | grep -vc 'bash -c') size=$(du -sh "$d" 2>/dev/null | cut -f1)"
done

echo
echo "=== hermes processes ==="
ps -eo pid,ppid,user,etime,args --no-headers | grep -iE 'hermes|gateway' | grep -v grep | cut -c1-140 || echo "none"

echo
echo "=== gateway unit + listener ==="
systemctl --user is-active hermes-gateway.service 2>/dev/null || echo "no hermes-gateway user unit"
ss -ltnp 2>/dev/null | grep -iE 'hermes|python' || echo "no hermes listener found"

echo
echo "=== this shell's ancestry (keep this subtree alive) ==="
p=$$
while [ "$p" != "1" ] && [ -n "$p" ]; do
  ps -o pid,ppid,user,etime,args --no-headers -p "$p" 2>/dev/null | cut -c1-140
  p=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')
done
