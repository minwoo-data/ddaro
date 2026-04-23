---
name: ddaro:clean
description: "Deprecated alias for /ddaro:clear (renamed in v0.1.2). Prints a one-line warning and forwards to /ddaro:clear. Will be removed in v0.2.0."
argument-hint: "[name]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

First print this deprecation warning line exactly once:

  [warn] /ddaro:clean is deprecated - use /ddaro:clear. This alias will be removed in v0.2.0.

Then execute the same logic as /ddaro:clear with `$ARGUMENTS` as optional name:

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## /ddaro:clear [name]" and run it.

- If no name given, list all ddaro-owned worktrees whose branch is merged to main.
- Confirm via `git branch --merged main` - refuse if not merged.
- If merged: `git branch -d d-<name>`, `git push origin --delete d-<name>`, `git worktree remove <path>`.
- If unmerged, tell user to run `/ddaro:merge` first or `/ddaro:abandon` to force-discard.
