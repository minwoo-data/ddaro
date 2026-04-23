---
name: ddaro:commit
description: "Safe commit — stage all, classify deletions, confirm flagged ones, commit, push, write context snapshot MD. Repeatable per edit session."
argument-hint: "[commit-message]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## `/ddaro commit [message]`" and execute with `$ARGUMENTS` as the optional commit message.

- Refuse if cwd is the main worktree (tell user to `/ddaro:start` first).
- Validate lock: current branch must match `.git/ddaro-lock` branch field.
- `git add -A`, then analyze `git diff --cached` for deletion patterns.
- Classify deletions: OK (replace/format) vs FLAG (pure) vs ALWAYS CONFIRM (function/class/export/export/100+ lines).
- If FLAG or ALWAYS CONFIRM present, show them and wait for `y/n/abort`.
- If no message given, auto-generate: `ddaro: d-<name> — N files (+X -Y)`.
- Commit, then `git push origin d-<name>`.
- Write `.ddaro/context/<ISO>-<sha7>.md` and overwrite `.ddaro/CURRENT.md`.
- Report commit SHA, change size, push status, ahead-of-main count, context path.
