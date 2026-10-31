# Auditing and pruning a Hermes install to "native state"

Use when the user asks what's non-native in their Hermes install, asks to reset it to
shipped defaults, wants third-party skills/plugins/MCP removed, or wants leftover
artifacts pruned — **without** losing conversation history or the OS layer.

The deliverable is a *verified* inventory (native vs non-native) and then a
*verified* cleanup. Never delete first and report later.

## Standing rules

- **Back up before deleting**, always. Backups contain `.env` / `auth.json` /
  `config.yaml` secrets → `chmod 600` the tarballs, and never echo values in output.
- **Never delete conversation records.** `~/.hermes/state.db`, `~/.hermes/sessions/`,
  `~/.hermes/logs/` are the user's history; they survive every cleanup step.
- **Never delete the OS layer** (kernel, git, gh, system Python, SSH, editors) or
  Hermes-managed tooling (`~/.hermes/tools/*`, `~/.hermes/installs/*`) — those are
  native to the host, not to the agent.
- **Do not restart the gateway** unless the user asks or a config/plugin change
  must take effect there. The CLI re-reads config on every invocation, so
  verification still works with the gateway left running.
- Secrets → `[REDACTED]` in any output, diff, or summary.

## Step 1 — Inventory native vs non-native

Four diffs answer "what is not native":

```bash
# Skills: installed vs the repo's bundled set
find ~/.hermes/skills -name SKILL.md | sed 's#.*/skills/##'
find ~/.hermes/hermes-agent/skills -name SKILL.md | sed 's#.*/skills/##'

# Plugins: user-installed vs repo-bundled (repo ships its own plugins/ dir)
ls ~/.hermes/plugins/
ls ~/.hermes/hermes-agent/plugins/

# Config vs the shipped template
diff ~/.hermes/hermes-agent/cli-config.yaml.example ~/.hermes/config.yaml

# MCP servers and their binaries
hermes mcp list
```

Also inspect: `~/.hermes/.env` (variable names only), `~/.hermes/skills/.hub/`,
`~/.hermes/skills/.curator_ledger.jsonl`, `~/.hermes/.curator_backups/`,
`~/.hermes/skills/.usage.json`, `~/.hermes/backups/config/`, and any
`~/.local/bin/<tool>` that only existed to back an MCP server.

`hermes skills list` and `hermes plugins list --plain --no-bundled` are the
human-facing views; use them for the report, not as the identity source (see
pitfalls).

## Step 2 — Back up

```bash
TS=$(date +%Y%m%d-%H%M%S)
tar czf ~/hermes-native-backup-$TS.tar.gz \
  ~/.hermes/config.yaml ~/.hermes/.env ~/.hermes/skills ~/.hermes/plugins \
  ~/.hermes/memories ~/.hermes/kanban.db ~/.hermes/cron
chmod 600 ~/hermes-native-backup-$TS.tar.gz
tar tzf ~/hermes-native-backup-$TS.tar.gz | head     # verify it lists
```

Put anything outside `~/.hermes` (repo checkouts, bundles, `/tmp` copies, tool
binaries) into separate archives so the main one stays a clean restore point.

## Step 3 — Restore curator-modified bundled skills

Bundled skills live in two places: the repo (`~/.hermes/hermes-agent/skills/`) and
the installed copy (`~/.hermes/skills/`). The background curator can edit the
installed copy. Restore by **copying the whole directory**, not just `SKILL.md` —
an installed skill may carry extra `references/` and `scripts/` the repo lacks.

```bash
rm -rf ~/.hermes/skills/<category>/<skill>
cp -a ~/.hermes/hermes-agent/skills/<category>/<skill> ~/.hermes/skills/<category>/<skill>
```

Verify with `dir_hash` — the `.bundled_manifest` stores a **skill-directory**
hash, not a per-file hash, so a per-file sha256 comparison always mismatches:

```python
import sys; sys.path.insert(0, '~/.hermes/hermes-agent')
from tools.skills_sync import dir_hash
# manifest line format: "<skill-name>:<hash>"
```

A full pass compares every installed skill's `dir_hash` against
`~/.hermes/skills/.bundled_manifest` and reports the two diff sets both ways.

## Step 4 — Rebuild config.yaml from the shipped template

For a genuine reset, regenerate `config.yaml` from the repo's
`cli-config.yaml.example` rather than hand-pruning keys — hand-pruning leaves
stale sections behind. Then re-apply only the settings the user actually wants
(e.g. a non-default model/provider). Validate with `hermes config check`
(exit 0 = valid).

**Inventory MCP servers BEFORE the rebuild.** A wholesale regeneration drops
every user-added top-level section — including `mcp_servers` entries the user
wants to keep — because the shipped example only has them commented out. Run
`hermes mcp list` first, and for each server ask (or confirm from the user's
instructions) whether it survives the cleanup. If a server is kept, re-add its
block verbatim from the backup and restore its binary; verify with the stdio
probe in `references/native-mcp.md`.

Prefer `hermes config set KEY VAL` for the few non-default keys. Editing the file
directly is acceptable only inside a wholesale rebuild like this one, and only
when the file is regenerated from the shipped example first.

## Step 4b — Restoring something the cleanup removed

When the user reverses a deletion, restore from the pre-cleanup backup rather
than reconstructing from memory:

```bash
tar xzf ~/hermes-native-backup-<ts>.tar.gz -C /tmp/restore   # pick the archive that holds it
install -m 755 /tmp/restore/.local/bin/<tool> ~/.local/bin/<tool>
```

