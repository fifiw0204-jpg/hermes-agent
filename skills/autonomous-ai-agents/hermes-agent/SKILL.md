---
name: hermes-agent
description: "Use, configure, theme, extend, and orchestrate Hermes Agent."
version: 3.2.0
author: Hermes Agent + Teknium
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, setup, configuration, multi-agent, spawning, cli, gateway, bots, bot-mode, features, themes, skins, desktop-plugins, tui-widgets, petdex, development]
    homepage: https://github.com/NousResearch/hermes-agent
    related_skills: [claude-code, codex, opencode]
---

# Hermes Agent

Hermes Agent is an open-source AI agent framework by Nous Research that runs in your terminal, a native desktop app, messaging platforms, and IDEs. It's in the same category as Claude Code (Anthropic), Codex (OpenAI), and OpenClaw — autonomous coding and task-execution agents that use tool calling to interact with your system. Hermes works with any LLM provider (OpenRouter, Anthropic, OpenAI, Google, DeepSeek, xAI, local models, and 20+ others) and runs on Linux, macOS, Windows, and WSL.

What makes Hermes different:

- **Self-improving through skills** — Hermes learns from experience by saving reusable procedures as skills that load into future sessions.
- **Persistent memory across sessions** — remembers who you are, your preferences, environment details, and lessons learned. Pluggable memory backends.
- **Multi-platform gateway** — the same agent runs on Telegram, Discord, Slack, WhatsApp, iMessage, Signal, Matrix, Teams, Email, and a dozen more platforms with full tool access, not just chat.
- **Many surfaces** — the same agent core drives the CLI, the Ink TUI, a native Electron desktop app, a web dashboard, and an ACP server for IDEs (VS Code / Zed / JetBrains).
- **Provider-agnostic** — swap models and providers mid-workflow; credential pools rotate across multiple API keys automatically.
- **Profiles** — run multiple independent Hermes instances with isolated configs, sessions, skills, and memory.
- **Extensible & themeable** — plugins, MCP servers, custom tools, webhook triggers, cron scheduling, skins that theme every surface, desktop UI plugins, TUI widgets, and pet mascots.

**This skill is a hub.** The body covers identity, quick start, spawning/orchestration, and hard invariants. Everything else lives in reference files — **load the matching reference (below) before answering**; do not answer detail questions from the body alone.

**Docs:** https://hermes-agent.nousresearch.com/docs/

## Scope & Verification

This skill is a concise operating guide, not the complete source of truth for every Hermes feature. If a Hermes feature, command, or setting is not mentioned here or in a reference, do not treat that absence as evidence that it does not exist. Check the live repository and official docs before giving a negative answer.

Good verification targets, cheapest first:

- **Every shipped feature, one line each: https://hermes-agent.nousresearch.com/docs/llms.txt.** Start here for any "can Hermes do X?" or "how do I do X?" — it indexes the entire documentation set with a link to the page that answers. It is generated from the docs tree on every build, so it is never behind the product. Fetch it with `web_extract`, or `curl -s https://hermes-agent.nousresearch.com/docs/llms.txt` when web tools are off. The whole documentation set in one file is at `/docs/llms-full.txt`.
- CLI commands: `hermes --help`, `hermes <command> --help`, and `hermes_cli/main.py`
- Source tree: https://github.com/NousResearch/hermes-agent

Never answer "Hermes can't do that" from memory. Hermes ships far more than this skill body describes, and the index exists so a negative answer is always checkable.

## Quick Start

```bash
# Install (shell installer — bootstraps PM, Python, dependencies, and the launcher)
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# Interactive chat (default surface; set display.interface: tui to launch the Ink TUI instead)
hermes

# Single query
hermes chat -q "What is the capital of France?"

# Setup wizard  /  pick model+provider  /  health check
hermes setup
hermes model
hermes doctor

# Other surfaces
hermes desktop                 # launch the native desktop app (alias: hermes gui)
hermes dashboard               # web admin panel + embedded chat
hermes proxy                   # OpenAI-compatible local proxy backed by your OAuth provider
```

