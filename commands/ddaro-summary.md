---
name: ddaro:summary
description: "Content-based summary - reads commits, diffs, and .ddaro/context/*.md to reconstruct what was being done and where work stopped. Survives session/IDE crashes."
argument-hint: "[name]"
allowed-tools: [Bash, Read, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## `/ddaro summary [name]`" and execute with `$ARGUMENTS` as optional name.

- If no name: summarize each ddaro worktree in 1-2 lines (all of them).
- If name given: produce detailed recap for that worktree only.
- Data sources:
  - `git log main..HEAD` commit messages
  - `git diff --stat main..HEAD`
  - `.ddaro/context/*.md` "What was done" sections
  - `.ddaro/CURRENT.md` Resume hint
  - `git status --porcelain` for uncommit
- Produce: "What was being worked on", "Where it stopped", "Next recommended action".
- Used for session recovery after crash - no special setup needed on user side.
