---
name: ddaro:config
description: "Config access. No args → interactive 9-item menu. With args → direct key set (for users who know the keys). Also sets the mode for the plugin-native protective hooks (main_protection / branch_naming / cross_worktree_check / branch_worktree_match / evidence_check) and runs `migrate` to clean up legacy settings.json hook entries."
argument-hint: "[menu (default) | show | init | migrate | main <path> | protect <path> | unprotect <path> | external <pattern> | naming <key> | pool <key> | language <en|ko> | context <true|false> | max <N> | main_protection <off|warn|strict> | branch_naming <off|warn|strict> | cross_worktree_check <on|off> | branch_worktree_match <off|warn|strict> | evidence_check <off|warn|strict>]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` sections "## /ddaro:config [action] [value]", "## Hook registration", and "## Main protection hooks", then execute with `$ARGUMENTS` as action + value.

**Hooks are plugin-native (0.5.0).** The protective hooks are registered by the plugin in `hooks/hooks.json` and are active whenever ddaro is enabled. The `main_protection` / `branch_naming` / `cross_worktree_check` / `branch_worktree_match` / `evidence_check` actions below only write the chosen **mode** into `<main>/.ddaro/config.json` - they never touch `.claude/settings.json`. The hook reads that mode at runtime and no-ops (fail-open) when it is `off` / absent.

- **No args → interactive menu**: numbered 9-item menu with current values in brackets (language / naming_strategy / name_pool / max_concurrent / warn_threshold / stale_days / context_persistence / protected_worktrees / main_worktree). Pick a number → sub-menu → save → return. `0` or Enter → exit. Persist to `<main_worktree>/.ddaro/config.json` immediately (no restart).
- `show` → print full current config without menu.
- `init` → relaunch initial setup wizard (5-step prompt).
- `migrate` *(new in 0.5.0)* → remove redundant ddaro hook entries from `.claude/settings.json` that were installed by versions `<= 0.4.0`. Now that the hooks are plugin-native, those entries are leftover cruft. Procedure:
  - Locate the project's `.claude/settings.json` (resolve from `<main>` first, then cwd). If absent → "nothing to migrate".
  - Parse it. In `hooks.PreToolUse` and `hooks.SessionStart`, remove any hook command whose `command` string references `${CLAUDE_PLUGIN_ROOT}/hooks/` followed by one of: `check-main-edit.py`, `check-main-bash.py`, `check-branch-naming.py`, `check-worktree-branch-match.py`, `check-evidence.py`, `session-start-notice.py`, `cross-worktree-health.py`. Drop now-empty `hooks` arrays and now-empty matcher blocks. **Leave every non-ddaro hook untouched.**
  - Idempotent: if no matching entries exist, report "already clean" and make no write. Preserve the rest of the file (indentation, other keys) and back nothing out otherwise.
  - This action edits `.claude/settings.json` only - it does not change any `.ddaro/config.json` mode.
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
  - Plugin-native: writing the mode is sufficient. `warn`/`strict` activate the hook; `off` makes it no-op. No `.claude/settings.json` edit (see the note above).
  - Bypass a single command even in strict mode: `ALLOW_MAIN_DIRECT=1 <your command>`. `git merge` is always allowed (main's job is to receive merges). Files matching `planning_patterns` (default: `.planning/**`, `.gsd/**`, `CHANGELOG.md`, `STATE.md`, `ROADMAP.md`, `.claude/**`) are always allowed.
- `branch_naming <off|warn|strict>` → toggle the hook-based branch-name enforcement. Prevents `git checkout -b <name>` / `switch -c` / `branch <name>` / `worktree add -b <name>` from creating branches that don't follow the ddaro convention so non-ddaro branch creations still respect `name_pool`.
  - Writes the `branch_naming` key in `.ddaro/config.json`.
  - Plugin-native (`PreToolUse` Bash → `${CLAUDE_PLUGIN_ROOT}/hooks/check-branch-naming.py`): writing the mode is sufficient; no `.claude/settings.json` edit.
  - Allowed branch patterns when strict: `d-<city>` / `d-<city>/<topic>` / `feat|fix|chore|docs|refactor|test|style|build|ci|perf/<topic>-<city>` / `backup/d-<city>-<...>` / `main|master|develop` / `release/*` / `hotfix/*` / `ddaro/*` / `dependabot/*`.
  - One-shot bypass: `ALLOW_NON_DDARO_BRANCH=1 <your command>`.
- `cross_worktree_check <on|off>` → toggle SessionStart drift report across all ddaro-managed worktrees. Reads `protected_worktrees` + `git worktree list` and reports per-worktree: tracked-deleted files, behind origin, uncommit count, stale (per `stale_days`). Silent when all clean (zero token cost).
  - Writes the `cross_worktree_check` key in `.ddaro/config.json`.
  - Plugin-native (SessionStart → `${CLAUDE_PLUGIN_ROOT}/hooks/cross-worktree-health.py`): writing `on`/`off` is sufficient; no `.claude/settings.json` edit.
- `branch_worktree_match <off|warn|strict>` → toggle the hook-based "commit on right worktree" guard. Blocks `git commit` when the worktree's city marker (e.g. `d-busan` from cwd `*-d-busan`) doesn't match the branch's city marker (e.g. branch `d-namyangju`). Catches the foot-gun where `git switch` jumps branches but the user forgot which physical worktree they were in.
  - Writes the `branch_worktree_match` key in `.ddaro/config.json`.
  - Plugin-native (`PreToolUse` Bash → `${CLAUDE_PLUGIN_ROOT}/hooks/check-worktree-branch-match.py`): writing the mode is sufficient; no `.claude/settings.json` edit.
  - One-shot bypass: `ALLOW_WORKTREE_BRANCH_MISMATCH=1 <your command>`.
- Unknown action → list valid actions.

Removals and other fine-grained edits → edit config file manually (safety).