## Key Paths

```
~/.hermes/config.yaml       Main configuration (settings — never secrets)
~/.hermes/.env              API keys and secrets ONLY (under $HERMES_HOME if set)
$HERMES_HOME/skills/        Installed skills
~/.hermes/skins/            Custom themes (see references/themes.md)
~/.hermes/desktop-plugins/  Desktop app UI plugins (see references/desktop-plugins.md)
~/.hermes/tui-widgets/      TUI widget apps (see references/tui-widgets.md)
~/.hermes/pets/             Installed pet mascots (see references/petdex.md)
~/.hermes/state.db          Canonical session store (SQLite + FTS5)
~/.hermes/sessions/         Gateway routing index, request dumps, *.jsonl transcripts
~/.hermes/logs/             Gateway and error logs
~/.hermes/auth.json         OAuth tokens and credential pools
~/.hermes/hermes-agent/     Source code (if git-installed)
```

Profiles use `~/.hermes/profiles/<name>/` with the same layout. When a profile is active, resolve the real home from `$HERMES_HOME` — never hardcode `~/.hermes`.

## Routing Table — load the reference for the task

| User wants... | Load |
|---|---|
| **Anything not listed below — "can Hermes do X?", "how do I set up X?"** | **https://hermes-agent.nousresearch.com/docs/llms.txt** |
| Bots that chat, run routines, or message each other; the Bots tab | docs: `/user-guide/bot-mode` |
| A dedicated bot with its own persona/voice and its own skill set (SOUL.md + scoped skills + own credentials/cron), or how many bots to split one skill family into | `references/bot-profiles-and-persona.md` |
| CLI commands, subcommands, flags, "how do I run X" | `references/cli-reference.md` |
| In-session slash commands | `references/slash-commands.md` |
| Provider setup, API keys, OAuth | `references/providers-and-models.md` |
| config.yaml sections, toolsets, voice/STT/TTS | `references/configuration.md` |
| AGENTS.md / .hermes.md / CLAUDE.md project rules | `references/project-context-files.md` |
| Secret redaction, PII, approval modes, "reset permissions" | `references/security-privacy.md` |
| Delegation, cron, curator, kanban | `references/background-systems.md` |
| Auditing what is non-native in an install; resetting to shipped defaults; pruning leftovers | `references/environment-audit-and-pruning.md` (+ `scripts/verify-native-state.sh`) |
| "What actually happened in that session?" — reconstructing a past session's real state (artifacts, commits, current numbers) instead of quoting its self-report | `references/session-state-reconstruction.md` |
| "Where did that skill change go?" — installed copy vs source repo vs branch vs PR; recovering text dropped from the installed copy | `references/skill-change-provenance.md` |
| "Will my skill survive a reinstall?" — what a fresh install rebuilds from, which source/branch to pin, why a live-only skill is not rebuildable | `references/skill-reinstall-survival.md` |
| "Is this skills repo a mess?" — auditing a skills tree for loadability, index drift, overlap, and naming hygiene | skill `skill-tree-audit` |
| Freeing disk space on the host; stale tool versions, build caches, old editor servers; "can this host host one more workload?" capacity verdict | `references/disk-space-reclamation.md` (+ `scripts/reclaim-disk-space.sh`, `scripts/trace-venv-wheel-deps.sh`) |
| Clearing stale host logins/connections: old SSH sessions, orphaned editor servers, root console logins | `references/host-session-cleanup.md` (+ `scripts/inventory-host-sessions.sh`) |
| "These directories don't belong here" — triaging stray home/repo dirs for liveness, redundancy, ownership | `references/host-directory-triage.md` |
| MCP servers (add, catalog, `hermes mcp`) | `references/native-mcp.md` |
| Webhook routes and event-driven runs | `references/webhooks.md` |
| A custom theme/skin ("synthwave theme", "change the gold ●") | `references/themes.md` + `templates/skin.yaml` |
| A desktop app UI element (pane, widget, ⌘K command, page) | `references/desktop-plugins.md` + `templates/plugin.js` |
| A live TUI panel or modal widget (ticker, clock, dashboard) | `references/tui-widgets.md` + `templates/clock.mjs` |
| Pet mascots — install, select, scale, diagnose | `references/petdex.md` |
| Windows-specific issues (keybinds, WinError 10106, BOM) | `references/windows-quirks.md` |
| Debugging: voice, tools missing, gateway, aux models | `references/troubleshooting.md` |
| Contributing code: adding tools, slash commands, tests | `references/contributor-guide.md` |
| delegate_task "capped at N" reports | `references/delegate-task-concurrency-diagnosis.md` |
| "Can app X use my Nous Portal subscription/OAuth?" | `references/portal-auth-for-third-party-apps.md` |
| Connecting a messaging platform (Telegram, Discord, Slack, WhatsApp, …) | docs: `/user-guide/messaging` |

