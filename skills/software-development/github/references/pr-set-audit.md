# Auditing a Repo's Whole Open PR Set

For the request "look at the PRs on this repo and say what each one is for".
The unit of analysis is the PR *set*, not one PR: a set can contain stacked
branches, two PRs editing the same file, branches that predate a landed
restructure, and PRs whose content already shipped by another route. Judge
each PR against the current base, then report the set as a whole with a
merge order.

## Procedure

### 1. Establish the ground truth first

```bash
gh pr list --repo OWNER/REPO --state all --limit 50 \
  --json number,title,state,headRefName,baseRefName,createdAt,mergedAt
gh issue list --repo OWNER/REPO --state all --limit 50 --json number,title,state
```

Check the issue tracker before promising an issue mapping. A repo whose
tracker is empty (or holds only unrelated closed items) has no per-PR
issues — infer each PR's problem domain from its body, commits and files,
and say plainly that the tracker holds no matching issue rather than
implying one exists.

### 2. Read each PR's actual content, not its title

Titles are often vague ("fix(skills): ..."); the body carries the problem
statement. When the body is a bare template (empty Verification checklist,
no prose), fall back to the commit subjects and the file list:

```bash
gh pr view N --repo OWNER/REPO --json body,baseRefName,headRefName,files
gh pr view N --repo OWNER/REPO --json commits --jq '[.commits[].messageHeadline]|join(" | ")'
gh pr diff N --repo OWNER/REPO --name-only
```

One PR body can be long; fetch bodies individually and print only the
fields you need, or the whole set drowns the transcript.

### 3. Classify each PR against the current base

Fetch the base and each head, then diff. The diff stat is the tell:

```bash
git fetch origin
git diff --stat origin/main origin/<branch> | tail -3
```

- **Net small, matches the PR title** — candidate to merge.
- **Thousands of deletions of files that still exist on `origin/main`** — the
  branch predates a landed restructure. Merging it reverts main's rewrite.
  Do not merge; report it as superseded and check whether its intent already
  shipped in another PR.
- **Only additions to paths main does not have** — the PR targets a path that
  was renamed or moved on main. It needs a rebase onto the new path before
  it can land, and it is still worth landing.

Confirm "already shipped" against main's history rather than assuming:

```bash
git log --oneline origin/main -- <path>
git show origin/main:<path> | grep -i <the value the PR introduced>
```

### 4. Detect stacking and sibling conflicts

```bash
gh pr view N --repo OWNER/REPO --json baseRefName,headRefName
git merge-base --is-ancestor origin/<A> origin/<B> && echo "B contains A"
```

- A PR whose base branch is another PR's head is **stacked**: merge the
  lower one first, and say which order.
- Two open PRs that touch the same file cannot both merge independently.
  Intersect their file lists and report the collision:

```bash
comm -12 <(gh pr diff A --repo OWNER/REPO --name-only | sort) \
         <(gh pr diff B --repo OWNER/REPO --name-only | sort)
```

Say which PR is the stronger implementation — the one whose change carries a
regression suite that fails on the old behaviour, not the one with the
cleaner diff — and what the other would need to drop or rebase onto. A
collision is not resolved by reporting it; the weaker PR's branch has to be
rewritten so it no longer claims the shared file. The procedure is in
`references/pr-workflow.md`, section "Narrowing or Splitting a PR Branch".

### 5. Flag scope pollution

Compare the title against the file list. A PR titled for one skill that also
edits two unrelated skills is two PRs wearing one title; merging it buries
the second change. Recommend splitting, and name which files belong where.
Splitting means the branch is rewritten into two branches with disjoint file
sets — each of which still has to pass the repo's own gate on its own.

### 6. Check CI honestly

```bash
gh pr view N --repo OWNER/REPO --json statusCheckRollup \
  --jq '[.statusCheckRollup[]|.name+":"+(.conclusion//.state)]|join(", ")'
```

An empty rollup means no CI is configured for that branch — report it as
"no checks reported", never as green.

## Reporting shape

Group by theme, not by number, so the reader sees which PRs are competing
for the same file. For each PR give: what problem it solves, what the
evidence for that reading is (body, commit subjects, files), and its status
(merge / rebase first / split / close).

Then give a merge order with reasons, and a short list of open decisions
that belong to the user. State what you did not check — reading PR metadata
is not running its test suite, and saying so keeps the report honest.

## Pitfalls

- **Reading the set PR by PR in isolation.** Stacked branches and
  same-file collisions only appear when you compare PRs against each other.
- **Trusting the title.** "fix(skills)" says nothing about which problem.
  The body and the commits say it; a templated body says nothing at all.
- **Merging on mergeability alone.** `mergeable=MERGEABLE` says the branches
  diverge cleanly, not that the PR is current with main's restructure.
- **Reporting a stale branch as mergeable.** A branch cut before a
  restructure is textually mergeable and semantically a revert.
- **Letting a huge diff stat pass without reading it.** A diff that deletes
  most of the tree is the signal that this PR is obsolete, not that it is
  large.
