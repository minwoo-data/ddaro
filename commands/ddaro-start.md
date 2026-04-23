---
name: ddaro:start
description: "Create a new isolated ddaro worktree + branch with lock. First run triggers initial config prompt. Scans existing worktrees and surfaces unmanaged ones (with /ddaro:adopt suggestion) and dirty-main state (classified into planning vs code)."
argument-hint: "[name]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## /ddaro:start [name]" and execute with `$ARGUMENTS` as the optional name.

- If no `.ddaro/config.json` exists, run initial 5-step setup first (language, main worktree, protected list, naming strategy, name pool).
- **Existing-worktree scan** — classify all worktrees via the tier algorithm in SKILL.md. Present in groups:
  - Ddaro-owned / adopted active → offer to resume instead of creating new.
  - Unmanaged (not under ddaro) → surface with three options per entry: finish in place, `/ddaro:adopt <path>`, or ignore. Default is ignore (never auto-adopt).
- Respect `max_concurrent` and `warn_threshold` limits.
- Use `naming_strategy` + `name_pool` from config when user gives no name.
- **Main-worktree dirty check** — if uncommitted changes exist in main, classify files using `config.planning_patterns` (default: `.planning/**`, `.gsd/**`, `STATE.md`, `ROADMAP.md`, `CHANGELOG.md`). Offer targeted options (commit all / commit planning only / cherry-pick later / start anyway / cancel). Planning-like files are what a user typically wants to carry into the new worktree; code changes usually belong in the ddaro branch itself.
- Create worktree with `git worktree add <path> -b d-<name> main`.
- Plant `<path>/.ddaro/OWNED`, `<path>/.ddaro/LOCK`, `<path>/.ddaro/context/`, initial `<path>/.ddaro/CURRENT.md`. Append `.ddaro/` to `<main_worktree>/.gitignore` if absent (once per project).
- Output cd + copy-paste prompt for user to continue in a new terminal.
