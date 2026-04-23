---
name: ddaro:config
description: "Direct config access - show settings, or set a key in one command. For users who know the key names. Use /ddaro:setting for guided menu."
argument-hint: "[init | main <path> | protect <path> | naming <key> | pool <key> | language <en|ko> | context <true|false> | max <N>]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## `/ddaro config [action] [value]`" and execute with `$ARGUMENTS` as action + value.

- No args → print full current config.
- `init` → relaunch initial setup wizard (5-step prompt).
- `main <path>` → change main worktree.
- `protect <path>` → add path to protected list.
- `naming <key>` → one of `d-number`, `d-pool`, `ddaro-number`, `ddaro-pool`.
- `pool <key>` → one of `animal`, `korea_city`, `us_state`, `fruit`, `greek`.
- `language <english|korean>` → output language.
- `context <true|false>` → context persistence toggle.
- `max <N>` → max concurrent worktrees.
- Unknown action → list valid actions.

Removals and other fine-grained edits → edit config file manually (safety).
