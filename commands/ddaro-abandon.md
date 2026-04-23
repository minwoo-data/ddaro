---
name: ddaro:abandon
description: "Force-discard a ddaro worktree. 3-layer protection: config-protected list rejection, .git/ddaro-owned flag check, and typed confirmation. Destructive."
argument-hint: "<name>"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## `/ddaro abandon <name>`" and execute with `$ARGUMENTS` as the required name.

- Refuse if `$ARGUMENTS` is empty.
- **Layer 1**: reject if the target path is in `protected_worktrees`.
- **Layer 2**: reject if target has no `.git/ddaro-owned` flag (not owned by ddaro).
- **Layer 3**: show destruction preview (commits lost, unpushed count, context snapshots lost, remote branch deletion opt-in), then require the user to type exactly `yes, I'm sure`.
- Execute:
  - `git worktree remove <path> --force`
  - `git branch -D d-<name>`
  - Optional: `git push origin --delete d-<name>` (if user said yes earlier)
