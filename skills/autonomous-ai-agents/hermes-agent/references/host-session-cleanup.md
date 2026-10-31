# Cleaning up stale host sessions (SSH, editor servers, consoles) on a Hermes host

Use when the user asks to clear old connections, drop stale logins, stop leftover
editor/agent servers, or "clean up the other sessions" on a box where Hermes
itself runs. This is process/session hygiene (RAM, PID sprawl, attack surface),
not disk hygiene — see `references/disk-space-reclamation.md` for the disk axis.

Read-only inventory first: `scripts/inventory-host-sessions.sh`.

## 1. Identify YOUR session before killing anything

Never infer "which connection is mine" from `who` output or from age — a stale
session can be newer than the live one. Walk the PID ancestry of the shell you
are running in and keep that whole subtree alive:

```bash
p=$$; while [ "$p" != "1" ] && [ -n "$p" ]; do
  ps -o pid,ppid,user,etime,args --no-headers -p "$p" | cut -c1-160
  p=$(ps -o ppid= -p "$p" | tr -d ' ')
done
```

Record the `sshd-session` PID that owns your terminal and the client IP from
that session's environment:

```bash
tr '\0' '\n' < /proc/<sshd-session-pid>/environ | grep -E 'SSH_CLIENT|SSH_CONNECTION'
```

Everything under that PID, plus the VS Code server build hash in its path, is
yours. Killing it severs your own session mid-task.

## 2. Map every session to an owner

`who -a` and `w` under-report SSH sessions that have no utmp entry (VS Code
Remote-SSH and `notty` sessions often appear only in `ps`). Enumerate
processes, then read `SSH_CLIENT` from each candidate's `/proc/<pid>/environ`
to tell the client IPs apart:

```bash
ps -eo pid,ppid,user,etime,tty,args --no-headers | grep -E 'sshd|vscode-server'
for p in <candidate-pids>; do
  echo "--- $p"; tr '\0' '\n' < /proc/$p/environ | grep -E 'SSH_CLIENT|SSH_CONNECTION'
done
```

Also list orphaned editor servers: a VS Code server whose parent died is
re-parented to PID 1 and stays resident, so it shows up as long-lived
`~/.vscode-server/cli/servers/Stable-<sha>/…` processes with no live SSH
session above them.

## 3. Kill in this order, re-checking between waves

1. The `sshd-session` privileged process (kills the transport and its
   `deploy@notty` child).
2. The client-side tree under it (bash / `sh` / editor command-shell).
3. Orphaned editor server processes from the dead sessions — these survive the
   sshd kill and must be signalled explicitly.
4. Root-owned console logins (see below).

Use `kill -TERM` first, check, then `kill -KILL` for what remains:

```bash
kill -TERM <pids>; sleep 2; ps -eo pid,args | grep <marker> | grep -v grep
kill -KILL <survivors>
```

**Expect a second wave.** Killing an editor server makes the client
auto-reconnect and respawn a fresh server tree under a NEW sshd session a few
seconds later. Re-run the inventory after the respawn and clear the new wave
too, otherwise the "cleanup" leaves the same footprint.

## 4. Root-owned console sessions

A login shell owned by root ignores plain `kill` from a non-root user, and
`kill -9` from a non-root user fails silently — no error, no death. Use
passwordless sudo and SIGHUP (the signal that ends a login session):

```bash
sudo -n kill -HUP <login-shell-pid>
```

Verify with `who` (the entry disappears) and not just with `ps` (the PID may
linger briefly as it reaps).

## 5. Do not run gateway verbs in the same command as kills

The runtime refuses commands that combine a gateway stop/restart verb with
process signalling, because the gateway would die before the command finishes
— and if that gateway is the one hosting your session, the command kills its
own shell. Keep them in separate calls, and prefer status-only checks:

```bash
systemctl --user is-active hermes-gateway.service   # separate call
```

Restart the gateway only from a shell outside the running gateway
(`hermes gateway restart`), never from inside it.

## 6. Filesystem deletes need their own consent step

Deleting leftover build directories (e.g. old `~/.vscode-server` server
builds) is a separate, irreversible action from killing processes. Issue it as
its own command so a consent timeout on the delete does not abort the process
cleanup that already succeeded, and do not re-attempt a blocked delete in a
reworded form.

## 7. Verify and report

After the cleanup, re-run the inventory and confirm the live session, the
gateway PID, and its listening port are all still up:

```bash
who; w -h
ps -eo pid,ppid,user,etime,args | grep sshd | grep -v grep
systemctl --user is-active hermes-gateway.service
ss -ltnp | grep <gateway-port>
```

Report in the closing message: what was killed, what was preserved and why,
what was left on disk, and that unsaved editor-side work in the killed
sessions is unrecoverable from the host.
