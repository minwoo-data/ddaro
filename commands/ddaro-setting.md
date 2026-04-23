---
name: ddaro:setting
description: "Interactive menu to browse and change all ddaro settings — language, naming strategy, name pool, max concurrent, thresholds, context persistence, protected list, main worktree."
argument-hint: ""
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## `/ddaro setting`" and execute.

- Display 9-item numbered menu with current values in brackets.
- User picks a number → sub-menu (numbered options or value entry) → save → return to main menu.
- 0 or Enter → exit.
- Persist changes to `<main_worktree>/.ddaro/config.json` immediately (no restart required).
- Items: language / naming_strategy / name_pool / max_concurrent / warn_threshold / stale_days / context_persistence / protected_worktrees / main_worktree.
