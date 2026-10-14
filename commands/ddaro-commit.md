---
name: ddaro:commit
description: "Safe commit - stage all, classify deletions, confirm flagged ones, optionally run verify (--verify), commit, push, write context snapshot MD. Repeatable per edit session."
argument-hint: "[--verify] [commit-message]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## /ddaro:commit [message]" and execute with `$ARGUMENTS` as the optional flags + commit message.

- Refuse if cwd is the main worktree (tell user to `/ddaro:start` first).
- Step 0: resolve config and run `python ${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py ensure-schema <main_worktree>` (show its line if any).
- Validate lock: current branch must match `.ddaro/LOCK` branch field.
- `git add -A`, then analyze `git diff --cached` for deletion patterns.
- Classify deletions: OK (replace/format) vs FLAG (pure) vs ALWAYS CONFIRM (function/class/export/export/100+ lines).
- If FLAG or ALWAYS CONFIRM present, show them and wait for `y/n/abort`.
- **If `--verify` flag set**: discover the project's verify command (primary: `.ddaro/verify.json`; fallback: `.claude/CLAUDE.md` "Commands" section). Run the verify command(s) matched to the touched files' types. On non-zero exit, prompt user before continuing - never silently commit broken code.
- If no message given, auto-generate: `ddaro: d-<name> - N files (+X -Y)`.
- Commit, then `git push origin d-<name>`.
- Context enrich (never write the MDs by hand): the PostToolUse hook already snapshotted the commit; run `python ${CLAUDE_PLUGIN_ROOT}/hooks/context_md.py enrich <worktree> <sha7>` with a JSON body on stdin (`what_was_done`, `next_planned`, `review_flags`, `currently`, `resume_hint{last_goal,next_expected}`) exactly as SKILL.md step 8 shows. stdout `created+enriched` just means the hook had not run; non-zero exit = print the one-line failure and continue.
- Report commit SHA, change size, push status, ahead-of-main count, context path.