The reference list above is not the feature list — it is the set of topics that
need more than their docs page. For everything else Hermes ships, fetch
`llms.txt` and it maps the question to the page that answers it.

Two theming rules that hold even without loading the reference: **you apply skins yourself** (`hermes config set display.skin <name>` — every surface repaints live within ~a second; don't tell the user to run `/skin`), and **to tweak one color, edit the ACTIVE skin** (`hermes skin set <key> <hex>`) — never fork `default`, which drops the palette and resets the background.

## Spawning Additional Hermes Instances

Run additional Hermes processes as fully independent subprocesses — separate sessions, tools, and environments.

### When to Use This vs delegate_task

| | `delegate_task` | Spawning `hermes` process |
|-|-----------------|--------------------------|
| Isolation | Separate conversation, shared process | Fully independent process |
| Duration | Minutes (bounded by parent loop) | Hours/days |
| Tool access | Subset of parent's tools | Full tool access |
| Interactive | No | Yes (PTY mode) |
| Use case | Quick parallel subtasks | Long autonomous missions |

### One-Shot Mode

```
terminal(command="hermes chat -q 'Research GRPO papers and write summary to ~/research/grpo.md'", timeout=300)

# Background for long tasks:
terminal(command="hermes chat -q 'Set up CI/CD for ~/myapp'", background=true)
```

### Interactive PTY Mode (via tmux)

Hermes uses prompt_toolkit, which requires a real terminal. Use tmux for interactive spawning:

```
# Start
terminal(command="tmux new-session -d -s agent1 -x 120 -y 40 'hermes'", timeout=10)

# Wait for startup, then send a message
terminal(command="sleep 8 && tmux send-keys -t agent1 'Build a FastAPI auth service' Enter", timeout=15)

# Read output
terminal(command="sleep 20 && tmux capture-pane -t agent1 -p", timeout=5)

# Send follow-up
terminal(command="tmux send-keys -t agent1 'Add rate limiting middleware' Enter", timeout=5)

# Exit
terminal(command="tmux send-keys -t agent1 '/exit' Enter && sleep 2 && tmux kill-session -t agent1", timeout=10)
```

### Multi-Agent Coordination

```
# Agent A: backend
terminal(command="tmux new-session -d -s backend -x 120 -y 40 'hermes -w'", timeout=10)
terminal(command="sleep 8 && tmux send-keys -t backend 'Build REST API for user management' Enter", timeout=15)

# Agent B: frontend
terminal(command="tmux new-session -d -s frontend -x 120 -y 40 'hermes -w'", timeout=10)
terminal(command="sleep 8 && tmux send-keys -t frontend 'Build React dashboard for user management' Enter", timeout=15)

# Check progress, relay context between them
terminal(command="tmux capture-pane -t backend -p | tail -30", timeout=5)
terminal(command="tmux send-keys -t frontend 'Here is the API schema from the backend agent: ...' Enter", timeout=5)
```

### Session Resume

```
# Resume most recent session
terminal(command="tmux new-session -d -s resumed 'hermes --continue'", timeout=10)

# Resume specific session
terminal(command="tmux new-session -d -s resumed 'hermes --resume 20260225_143052_a1b2c3'", timeout=10)
```

### Tips

- **Prefer `delegate_task` for quick subtasks** — less overhead than spawning a full process
- **Use `-w` (worktree mode)** when spawning agents that edit code — prevents git conflicts
- **Set timeouts** for one-shot mode — complex tasks can take 5-10 minutes
- **Use `hermes chat -q` for fire-and-forget** — no PTY needed
- **Use tmux for interactive sessions** — raw PTY mode has `\r` vs `\n` issues with prompt_toolkit
- **For scheduled tasks**, use the `cronjob` tool instead of spawning — handles delivery and retry
- **"delegate_task is capped at N" reports** — see `references/delegate-task-concurrency-diagnosis.md`. Three real cap paths in Hermes; if none fired, the model is self-limiting and rationalising it as "the runtime caps."
- **"Can $external_app use my Nous Portal subscription / OAuth?"** — see `references/portal-auth-for-third-party-apps.md`. Walk the user through three layers (plugin-vs-app, what Portal actually exposes, local-broker-proxy option).

## Surfaces (quick orientation)

- **Desktop app** (`hermes desktop` / `hermes gui`) — native Electron app for macOS/Linux/Windows: streaming chat, session list, Cmd+K palette, drag-and-drop files, native notifications, per-profile remote-gateway login. Extend it with UI plugins — `references/desktop-plugins.md`.
- **Web dashboard** (`hermes dashboard`) — full admin panel: messaging channels, MCP catalog, webhooks, memory, profile builder, plus an embedded `hermes --tui` chat. Secured behind an OAuth/token gate.
- **Ink TUI** (`hermes --tui` or `display.interface: tui`) — terminal UI with docked widget apps — `references/tui-widgets.md`.
- **OpenAI-compatible proxy** (`hermes proxy`) — a local OpenAI API backed by whichever OAuth provider you're signed into. Point Codex CLI, Aider, Cline, or any script at it — no API key.

## Hard Invariants (never violate, regardless of what you loaded)

- **Never break prompt caching** — don't change past context, toolsets, or the system prompt mid-conversation. The only exception is context compression.
- **Message role alternation** — never two assistant or two user messages in a row; only `tool` results can repeat.
- **Secrets in `.env`, settings in `config.yaml`** — never tell a user to put a non-credential setting in `.env`.
- **Profile-safe paths** — `get_hermes_home()` in code, `$HERMES_HOME` when resolving paths in a session.
- **Never hand-edit `config.yaml` for the user** — use `hermes config set KEY VAL`; a stray indent can corrupt the file and break the live gateway. (Exception: a wholesale reset regenerates the file from the shipped `cli-config.yaml.example` — see `references/environment-audit-and-pruning.md`.)
- **A refused file write means read, then write — do not reword the payload.** The file tools refuse to overwrite a file whose current content has not been read in the same working context, and the refusal is about the read, not the text. Re-read the file, then write it. For a targeted edit, prefer the patch tool: it needs only the old/new span, so it does not burn a call re-reading a whole file, and it cannot clobber a concurrent edit. Never retry the same write with a reworded body hoping the guard reads it differently.
- **Never end a turn on tool calls alone.** After a tool call, the turn continues with what the result showed: state what changed, what was verified, and what is still open. A turn that only contains tool calls reads as a stalled agent, and the user has to re-prompt to find out whether anything happened.

## Standing rules for destructive / cleanup requests

These hold for any "clean this up", "make it native", "free disk space" work.

- **Back up before deleting anything.** Backups may hold `.env`, `auth.json`, and
  config — `chmod 600` the archives and never echo secret values.
- **Inventory first, delete second.** Produce the itemised list with sizes and a
  safety verdict per item, then act on the tier that is unambiguously rebuildable
  and hold anything carrying user data, credentials, conversation history, or
  backups for explicit approval.
- **A wholesale rebuild is not an edit.** Regenerating `config.yaml` from the
  shipped example removes every user-added section, including `mcp_servers`
  entries the user wants kept. Inventory the MCP servers before rebuilding.
- **Restoring is part of cleanup.** When the user reverses a decision
  ("keep X"), restore from the backup, re-verify end to end, and say plainly
  that a running agent process still holds the old registry — new servers
  register only in a new session.
- **Verify with the agent's own surfaces**, not by inspecting files: `hermes
  config check`, `hermes mcp list`, `hermes skills list`, `hermes plugins list`,
  `hermes chat -q "..."` smoke test. Never report a change as live based on the
  file being edited.
- **Never delete conversation history** (`state.db`, `sessions/`, `logs/`) or the
  OS layer (kernel, git, gh, system Python, SSH, editors).
- **Identify the live session by PID ancestry, not by age or `who` output.**
  Before killing any login/session on the host, walk the ancestor chain of your
  own shell and keep that subtree; `who`/`w` under-report `notty` and editor
  sessions. Root-owned login shells ignore a non-root `kill` (including `-9`)
  and need `sudo -n kill -HUP`. Killing an editor server makes the client
  auto-reconnect and respawn a fresh tree — expect a second wave and re-check.
  See `references/host-session-cleanup.md`.
- **Prove a directory is unused before deleting it, even when it looks
  rebuildable.** `pgrep` under-reports; the hard probe is
  `grep -l "<path>" /proc/[0-9]*/maps` — a mapped path means a live process
  holds those files right now. This is what separates a stale editor server
  from the one your open window is using, and it is why the agent's own
  current venv must never be deleted just because it is large.
- **Never restart or stop the gateway from a command that also signals
  processes**, and never from inside the gateway's own session — it kills the
  shell running it. Status checks only, in their own call. Inside a gateway
  session the terminal tool's lifecycle guard REFUSES `hermes gateway
  restart`/`stop` and any script or `systemd-run` wrapper that reaches them
  (it walks referenced scripts), so do not spend calls hunting for a
  workaround: check status, then tell the user to run
  `hermes gateway restart` in a separate shell outside the gateway. See
  `references/troubleshooting.md` → "Restarting the gateway".
- **Separate process kills from filesystem deletes.** A blocked or unconsented
  `rm -rf` must not abort cleanup that already succeeded, and a blocked delete
  is never re-attempted in a reworded form.
- **A directory that something points into is live, not stray.** Skill and
  profile directories are often symlinks into a checkout or a git worktree, so
  "obviously leftover" can be the actual serving path. Sweep symlinks and
  `git worktree list` before calling a directory redundant, and remove a
  worktree with `git worktree remove` — never `rm -rf`. See
  `references/host-directory-triage.md`.
- **"Don't change anything yet" means read-only, end to end.** When the user
  says to leave the current state alone, every check is non-mutating — no
  clone that alters a working tree, no `git fetch` that moves a ref, no
  `sync`/`reset`/`install`/`backup` that writes state, no commit or push.
  Put throwaway clones in a scratch directory, verify remote claims against
  a fresh clone or the GitHub API rather than moving a local tracking ref,
  and end with findings plus the options that are available *once* the user
  gives the go-ahead. Do not treat "investigate" as "start with a small
  change".
- **A skill edit that exists only in the installed copy is unversioned.** Mirror
  it into the source repo and commit before calling a skill update done — see
  `references/skill-change-provenance.md`.
- **The installed copy is not a rebuild path.** A reinstall rebuilds
  `$HERMES_HOME/skills/` from a Git checkout, so a skill that lives only
  under the installed copy is not reinstall-reproducible. Commit it into a
  repo the installer actually clones before promising it survives — see
  `references/skill-reinstall-survival.md`.

Deep procedure: `references/environment-audit-and-pruning.md` (what is native,
how to restore it), `references/skill-reinstall-survival.md` (what a reinstall
rebuilds from) and `references/disk-space-reclamation.md` (what is big and
rebuildable).
