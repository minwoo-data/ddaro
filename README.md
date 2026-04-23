# ddaro

> Language: **English** · [한국어](README.ko.md)

**Run multiple AI coding sessions without ever corrupting your repo.**

AI coding has gone parallel. You run one Claude Code session for billing, another for auth, a third to experiment. But git was designed for humans doing one thing at a time, so two sessions touching the same working tree overwrite each other silently. ddaro is the session-isolation layer that rebuilds the git workflow for parallel AI development.

```
/ddaro:start   -> work safely      (new worktree + branch, one per session)
/ddaro:commit  -> snapshot         (deletion-aware commit + auto-push + context MD)
/ddaro:merge   -> review & merge   (size-based review + pre-flight conflict check)
```

Ever had multiple Claude Code sessions stomp on each other's code, or watched edits silently disappear? ddaro physically isolates every session into its own worktree and branch so collisions cannot happen, and verifies nothing is being overwritten when you merge.

---

## 30-second demo

**Without ddaro:**

You fire up Session A to fix billing and Session B to refactor auth. Both edit `src/services/` at the same time. You alt-tab, and Session B overwrites a file Session A just saved. You only catch it a week later. The fix is gone.

**With ddaro:**

`/ddaro:start billing` for Session A, `/ddaro:start auth` for Session B. Two worktrees, two branches, two folders. Collision is structurally impossible. On `/ddaro:merge`, ddaro shows the diff, flags deletions that have no replacement, and refuses the merge if something on `main` would silently vanish.

## Who should use this

- **Parallel Claude Code sessions** - fastest way to stop them clobbering each other's edits
- **Risky refactors** - scratch worktree with auto-push on every commit, so a crash or a bad idea cannot eat the work
- **Long-running experimental branches** - each worktree carries a topic + lock file, so you remember what each was for even after a week
- **Crash-prone workflows** - plain-text context snapshots to disk after every commit; `/ddaro:resume` rebuilds the picture in one command
- **Interruption-heavy days (hotfix while feature in flight)** - feature worktree stays untouched while you spawn a separate hotfix worktree, merge it, and resume the feature with its full context restored

## Sibling tools (same marketplace)

