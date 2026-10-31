# Where a skill change actually lives

Use when the user says a previous session changed a skill ("上一個 session 有更新"),
or asks whether a skill edit is real, shipped, or safe from an update wiping it.
A Hermes skill has up to **five** homes, and they drift apart silently.
Answer by checking all of them before claiming anything about the change.

## The five homes

| Home | Path | Holds | Survives |
|---|---|---|---|
| Installed copy | `$HERMES_HOME/skills/<category>/<skill>/` | what the loader reads **now** | until the next update overwrites it |
| Source repo | `~/.hermes/hermes-agent/skills/<category>/<skill>/` | the committed, upstreamable copy | as long as the branch/remote lives |
| Git branch | `git -C ~/.hermes/hermes-agent branch` | in-flight work | until the branch is deleted |
| Remote + PR | `git remote -v`, `gh pr list` | the shared, reviewable artifact | only after a PR is opened |
| Upstream rule source | another repo (e.g. a rule library the skill was ported from) | the rules the port is derived from | only in that repo |

The installed copy is the one that runs today. It is the one with **no version
control** — a curator patch or a `skill_manage` edit applied only there is
unversioned and gets clobbered by the next `hermes update`. So "the skill on
disk says X" and "X is protected" are different claims.

## Procedure

### 1. Diff installed copy against the source repo

```bash
diff -r ~/.hermes/skills/<category>/<skill> \
        ~/.hermes/hermes-agent/skills/<category>/<skill>
```

`<` lines are installed-only (uncommitted edits), `>` lines are repo-only
(committed but not synced to the install). Both directions matter:

- **Installed-only content** — an edit with no version control. Highest-value
  thing to recover: it is one update away from gone.
- **Repo-only content** — committed work the running agent is not using.

Compare `references/` and `scripts/` too, not just `SKILL.md`. An installed
skill often carries `references/` or `scripts/` the repo lacks, and a
SKILL.md-only diff hides that.

Do not use per-file md5/sha256 to compare the two — `.bundled_manifest` stores a
**skill-directory** hash (`tools.skills_sync.dir_hash`), so a per-file hash
never matches and will tell you a correct file is wrong.

Compare three hashes, not two: the installed copy, the source repo's working
tree, and the manifest entry. The manifest stores the *origin* hash from the
last sync.

```bash
cd ~/.hermes/hermes-agent && python3 -c "
import sys; sys.path.insert(0,'.')
from tools.skills_sync import dir_hash
from pathlib import Path
for p in ['~/.hermes/skills/<cat>/<skill>',
          '~/.hermes/hermes-agent/skills/<cat>/<skill>']:
    print(dir_hash(Path(p)))
"
grep '<skill>' ~/.hermes/skills/.bundled_manifest
```

Three readings:

- installed == repo == manifest — in sync, nothing pending.
- installed != repo, repo == manifest — the repo copy is what was synced; the
  installed copy has drifted (someone edited it in place).
- installed != repo == manifest, and upstream also changed — the installed copy
  is classified **user-modified**: the sync keeps it and skips the upstream
  version, so it never receives updates again. That is the failure mode to
  warn about: the fix is to commit the installed content into the repo, not
  to re-sync.

### 1b. Prove a commit is absent from a repo

To state that a commit exists in one repo and not another, check the object
store rather than searching trees — a tree search can miss it:

```bash
git -C <other-repo> cat-file -t <sha>   # "Not a valid object name" = absent
```

Cross-repo questions ("this commit is in the fork, is it also in the upstream
repo?") are the normal shape of a provenance question, and the answer is
always per-object, not per-branch.

### 2. Check the branch and remote state

```bash
cd ~/.hermes/hermes-agent
git branch --show-current
git log --oneline origin/main..HEAD          # commits not yet upstream
git rev-parse HEAD @{u}                      # local vs remote SHA, same = pushed
git rev-list --count HEAD..@{u}              # >0 = unpushed commits
gh pr list --repo <owner>/<repo> --state all
```

Three separate claims, often confused:

- **committed** — the change is in a commit
- **pushed** — the commit is on the remote (local and remote SHA equal)
- **submitted** — a PR exists that a reviewer can see

`gh pr list` returning nothing means the work was committed and pushed but
never submitted. That is the usual end state of a session that stopped at
"git push".

### 3. Recover content that was dropped from the installed copy

The curator keeps a content-addressed blob store of every version it wrote:

```
~/.hermes/.curator_backups/blobs/<sha256>
~/.hermes/skills/.curator_ledger.jsonl
```

Each blob is a full file; the ledger row records which skill and when it was
written. A wholesale rebuild that replaces a skill's `SKILL.md` leaves the
previous text only in the blob store — so rules that "vanished" during a
cleanup are usually still on disk.

```bash
grep -rl "<a distinctive phrase>" ~/.hermes/.curator_backups/blobs/
```

Read the matching blob and diff it against the live file. Whatever is in the
blob and not in the live file was lost — the fix is to re-apply it deliberately
(installed copy **and** repo), not to assume it was intentionally dropped.

### 4. Report the drift, then fix it in the right order

State the homes separately in the report. Then, for content that exists
only in the installed copy:

1. Copy it into the source repo (`skills/<category>/<skill>/`).
2. Commit on the working branch.
3. Push so the remote SHA matches.
4. Re-sync the installed copy from the repo.
5. Open the PR.

Skipping step 1–3 leaves the fix one `hermes update` from gone; skipping
step 4 leaves the agent running on content the repo does not describe.

When the skill is a **port** of a rule source in another repo, the port's
own rules are not the whole story: check the source repo for rules the port
never carried. Enumerate the source's rule files and mark each carried,
rewritten, or dropped — anything unaccounted for exists in exactly one place
and is lost the moment the source repo is deleted. The port repo owns the
branch; the source repo keeps a pointer, never a second copy of the body.

## Pitfalls

- **"The skill on disk says X" is not "X is committed."** The installed copy
  is unversioned runtime state; a curator edit there has no history and no
  backup outside the blob store.
- **A `skill_manage` patch lands in the installed copy, not the repo.** For a
  bundled skill that also exists in `~/.hermes/hermes-agent/skills/`, the
  patch must be mirrored into the repo or it never ships and never survives
  an update.
- **Comparing per-file hashes against `.bundled_manifest` always mismatches** —
  the manifest holds a directory hash. Use `tools.skills_sync.dir_hash`.
- **Diffing only `SKILL.md` hides `references/` and `scripts/` drift**, which
  is where most of the lost content lives.
- **`gh pr list` on the fork is not the upstream PR list.** Check both repos
  when the branch was pushed to a fork.
- **A blob-store hit proves the content existed, not that it was wanted.**
  Re-read it and decide with the user before re-applying — a rule dropped
  during an intentional cleanup should stay dropped.
- **The ledger's blob names are content hashes, not skill names.** Grep the
  blobs for a distinctive phrase rather than trying to map hash to skill.
- **A drifted installed copy silently opts out of future updates.** Once the
  sync classifies it as user-modified, upstream versions for that skill stop
  arriving — a stale skill that looks fine on disk. Commit the installed
  content into the repo to rejoin the update path.
- **The repo copy is not the branch copy.** A skill may be committed on a
  working branch that was never merged; diff against the branch's content
  (`git show <branch>:<path>`), not the working tree, when the question is
  "what did the session actually commit".
- **Two repos can hold the same skill legitimately.** A source library and a
  framework-native port are separate artifacts with different mechanisms and
  different names. Verify the direction of the port (which repo holds the
  mechanism, which holds the rules) before concluding one is a stale copy of
  the other.
