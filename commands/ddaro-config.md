---
name: ddaro:config
description: "Config access. No args → interactive 9-item menu. With args → direct key set (for users who know the keys). Also toggles the optional protective hooks (main_protection / branch_naming / cross_worktree_check / branch_worktree_match)."
argument-hint: "[menu (default) | show | init | main <path> | protect <path> | unprotect <path> | external <pattern> | naming <key> | pool <key> | language <en|ko> | context <true|false> | max <N> | main_protection <off|warn|strict> | branch_naming <off|warn|strict> | cross_worktree_check <on|off> | branch_worktree_match <off|warn|strict>]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## /ddaro:config [action] [value]" and the "## Main protection hooks" section, then execute with `$ARGUMENTS` as action + value.

- **No args → interactive menu**: numbered 9-item menu with current values in brackets (language / naming_strategy / name_pool / max_concurrent / warn_threshold / stale_days / context_persistence / protected_worktrees / main_worktree). Pick a number → sub-menu → save → return. `0` or Enter → exit. Persist to `<main_worktree>/.ddaro/config.json` immediately (no restart).
- `show` → print full current config without menu.
- `init` → relaunch initial setup wizard (5-step prompt).
- `main <path>` → change main worktree.
- `protect <path>` → add path to protected list.
- `unprotect <path>` → remove path from protected list.
- `external <pattern>` → append a glob to `external_patterns` (for Tier 5 worktrees owned by other tools).
- `naming <key>` → one of `d-number`, `d-pool`, `ddaro-number`, `ddaro-pool`.
- `pool <key>` → one of `animal`, `korea_city`, `us_state`, `fruit`, `greek`.
- `language <english|korean>` → output language.
- `context <true|false>` → context persistence toggle.
- `max <N>` → max concurrent worktrees.
- `main_protection <off|warn|strict>` → toggle the hook-based main guard. **First-time setup (`/ddaro:start`) already prompts for this and defaults to `strict`** — this command is for changing it later.
  - Writes the `main_protection` key in `.ddaro/config.json`.
  - If moving from `off` → `warn`/`strict`: preview the `.claude/settings.json` hook entries and prompt y/n/x. `y` merges entries (preserving the user's existing hooks via a sentinel marker); `n` prints the JSON for manual paste; `x` cancels.
  - If moving from `warn`/`strict` → `off`: remove only the ddaro-tagged entries from `.claude/settings.json`. Leave other hooks untouched.
  - Bypass a single command even in strict mode: `ALLOW_MAIN_DIRECT=1 <your command>`. `git merge` is always allowed (main's job is to receive merges). Files matching `planning_patterns` (default: `.planning/**`, `.gsd/**`, `CHANGELOG.md`, `STATE.md`, `ROADMAP.md`, `.claude/**`) are always allowed.
- `branch_naming <off|warn|strict>` → toggle the hook-based branch-name enforcement. Prevents `git checkout -b <name>` / `switch -c` / `branch <name>` / `worktree add -b <name>` from creating branches that don't follow the ddaro convention so non-ddaro branch creations still respect `name_pool`.
  - Writes the `branch_naming` key in `.ddaro/config.json`.
  - If moving from `off` → `strict`: preview the `.claude/settings.json` hook entry (`PreToolUse` Bash → `${CLAUDE_PLUGIN_ROOT}/hooks/check-branch-naming.py`) and prompt y/n/x to merge.
  - Allowed branch patterns when strict: `d-<city>` / `d-<city>/<topic>` / `feat|fix|chore|docs|refactor|test|style|build|ci|perf/<topic>-<city>` / `backup/d-<city>-<...>` / `main|master|develop` / `release/*` / `hotfix/*` / `ddaro/*` / `dependabot/*`.
  - One-shot bypass: `ALLOW_NON_DDARO_BRANCH=1 <your command>`.
- `cross_worktree_check <on|off>` → toggle SessionStart drift report across all ddaro-managed worktrees. Reads `protected_worktrees` + `git worktree list` and reports per-worktree: tracked-deleted files, behind origin, uncommit count, stale (per `stale_days`). Silent when all clean (zero token cost).
  - Writes the `cross_worktree_check` key in `.ddaro/config.json`.
  - If `on`: preview the `.claude/settings.json` SessionStart hook entry (`${CLAUDE_PLUGIN_ROOT}/hooks/cross-worktree-health.py`) and prompt y/n/x to merge.
- `branch_worktree_match <off|warn|strict>` → toggle the hook-based "commit on right worktree" guard. Blocks `git commit` when the worktree's city marker (e.g. `d-busan` from cwd `*-d-busan`) doesn't match the branch's city marker (e.g. branch `d-namyangju`). Catches the foot-gun where `git switch` jumps branches but the user forgot which physical worktree they were in.
  - Writes the `branch_worktree_match` key in `.ddaro/config.json`.
  - If `strict`: preview the `.claude/settings.json` PreToolUse Bash hook entry (`${CLAUDE_PLUGIN_ROOT}/hooks/check-worktree-branch-match.py`) and prompt y/n/x to merge.
  - One-shot bypass: `ALLOW_WORKTREE_BRANCH_MISMATCH=1 <your command>`.
- Unknown action → list valid actions.

Removals and other fine-grained edits → edit config file manually (safety).
