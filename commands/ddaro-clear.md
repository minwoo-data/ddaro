---
name: ddaro:clear
description: "Post-merge cleanup. The single code path that removes a worktree. Requires cwd == main (refuses with cd instructions otherwise). Applies to owned and adopted identically once the branch is merged. Refuses unmerged - use /ddaro:merge first, or /ddaro:abandon (owned) / git worktree remove --force (adopted) to force-discard."
argument-hint: "[name]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## /ddaro:clear [name]" and execute with `$ARGUMENTS` as an optional name.

- **Precondition - cwd must equal `config.main_worktree`**. If not, print a helpful refusal:
  ```
  ✗ /ddaro:clear must run from main.
    cd <config.main_worktree>
    /ddaro:clear <name>
  ```
  Do not execute any deletion on mismatch.
- **Target resolution**:
  - No name → list merged ddaro-owned + adopted worktrees as candidates; let the user pick.
  - Name given → match against `LOCK.branch` or worktree folder basename.
- **Merge confirmation**: `git branch --merged main` must include the target's branch. If not, refuse and suggest `/ddaro:merge` first, or `/ddaro:abandon` (owned only) / `git worktree remove --force` (adopted).
- **Execute, in order**:
  - `git branch -d <branch>` (refuses if unmerged - expected safety).
  - `git push origin --delete <branch>` (prompt y/n if the remote ref still exists; skip silently if it does not).
  - `git worktree remove <path>` (context dir inside `.ddaro/` is gone with it).
- **Report**: confirm to the user. cwd stays at main so the next action proceeds naturally.

Applies identically to Tier 1 (owned) and Tier 2 (adopted). Tier differences live only in `/ddaro:abandon`.
