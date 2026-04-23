---
name: ddaro:clear
description: "Post-merge cleanup. Delete merged branches and remove their worktrees. Safe deletion only (refuses unmerged). Renamed from /ddaro:clean in v0.1.2; old name accepted as a deprecated alias."
argument-hint: "[name]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## /ddaro:clear [name]" and execute with `$ARGUMENTS` as optional name.

- If no name given, list all ddaro-owned worktrees whose branch is merged to main.
- Confirm via `git branch --merged main` - refuse if not merged.
- If merged: `git branch -d d-<name>`, `git push origin --delete d-<name>`, `git worktree remove <path>`.
- If unmerged, tell user to run `/ddaro:merge` first or `/ddaro:abandon` to force-discard.
