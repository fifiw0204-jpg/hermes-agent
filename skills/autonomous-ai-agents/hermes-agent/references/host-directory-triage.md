# Triaging suspicious directories before pruning them

Use when the user points at one or more directories (usually in `$HOME`) and asks
whether they are stray, redundant or out of place — "these don't belong here",
"盤查一下", "why are these here?". Distinct from the process axis
(`references/host-session-cleanup.md`), the size axis
(`references/disk-space-reclamation.md`) and the native/non-native axis
(`references/environment-audit-and-pruning.md`). This one is about **ownership
and liveness of a directory**.

Default posture is read-only. The deliverable is one verdict per directory with
the evidence that produced it — the user decides what gets removed.

## 1. Never judge a directory by its name, age or size

Ask three questions per directory, in this order:

1. Does anything **point into it** (symlink, config path, script constant)?
2. Is it **registered** in some tool's own registry (git worktree, venv,
   npm link, systemd unit)?
3. Is its content **already delivered somewhere else** (a card attachment, a
   canonical repo copy)?

A directory that fails none of these is a candidate for removal. A directory
that fails any of them is not garbage, however odd it looks.

## 2. The symlink sweep — the usual hidden dependency

Skill directories are frequently symlinks into a checkout or a worktree, so the
"obviously stray" directory may in fact be the live install path:

```bash
for d in ~/.hermes/skills/*/ ~/.hermes/profiles/*/skills/*/ ~/.local/bin/*; do
  [ -L "$d" ] && printf '%s -> %s\n' "$d" "$(readlink -f "$d")"
done
```

If a symlink resolves into a directory you were about to call redundant, that
directory is live. Deleting it leaves a dangling symlink and the skill simply
stops loading — no error anyone will notice until a task fails.

## 3. Git worktrees are not loose directories

```bash
git -C <main-repo> worktree list        # every registered worktree, wherever it lives
git -C <worktree> status --porcelain    # empty = no uncommitted work
```

Remove with `git worktree remove <path>` — never `rm -rf`: that leaves stale
metadata under `<repo>/.git/worktrees/` and the path stays registered.

To decide whether a worktree's content is already in the canonical branch,
compare trees rather than commit ids:

```bash
git -C <main-repo> log --oneline <canonical-branch>..<worktree-branch>
diff -rq <main-repo>/<path> <worktree>/<path>
```

Commits that appear under **different SHAs** in the canonical branch were
cherry-picked or rebased — the content is merged even though the SHAs differ.
An empty `diff -rq` plus a clean status is the real "duplicate" test.

## 4. "Already delivered elsewhere" check

One-off audit and report outputs are usually copied onto the card that produced
them: `~/.hermes/kanban/attachments/<card-id>/`. If the deliverable is there,
the home-directory copy is a duplicate — but compare size/line count before
recommending deletion, and confirm the copy is the newer one.

## 5. Scratch work directories pinned by hardcoded paths

If a script inside a scratch directory embeds its own absolute path, the
directory cannot be relocated without editing every script — relocation is a
code change, not a cleanup step. Report it as a decision for the user
(keep it, or move it together with a path rewrite), never as a plain delete.

Absence of that path from the skill bodies does **not** mean the directory is
orphaned: worker profiles run with their own cwd and write into it, and their
own scratch/cache dirs reference it.

## 6. Verdict vocabulary — one per directory

- **LIVE** — something points at it, or it holds the only copy → keep.
- **REDUNDANT** — a duplicate whose consumer can be repointed. Give the exact
  repoint command, the exact removal command, and the order (repoint → verify →
  remove). Never hand over a bare delete for a REDUNDANT verdict: removing
  first breaks the consumer.
- **ORPHAN** — no consumer, no duplicate, no hardcoded reference → deletable.
- **DECISION NEEDED** — the outcome depends on a choice only the user can make
  (e.g. where a working directory should live from now on).

## 7. Time-boxed audits

When the user sets a limit ("限時3分鐘"), lead with the verdict table and the
deciding evidence, then the supporting detail. Do not spend the budget
re-deriving facts already established earlier in the same session, and state
plainly what you did not check.
