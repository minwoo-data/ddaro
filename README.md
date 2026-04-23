# ddaro

> Language: **English** · [한국어](README.ko.md)

**Worktree-based parallel workflow for Claude Code.** Isolated branch work with deletion-aware commits, size-based merge review, and crash-recoverable context logs.

When you run multiple Claude Code sessions at once — or just want to keep `main` spotless while experimenting — ddaro gives you disposable, safety-wrapped scratch worktrees. Each one has its own branch, its own lock, and its own on-disk memory so a session crash never loses context.

---

## Quick Start

### 1. Add the haroom_plugin marketplace (one time)

```
/plugin marketplace add https://github.com/minwoo-data/haroom_plugin.git
```

`ddaro` is distributed through the **haroom_plugin** aggregator along with the other haroom plugins (prism, triad, mangchi).

### 2. Install

```
/plugin install ddaro
```

### 3. Use

```
/ddaro:start           # creates a new isolated worktree (first run prompts for setup)
/ddaro:commit          # safe commit + push + context snapshot
/ddaro:merge           # size-based review + merge + cleanup
```

Restart Claude Code after install/update.

---

## Commands

| Command | What it does |
|---|---|
| `/ddaro:start [name]` | Create a new worktree + branch + lock |
| `/ddaro:commit [msg]` | Stage all, classify deletions, confirm flagged, commit, push, write context MD |
| `/ddaro:merge` | Pre-flight conflict check, size-based review, merge, y/n cleanup |
| `/ddaro:status` | Current worktree's state (branch, commits, push, lock match) |
| `/ddaro:list` | All ddaro-owned worktrees with technical summary |
| `/ddaro:summary [name]` | Read-only content recap |
| `/ddaro:resume` | Pick a worktree + recap + cd + paste prompt (crash recovery / days-later return) |
| `/ddaro:clear [name]` | Delete merged worktrees post-hoc (renamed from `/ddaro:clean` in v0.1.2) |
| `/ddaro:abandon <name>` | 3-layer guarded force-discard |
| `/ddaro:setting` | Interactive settings menu |
| `/ddaro:config [key]` | Direct config access |

Also callable as `/ddaro <subcommand>`.

---

## Features

- **Physical isolation** — each task gets its own git worktree in its own folder. Parallel Claude sessions cannot collide.
- **Deletion-aware commits** — classifies diff deletions (replace / format / pure / function-level / >100 lines) and prompts only when destructive.
- **Size-based merge review** — small diffs merge after deletion re-check; medium diffs auto-invoke `triad`; large diffs auto-invoke `prism`.
- **Crash-recoverable context** — every commit writes `.ddaro/context/<sha>.md` and refreshes `CURRENT.md`. After a session or IDE crash, `/ddaro:summary` rebuilds the full picture.
- **3-layer protection** against accidental destruction:
  - Layer 1: `protected_worktrees` config list
  - Layer 2: `.ddaro/OWNED` ownership flag
  - Layer 3: typed `yes, I'm sure` confirmation for `abandon`
- **Configurable naming** — numbers by default, or swap to animals / Korean cities / US states / fruit / Greek letters via `/ddaro:setting`.
- **Bilingual** — all output in English (default) or Korean via config.

---

## Configuration

First `/ddaro:start` triggers a 5-step setup:

1. Language (english / korean)
2. Main worktree (which folder ddaro must not touch)
3. Protected worktrees (other folders to leave alone)
4. Naming strategy (`d-number` / `d-pool` / `ddaro-number` / `ddaro-pool`)
5. Name pool (`korea_city` / `animal` / `us_state` / `fruit` / `greek`)

Change later via `/ddaro:setting` (interactive menu) or `/ddaro:config <key> <value>`.

Config file: `<main-worktree>/.ddaro/config.json`.

---

## Example session

```
/ddaro:start billing-fix
# → Creates myapp-d-billing-fix worktree + d-billing-fix branch
# → Outputs copy-paste prompt for new terminal

# ... edit in the new worktree, run Claude there ...

/ddaro:commit "reproduce the bug"
# → Stages, checks deletions, commits, pushes
# → Writes .ddaro/context/<ts>-<sha>.md

/ddaro:commit "fix date math"
# → Same cycle, another context snapshot

/ddaro:merge
# → fetch origin, conflict dry-run, size check (small/medium/large)
# → auto-review if medium/large
# → PR path or local merge
# → y/n to cleanup worktree

# Later, after a crash:
cd myapp-d-billing-fix
claude
/ddaro:summary
# → Full recap: what was done, where you stopped, next recommended
```

---

## Update

```
/plugin update
```

Then restart Claude Code.

---

## Troubleshooting

### `/ddaro:*` commands don't appear after install

Plugins are loaded at Claude Code startup. If `/ddaro:start` and the other subcommands don't show up:

1. **Restart Claude Code** — required after every install and update.
2. Run `/plugin` and confirm `ddaro` is listed as **enabled**.
3. If it's listed but disabled, enable it: `/plugin enable ddaro@ddaro`.
4. Still missing? Open `~/.claude.json` and check that `enabledPlugins` contains a `ddaro` entry. If it's `{}`, the install didn't complete — rerun `/plugin install ddaro@ddaro`.

Symptom check: if `/ddaro` only triggers a local skill (not the namespaced `/ddaro:start`, `/ddaro:commit`, …), the plugin is not loaded.

### Marketplace add succeeded but install fails

- Confirm git clone access to `https://github.com/minwoo-data/ddaro.git` from your shell.
- Remove and re-add the marketplace: `/plugin marketplace remove ddaro` then the Quick Start step 1 again.

---

## Requirements

- Claude Code (any version with `/plugin` command)
- Git 2.5+ (for `worktree` command)
- `gh` CLI (for PR path in `/ddaro:merge` — optional, local-merge path works without)
- Works on Windows (Git Bash / WSL2), macOS, Linux.

---

## Philosophy

Main worktree is a **receiver** — you look at it, you don't change it directly. All work happens in ddaro worktrees, one per task. When a task is done, its worktree is reviewed, merged, and removed. Main stays clean, history stays intentional.

The context MD layer exists because Claude sessions forget things on crash or restart. Instead of relying on tmux or shell state, ddaro writes what was done to disk after every commit. That file is your memory, not the Claude process.

---

## License

MIT — see [LICENSE](LICENSE)

## Author

Minwoo Park — [github.com/minwoo-data](https://github.com/minwoo-data)

## Contributing

Issues and PRs welcome at [github.com/minwoo-data/ddaro](https://github.com/minwoo-data/ddaro).
