---
name: ddaro:start
description: "Create a new isolated ddaro worktree + branch with lock. Auto-detect existing ddaro worktrees and offer to resume. First run triggers initial config prompt."
argument-hint: "[name]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## `/ddaro start [name]`" and execute with `$ARGUMENTS` as the optional name.

- If no `.ddaro/config.json` exists, run initial setup prompt first (language, main worktree, protected list, naming strategy, name pool).
- Scan existing ddaro worktrees. If any are active (uncommit) or ready (pushed, mergeable), offer to resume one instead of creating new.
- Respect `max_concurrent` and `warn_threshold` limits.
- Use `naming_strategy` + `name_pool` from config when user gives no name.
- Create worktree with `git worktree add <path> -b d-<name> main`.
- Plant `.git/ddaro-owned`, `.git/ddaro-lock`, `.ddaro/context/`, `.ddaro/.gitignore` (`*`), initial `.ddaro/CURRENT.md`.
- Output cd + copy-paste prompt for user to continue in a new terminal.
