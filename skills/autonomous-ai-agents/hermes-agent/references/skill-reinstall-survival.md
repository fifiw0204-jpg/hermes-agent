# Making a skill survive a Hermes Agent reinstall

Use when the user asks "if I reinstall Hermes Agent, will my skill still be
there?" / "how do I make my skill come back after a reinstall?" / "why did my
skill disappear after reinstalling?".

The installed copy under `$HERMES_HOME/skills/` is **runtime state, not a
source**. A reinstall rebuilds that directory from a Git checkout, so the
question is never "is the file on disk" but "**is the file in a checkout the
installer will make**".

## The chain

```
source repo (Git)  ->  checkout the installer clones  ->  bundled sync  ->  $HERMES_HOME/skills/<cat>/<skill>/
```

- The bundled source of truth is the `skills/` tree **of the checkout**, not
  `$HERMES_HOME/skills`. `tools/skills_sync.py` discovers bundled skills from
  the checkout and copies them into `$HERMES_HOME/skills/`, recording a
  **directory** hash per skill in `~/.hermes/skills/.bundled_manifest`.
- `scripts/install.sh` performs the clone, then runs source completion /
  post-install maintenance, which is where `sync_skills()` runs.
- Therefore: **a skill that exists only in `$HERMES_HOME/skills/` is not
  reinstall-reproducible.** On the same host a reinstall may leave the file
  behind (the installer creates the skills dir rather than deleting it), but
  the manifest entry is dropped because the checkout no longer carries the
  skill, so it stops being tracked and stops receiving updates. On a fresh
  `HERMES_HOME` it is simply gone.

## Choosing the source a reinstall will use

The installer's source is controlled by the checkout it clones:

| Source | How the installer picks it | Result for a skill only on a branch |
|---|---|---|
| Upstream default branch | default install (`curl ... install.sh \| bash`) | absent unless merged upstream |
| Fork branch | `HERMES_REPO_URL=<fork-url> ... --branch <branch>` | present, pinned to that branch |
| Upstream release | official repo + default branch | follows released versions only |

Two installer facts decide this:

- The installer resolves a stable **release tag** only for the official
  upstream repo on the default branch. For a fork, or for any non-default
  branch, `stable_target()` returns empty and the installer clones the
  requested ref directly.
- `BRANCH` / `REPO_URL` in `scripts/install.sh` are the source of truth for
  "what will the next reinstall fetch". Changing them changes every future
  reinstall, so change them deliberately and say so.

**The durable fix is upstreaming.** A skill lives permanently in a reinstall
only once it is merged into the branch the installer clones by default. Until
then, a fork-branch install is a pinned, reproducible-but-frozen source.

## Two control planes — never mix them

- **Agent-level** (`REPO_URL`, `BRANCH`, `--branch` in `scripts/install.sh`)
  controls the whole Hermes checkout and therefore every bundled skill.
- **Skill-level** (`hermes skills install <owner>/<repo>/<path>`, taps,
  `skills.external_dirs`) controls one skill's own source.

They do not substitute for each other. A skill hub install cannot deliver a
skill that lives on a non-default branch: the GitHub skill source resolves
the repo's **default branch tree**, so the skill must be on the default
branch of that repo to be installable by identifier.

## Procedural checklist

1. **Establish the current source of truth.**
   ```bash
   cd ~/.hermes/hermes-agent
   git branch --show-current
   git remote -v
   git log --oneline origin/main..HEAD          # commits not upstream
   ```
2. **Confirm the checkout actually carries the skill**, not just the branch
   name. A stale local `origin/*` ref will make an upstream check lie:
   ```bash
   git ls-tree -r --name-only HEAD | grep 'skills/.*/<skill>'
   ```
   For an upstream/fork claim, verify against a fresh clone or the GitHub
   contents API rather than the local tracking ref.
3. **Check whether the skill is tracked as bundled.** If the installed
   directory hash differs from the manifest entry, the installed copy is
   classified **user-modified** — the sync keeps it and skips upstream
   versions for that skill forever. See `references/skill-change-provenance.md`.
4. **Decide the durability tier:**
   - merged upstream → survives any reinstall, keeps updating
   - fork branch + installer pinned to that branch → survives reinstalls,
     frozen until the branch is rebased
   - hub/external-dir install → survives reinstall only if re-installed; not
     part of the bundled sync
   - installed copy only → survives nothing; commit it first
5. **Before anything else, commit live-only content into a repo.** Content
   that exists only under `$HERMES_HOME/skills/` (curator patches, a
   hand-written skill) has no rebuild path. Copy it into the source repo and
   commit; then re-sync the installed copy from the repo.
6. **Re-join the update path** if the installed copy drifted: the bundled
   reset path (`hermes skills reset --help` for the flags) restores the
   checkout's copy and clears the user-modified mark.
7. **State what each future reinstall will produce** — which source, which
   branch, whether it is pinned, and what still has no rebuild path.

## Backup/restore is a different mechanism

`hermes backup` includes `$HERMES_HOME/skills` (the skills directory is not
in the excluded set), and `hermes import` restores it. That is **state
migration**: it moves today's bytes to a new install. It is not a versioned
update path — it carries no upstream history, does not rejoin the sync, and
does nothing about a skill that was never committed anywhere. Use it to
rescue live-only content; do not present it as the answer to "how do I keep
this skill across reinstalls".

## Pitfalls

- **"The file is still in `~/.hermes/skills/`" does not mean the reinstall
  kept it.** On a same-host reinstall the installer creates the skills
  directory rather than wiping it, so a leftover file can mask the fact that
  the checkout no longer carries the skill and the manifest entry is gone.
  Judge rebuildability by the checkout, not by the leftover file.
- **A local `origin/main` ref can be stale.** It is what `git log
  origin/main..HEAD` compares against; verify upstream claims with a fresh
  clone or the GitHub API, or the "not upstream" conclusion will be wrong.
- **A skill hub identifier cannot select a branch.** The GitHub skill source
  reads the repo's default branch tree, so "install it from my feature
  branch" is not a request the hub can satisfy.
- **"Reinstall" is ambiguous.** Same host vs fresh `HERMES_HOME` gives
  different answers; and pinning the installer to a fork branch changes what
  *every future* reinstall fetches, including upstream fixes.
- **Two competing copies of the same behaviour confuse the model.** If a
  framework-native skill and an external/source-repo copy of the same rules
  are both loadable, the model sees two mutually exclusive dispatch
  procedures. Pick one mechanism per task class: expose the source tree only
  for rules that have no native equivalent.
