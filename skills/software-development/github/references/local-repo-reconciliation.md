# Reconciling a local repo with remote main

Class of task: a clone has drifted from `origin/main` — local `main` is behind,
local branches carry work that may or may not already be upstream, stale
worktrees and branches pile up. Goal: local `main` fast-forwarded to
`origin/main`, every unmerged local change preserved as one PR, no branch or
worktree deleted before its content is proven to be covered elsewhere.

This is the *state-reconciliation* companion to `references/pr-workflow.md`
(which covers making one change into one PR). Read both when a repo needs
cleaning up, not just a new PR.

## 0. Snapshot before touching anything

```bash
cd <repo>
git status -sb
git worktree list
git branch -vv | cat
git log --oneline origin/main..HEAD
git diff > /tmp/pre-align.patch      # uncommitted work, if any
md5sum /tmp/pre-align.patch
```

The patch file is the only thing standing between a mistaken `reset --hard`
and lost work. If the tree is clean, the patch file is empty and that is the
proof — not an assumption.

## 1. Inventory in ONE batched pass

A repo with a dozen candidate branches is one script, not a dozen turns. Do
the whole classification in a single call and print a table:

```bash
for b in $(git branch --format='%(refname:short)'); do
  echo "== $b"
  git cherry -v origin/main "$b" 2>/dev/null | head -20
done
```

Do not re-inspect the same branches in later turns — the point of the batch is
that it ends the inventory phase.

## 2. Classify each local commit by CONTENT, not by identity

`git cherry -v origin/main <branch>` prints `+` for commits with no
equivalent upstream patch and `-` for ones already upstream. That is a
patch-id comparison, and patch-id is fooled by a rebase that resolved
conflicts differently or by an upstream commit that bundled the same edit
with others. A `+` therefore means "not provably upstream", not "unique".

To decide, compare trees and blobs:

```bash
# whole-tree diff between the candidate commit and its suspected upstream twin
git diff --stat <candidate> <upstream-side-commit>

# per-file blob identity — the decisive check
git rev-parse <candidate>:<path>       # vs
git rev-parse <upstream-side>:<path>
```

A commit is **covered** only when the files it touches have identical blob
hashes on both sides. "Looks similar" is not coverage. Keep the comparison
script in scratch and reuse it for every candidate — hand-comparing a dozen
branches is where errors hide.

## 3. Move local main forward

```bash
git fetch origin
git checkout main
git merge --ff-only origin/main
```

`--ff-only` is the point: a diverged local `main` fails loudly instead of
silently creating a merge commit that nobody reviewed. Never `reset --hard`
a branch whose commits are not proven covered — step 2 comes first.

If the working tree still holds changes that are already on a PR branch,
`git restore --staged --worktree .` is safe *only after* confirming the same
files exist identically on that branch (step 2's blob check).

## 4. Land the surviving work as one branch

```bash
git worktree add .worktrees/<slug> -b fix/<slug> origin/main
```

Bring the work in with `git cherry-pick -n <sha>` (no commit) so each file
can be committed as its own logical change, then verify:

```bash
git diff --stat                      # against origin/main
```

If a cherry-pick overlaps edits already present, abort rather than force:

```bash
git cherry-pick --abort 2>/dev/null; git reset -q
git diff --quiet <candidate> <expected-side> && echo IDENTICAL
```

then re-apply the file content manually and commit it as its own change.

## 5. Open the PR

Use the repo's own gate script when it has one (it runs the changed skills'
suites, refuses a stale base, and refuses to push the default branch).
Otherwise `git push -u origin <branch>` + `gh pr create`. Merging stays a
human action when the repo's contract says so.

## 6. Prune only after the coverage proof

Delete order matters — a branch checked out in a worktree cannot be deleted
until the worktree is gone:

```bash
git worktree remove .worktrees/<slug>      # first
git branch -D <branch>                      # then, only if proven covered
```

Preconditions for every deletion:

- the branch has no open PR;
- every commit exclusive to it is covered by `origin/main` or by the PR
  branch, proven by blob comparison (step 2);
- the working tree it was checked out in has no uncommitted changes
  (`git status --porcelain` empty).

Keep one branch: the one the open PR is on.

## 7. Repoint anything that pointed into the removed tree

```bash
ls -l .git/hooks/
```

A git hook installed as a symlink into a worktree path breaks every future
commit once that worktree is removed. Repoint it at the canonical file in
the primary worktree (or wherever the repo's setup script says), and
re-verify the hook script parses:

```bash
bash -n .git/hooks/pre-commit && echo "syntax ok"
```

## Pitfalls

- **Deleting a branch because its commits "look upstream".** Patch-id and
  eyeballing are not proof; compare blob hashes per file, or the deleted
  commit's content is gone for good.
- **`reset --hard` / `checkout -f` before snapshotting.** Uncommitted work in
  a diverged tree is unrecoverable without the patch file from step 0.
- **Structural hooks that scan the whole tree.** A layout check that walks
  every tracked directory rejects commits on a repo whose *pre-existing*
  layout already violates the rule — a false positive that blocks all
  further work. Fix the check to compare against `HEAD`
  (`git ls-tree --name-only HEAD -- <path>`) so only directories introduced
  *by this commit* are rejected; do not rename existing directories to
  satisfy a stale allow-list, and do not bypass the hook with
  `--no-verify`.
- **Restoring the hook before the PR merges.** The fixed hook lives on the
  PR branch; the primary worktree's hook is the old one until the PR lands.
  Say so explicitly, and give the command that re-installs the hook after
  the merge.
- **Re-reading branches already inventoried.** Batch the inventory; a
  per-branch re-check burns the session budget that the actual change needs.