- **[prism](https://github.com/minwoo-data/prism)** - 5-agent parallel code review with singleton verification. Use before major PRs.
- **[triad](https://github.com/minwoo-data/triad)** - 3-perspective deliberation on design docs (LLM clarity / architecture / end-user).
- **[mangchi](https://github.com/minwoo-data/mangchi)** - Claude + Codex cross-model iterative code refinement.

---

## Quick Start

### 1. Add the haroom_plugins marketplace (one time)

```
/plugin marketplace add https://github.com/minwoo-data/haroom_plugins.git
```

`ddaro` is distributed through the **haroom_plugins** aggregator along with the other haroom plugins (prism, triad, mangchi).

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
| `/ddaro:status` | In-worktree: local state. In main: auto-delegates to `/ddaro:list`. |
| `/ddaro:list` | All worktrees grouped by tier (owned / adopted / unmanaged / protected / external) |
| `/ddaro:resume [name] [--recap-only] [--all]` | Pick a worktree + recap + cd + paste prompt. `--recap-only` = read-only summary (replaces old `/ddaro:summary`). |
| `/ddaro:adopt <path>` | Bring an existing non-ddaro worktree under ddaro management (plants `.ddaro/` overlay, marks `adopted=true`). |
| `/ddaro:clear [name]` | Delete merged worktrees post-hoc (the single cleanup path — must run from main) |
| `/ddaro:abandon <name> [--force]` | 3-layer guarded force-discard. `--force` required for adopted targets. |
| `/ddaro:config [key] [value]` | No args → interactive menu. With args → direct key set. Also toggles main_protection hook. |

Also callable as `/ddaro <subcommand>`.

---

## Features

- **Physical isolation** - each task gets its own git worktree in its own folder. Parallel Claude sessions cannot collide.
- **Deletion-aware commits** - classifies diff deletions (replace / format / pure / function-level / >100 lines) and prompts only when destructive.
- **Size-based merge handling** - small / medium / large diffs each get progressively stricter deletion scans. Cross-plugin review (`--review=triad` or `--review=prism`) is opt-in only and requires the named plugin to be installed. ddaro never calls another plugin automatically.
- **Crash-recoverable context** - every commit writes `.ddaro/context/<sha>.md` and refreshes `CURRENT.md`. After a session or IDE crash, `/ddaro:resume` (or `/ddaro:resume --recap-only` for read-only) rebuilds the full picture.
- **3-layer protection** against accidental destruction:
  - Layer 1: `protected_worktrees` config list
  - Layer 2: `.ddaro/OWNED` ownership flag
  - Layer 3: typed `yes, I'm sure` confirmation for `abandon`
- **Configurable naming** - numbers by default, or swap to animals / Korean cities / US states / fruit / Greek letters via `/ddaro:config`.
- **Bilingual** - all output in English (default) or Korean via config.

---

## Configuration

First `/ddaro:start` triggers a 6-step setup:

1. Language (english / korean)
2. Main worktree (which folder ddaro must not touch)
3. Protected worktrees (other folders to leave alone)
4. Naming strategy (`d-number` / `d-pool` / `ddaro-number` / `ddaro-pool`)
5. Name pool (`korea_city` / `animal` / `us_state` / `fruit` / `greek`)
6. **Main protection** (`strict` default / `warn` / `off`) — installs a PreToolUse hook in `.claude/settings.json` that blocks direct `git commit` / `Edit` / `Write` on main. `git merge` stays allowed (main's job is to receive merges). Files in `planning_patterns` (`.planning/**`, `.gsd/**`, `CHANGELOG.md`, `STATE.md`, `ROADMAP.md`, `.claude/**`) also pass through. One-shot bypass: `ALLOW_MAIN_DIRECT=1 <cmd>`.

Change later via `/ddaro:config` (no args → interactive menu, or `/ddaro:config <key> <value>` for direct set). Toggle the guard specifically: `/ddaro:config main_protection <off|warn|strict>`.

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

# Later, after a crash (from main, picker-driven):
/ddaro:resume
# → numbered picker → pick billing-fix → prints cd + paste block + full recap

# Or if you already know which one: read-only recap, no cd:
/ddaro:resume billing-fix --recap-only
# → what was done, where you stopped, next recommended
```

### Interruption: hotfix while a feature is in flight

A common pattern — you're deep in a refactor and a production bug lands. Instead of stashing and branch-hopping, spawn a second worktree:

```
# Session A is already running /ddaro:start payment-refactor with ~12 commits
# on top. Don't touch it. From your main worktree terminal:

cd <main>
/ddaro:start hotfix-login-502
# → creates project-d-hotfix-login-502, separate folder, separate branch

cd <project>-d-hotfix-login-502
claude
# ... 10-minute fix ...

/ddaro:commit "fix: 502 on Safari login"
/ddaro:merge --local
# → fast local merge into main, skips PR

cd <main>
/ddaro:clear hotfix-login-502
# → branch deleted locally + remote, worktree removed

# Now resume the feature you were in:
cd <project>-d-payment-refactor
claude
/ddaro:resume
# → recap of the 12-commit state, next step, paste-ready prompt
```

No new command is needed — the "hotfix" flow is just the normal pipeline (`start` → `commit` → `merge --local` → `clear`) applied in parallel to your in-flight worktree. The feature worktree is never touched while you fix production.

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

1. **Restart Claude Code** - required after every install and update.
2. Run `/plugin` and confirm `ddaro` is listed as **enabled**.
3. If it's listed but disabled, enable it: `/plugin enable ddaro@ddaro`.
4. Still missing? Open `~/.claude.json` and check that `enabledPlugins` contains a `ddaro` entry. If it's `{}`, the install didn't complete - rerun `/plugin install ddaro@ddaro`.

Symptom check: if `/ddaro` only triggers a local skill (not the namespaced `/ddaro:start`, `/ddaro:commit`, …), the plugin is not loaded.

### Marketplace add succeeded but install fails

- Confirm git clone access to `https://github.com/minwoo-data/ddaro.git` from your shell.
- Remove and re-add the marketplace: `/plugin marketplace remove ddaro` then the Quick Start step 1 again.

---

## Requirements

- Claude Code (any version with `/plugin` command)
- Git 2.5+ (for `worktree` command)
- `gh` CLI (for PR path in `/ddaro:merge` - optional, local-merge path works without)
- Works on Windows (Git Bash / WSL2), macOS, Linux.

---

## Philosophy

Main worktree is a **receiver** - you look at it, you don't change it directly. All work happens in ddaro worktrees, one per task. When a task is done, its worktree is reviewed, merged, and removed. Main stays clean, history stays intentional.

The context MD layer exists because Claude sessions forget things on crash or restart. Instead of relying on tmux or shell state, ddaro writes what was done to disk after every commit. That file is your memory, not the Claude process.

---

## License

MIT - see [LICENSE](LICENSE)

## Author

haroom - [github.com/minwoo-data](https://github.com/minwoo-data)

## Contributing

Issues and PRs welcome at [github.com/minwoo-data/ddaro](https://github.com/minwoo-data/ddaro).
