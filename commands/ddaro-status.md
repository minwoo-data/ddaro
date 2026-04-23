---
name: ddaro:status
description: "Show current ddaro worktree status - branch, lock match, commits ahead of main, uncommit, push state, context snapshot count, next suggested action."
argument-hint: ""
allowed-tools: [Bash, Read, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## `/ddaro status`" and execute.

- Detect if cwd is a ddaro worktree (has `.git/ddaro-owned`).
- If not, tell user they're in main or non-ddaro space; suggest `/ddaro:list` to see active ones.
- If yes, read `.git/ddaro-lock`, compare with current branch.
- Count commits ahead, uncommitted files, push status (origin up-to-date / ahead / behind).
- Count context snapshots in `.ddaro/context/`.
- Recommend next action (commit / merge / continue editing).
