---
name: ddaro:config
description: "Direct config access - show settings, or set a key in one command. For users who know the key names. Use /ddaro:setting for guided menu. Also toggles the optional main_protection hook (off/warn/strict)."
argument-hint: "[init | main <path> | protect <path> | unprotect <path> | external <pattern> | naming <key> | pool <key> | language <en|ko> | context <true|false> | max <N> | main_protection <off|warn|strict>]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## /ddaro:config [action] [value]" and the "## Main protection hooks" section, then execute with `$ARGUMENTS` as action + value.

- No args → print full current config.
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
- `main_protection <off|warn|strict>` → toggle the hook-based main guard.
  - Writes the `main_protection` key in `.ddaro/config.json`.
  - If moving from `off` → `warn`/`strict`: preview the `.claude/settings.json` hook entries and prompt y/n/x. `y` merges entries (preserving the user's existing hooks via a sentinel marker); `n` prints the JSON for manual paste; `x` cancels.
  - If moving from `warn`/`strict` → `off`: remove only the ddaro-tagged entries from `.claude/settings.json`. Leave other hooks untouched.
- Unknown action → list valid actions.

Removals and other fine-grained edits → edit config file manually (safety).
