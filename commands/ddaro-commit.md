---
name: ddaro:commit
description: "Safe commit: deletion check, optional --verify, commit, push, snapshot."
argument-hint: "[--verify] [message]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
disable-model-invocation: true
---

# /ddaro:commit

<!-- step0 -->
**Step 0.** Find `.ddaro/config.json` in cwd or a parent; in a linked worktree with none, use the main worktree's (`git rev-parse --path-format=absolute --git-common-dir`, then its parent). None found: say "not a ddaro project - run /ddaro:start" and stop (`/ddaro:start` runs first-time setup instead). Then run `python "${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py" ensure-schema <main_worktree>` once (`<main_worktree>` = cwd if in main, else `.ddaro/LOCK` `main_worktree`, else `config.main_worktree`) and show its line if it prints one. Terms: "main worktree" = the folder `config.main_worktree` (receives merges only); `<base>` = `config.base_branch` (default `main`), `origin/<base>` its remote-tracking ref; never hardcode a branch name. Reply in `config.language`. If a ddaro script exits non-zero or python is missing, print `[ddaro] <script> <subcommand> failed (exit N): <first stderr line>` and continue; never hand-write `.ddaro/context/*`, `CURRENT.md`, or the config keys `base_branch` / `auto_snapshot` / `schema_version`.
<!-- /step0 -->

Run inside an owned/adopted worktree; in the main worktree stop and suggest `/ddaro:start`. **Lock check**: if the checked-out branch differs from `.ddaro/LOCK` `branch`, show both and ask y/n (default abort).

1. `git add -A` (`.ddaro/` is git-ignored).
2. **Deletions** in `git diff --cached`: replacement (same symbol re-added nearby) or whitespace-only -> OK silently; pure deletion with no replacement -> FLAG; removed function/class/export, or >100 pure-deletion lines -> ALWAYS CONFIRM. If any FLAG/CONFIRM, show `Diff summary: +X -Y (N files)` and one line per item (`[confirm] <file>:<line> <what> - no replacement, intentional?`), then wait for y / n / abort.
3. **`--verify` only**: commands from `.ddaro/verify.json` (`{"commands": [{"pattern": "**/*.py", "run": "pytest -x -q"}], "default": "..."}`; first matching pattern per staged file, each command run once), else the fenced commands under `## Commands` in `.claude/CLAUDE.md` (pytest for .py, smoke/npm test for js/html), else warn "no verify config found" and continue. On a non-zero exit show the last 20 lines and ask: `k` keep staged and stop (default) / `d` unstage and `git restore` the touched files / `c` commit anyway (record "verify bypassed (c)" in review_flags).
4. `git commit -m "<message>"`; no message -> `ddaro: <branch> - N files (+X -Y)` (ASCII). If a pre-commit hook rejects, ask for a fix or message; never `--no-verify`.
5. `git push origin <branch>` (set upstream on first push).
6. **Enrich** the snapshot the hook just wrote (`<sha7>` from `git rev-parse --short=7 HEAD`):
```bash
python "${CLAUDE_PLUGIN_ROOT}/hooks/context_md.py" enrich <worktree> <sha7> <<'JSON'
{"what_was_done": "<one-line intent>", "next_planned": "<TODOs / next step>",
 "review_flags": "<step 2 flags, verify bypass, or None>", "currently": "Idle (just committed)",
 "resume_hint": {"last_goal": "<topic + intent>", "next_expected": "<next step>"}}
JSON
```
stdout `created+enriched <sha7>` just means the hook had not run.
7. Report: commit sha7, `N files (+X -Y)`, push state, commits ahead of `<base>`, snapshot file.

Between edits: re-check `git log --oneline -3 -- <file>` before editing a file you read earlier (another writer may have changed it); commit unrelated prerequisite fixes as their own commit first.
