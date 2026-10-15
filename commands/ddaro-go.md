---
name: ddaro:go
description: "Run the next lifecycle stage (spec -> review -> implement -> check)."
argument-hint: "[spec|review|check]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, Agent]
disable-model-invocation: true
---

# /ddaro:go

<!-- step0 -->
**Step 0.** Find `.ddaro/config.json` in cwd or a parent; in a linked worktree with none, use the main worktree's (`git rev-parse --path-format=absolute --git-common-dir`, then its parent). None found: say "not a ddaro project - run /ddaro:start" and stop (`/ddaro:start` runs first-time setup instead). Then run `python "${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py" ensure-schema <main_worktree>` once (`<main_worktree>` = cwd if in main, else `.ddaro/LOCK` `main_worktree`, else `config.main_worktree`) and show its line if it prints one. Terms: "main worktree" = the folder `config.main_worktree` (receives merges only); `<base>` = `config.base_branch` (default `main`), `origin/<base>` its remote-tracking ref; never hardcode a branch name. Reply in `config.language`. If a ddaro script exits non-zero or python is missing, print `[ddaro] <script> <subcommand> failed (exit N): <first stderr line>` and continue; never hand-write `.ddaro/context/*`, `CURRENT.md`, or the config keys `base_branch` / `auto_snapshot` / `schema_version`.
<!-- /step0 -->

Conductor only: it picks the stage, gates cost, and records state; it never touches git history.

1. Must run inside an owned/adopted worktree; in main, list worktrees to `cd` into; elsewhere suggest `/ddaro:start` or `/ddaro:adopt`.
2. Stage: `$1` in spec/review/check forces it. Else `.ddaro/lifecycle.json` `{"stage", "doc", "updated"}`; absent -> infer and show the evidence:
   1. no `docs/design/<topic>.md` (topic from LOCK) -> `spec`
   2. doc without any h2 containing "Review findings" (numbered or dated headings count) -> `review`
   3. reviewed, and `git diff --name-only origin/<base>...HEAD` (three dots) plus uncommitted edits, minus `docs/**`, `*.md`, `.planning/**`, `.ddaro/**`, is empty -> `implement` (stop: the human writes the code)
   4. that set is non-empty -> `check`
   5. stage `done` recorded -> hand off to `/ddaro:commit` + `/ddaro:merge`
   LOCK/branch mismatch or far behind `origin/<base>`: say so and ask instead of guessing.
3. Before `review` (8 agents) or `check` (prism-all + checklist) state the cost and get a yes; offer to jump to another stage. `spec` still asks its `[DECIDE]` items.
4. Run the stage by following `${CLAUDE_PLUGIN_ROOT}/commands/ddaro-<stage>.md` (do not re-implement it).
5. Write `.ddaro/lifecycle.json` with the next stage (spec->review, review->implement, check PASS->done, check BLOCK->check) and today's date from session context, then say what `/ddaro:go` will do next. Never advance past a BLOCK.