Then re-add the config block and re-verify end to end (binary runs, server
answers `tools/list`, `hermes mcp list` shows it enabled). State plainly that
the *running* agent process still holds the old registry — the newly added
server's tools appear only in a new session.

## Step 5 — Delete non-native artifacts

Order matters — config first, so nothing re-registers what you remove:

1. Remove the MCP section from `config.yaml` **and** delete its binary.
2. Delete non-native plugin directories under `~/.hermes/plugins/` and drop their
   `plugins.enabled` entries.
3. Delete non-native skill directories under `~/.hermes/skills/`.
4. Delete leftover clones/bundles/`/tmp` copies and stale `.env` blocks for
   removed projects (remove the whole commented block, not just the assignment).
5. Remove stale `~/.hermes/skills/.usage.json` entries for skills that no longer
   exist (keep plugin-scoped entries like `ponytail:ponytail` — plugin skills
   live outside `~/.hermes/skills` and a naive "does the dir exist" filter deletes
   them wrongly).
6. Prune the curator audit trail via its own API, not `rm`:

```python
from tools import skill_ledger as sl
# keep only rows for skills that still exist, then GC unreferenced blobs
sl.gc_blobs()   # returns (deleted, bytes_freed)
```

Raw-deleting the ledger leaves blobs orphaned; raw-deleting blobs breaks
rollback for rows that still reference them.

7. Old install environments: keep only the one `installs/<id>/facts.json`
   actually points at; the others are dead venvs (hundreds of MB each).
   `hermes pm gc` does this safely — see `references/disk-space-reclamation.md`.
8. Stale tool-store versions under `~/.hermes/tools/` (old `node-*`,
   `python-*`, `uv-*`, `fetch-<sha>` dirs left by earlier installs): run
   `hermes pm gc` instead of `rm` — it checks which entries `facts.json`
   registers and which venvs still symlink into them.

## Pitfalls

- **`.bundled_manifest` is a directory hash.** Use `tools.skills_sync.dir_hash`;
  comparing `SKILL.md` sha256/md5 never matches and you will "fix" a correct file.
- **`hermes skills list` truncates names with `…`** in the table, so grepping it
  for skill names silently misses entries (e.g. `document-to-action-ite…`).
  Derive identity from `find ~/.hermes/skills -name SKILL.md`, and use the CLI
  output only for the report.
- **Skill-count mismatch is often gating, not loss.** A skill whose frontmatter
  says `platforms: [macos]` never registers on Linux; one with
  `requires_toolsets: [kanban]` stays unregistered while that toolset is off.
  Before calling a skill "missing", check its frontmatter.
- **Restoring `SKILL.md` alone is not restoring a skill.** Copy the whole
  directory, or the installed copy keeps drifting from the repo.
- **Deleting a skill leaves residue in three places**: the ledger
  (`.curator_ledger.jsonl`), the blob store (`~/.hermes/.curator_backups/blobs`),
  and `.usage.json`. Clean all three or the agent still carries the deleted
  project's fingerprints.
- **Plugin-scoped skills live outside `~/.hermes/skills`** — a `.usage.json`
  cleanup keyed on directory existence will delete `ponytail:ponytail` and break
  the plugin's usage tracking.
- **Config/plugin changes need a gateway restart to reach the messaging
  platforms.** The CLI sees them immediately. If you skip the restart, say so
  explicitly rather than implying the change is live everywhere.
- **Backup archives contain credentials.** `chmod 600` them and keep them out of
  anything the agent will later echo.
- **A config rebuild is not a config edit.** Regenerating from
  `cli-config.yaml.example` silently removes every user-added section, so a
  server the user wanted is gone until it is restored — inventory MCP servers
  before rebuilding, not after.
- **Deleting a tool binary is not the same as removing the server.** The
  `mcp_servers` entry, the binary, and the `.env` key are three separate
  artifacts; a half-removed server shows up as "enabled" in `hermes mcp list`
  but fails on every call.

## Step 6 — Verify

```bash
hermes skills list                 # native skills only; explain any count gap by gating
hermes skills list | grep -c "pkb:"   # plugin/project skills gone (adjust the prefix)
hermes plugins list --plain --no-bundled
hermes mcp list                    # "No MCP servers configured"
hermes config check                # exit 0
hermes curator status              # "no curator-managed skills"
hermes cron list                   # job count unchanged
hermes gateway status              # still running, same PID
python3 -c "import sqlite3;c=sqlite3.connect('~/.hermes/state.db');\
print(c.execute('select count(*) from sessions').fetchone()[0],\
c.execute('select count(*) from messages').fetchone()[0])"
```

Or run the bundled probe:

```bash
bash scripts/verify-native-state.sh    # exits non-zero if any check fails
```

Report shape (keep this order; the user reads it as an audit):

1. **已刪除 / Removed** — grouped list of every deleted artifact, with paths.
2. **已還原／保留** — what was restored from the repo, and what was deliberately kept and why.
3. **驗證結果** — the command output block, plus a one-line explanation for any count gap (gating, not loss).
4. **備份** — absolute paths of the archives.

Mention anything you deliberately left alone (home-dir user files, credentials you
kept) as an explicit "left for you to decide" list rather than silently skipping it.

Report the inventory, what was deleted, what was deliberately kept, the count-gap
explanation, and the backup paths.
