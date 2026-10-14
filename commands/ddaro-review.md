---
name: ddaro:review
description: "Multi-lens review of a design doc or diff, findings written back in."
argument-hint: "<file> [--diff] [--codex] [--review-only]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, Agent]
disable-model-invocation: true
---

# /ddaro:review

<!-- step0 -->
**Step 0.** Find `.ddaro/config.json` in cwd or a parent; in a linked worktree with none, use the main worktree's (`git rev-parse --path-format=absolute --git-common-dir`, then its parent). None found: say "not a ddaro project - run /ddaro:start" and stop (`/ddaro:start` runs first-time setup instead). Then run `python ${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py ensure-schema <main_worktree>` once (`<main_worktree>` = cwd if in main, else `.ddaro/LOCK` `main_worktree`, else `config.main_worktree`) and show its line if it prints one. Terms: "main worktree" = the folder `config.main_worktree` (receives merges only); `<base>` = `config.base_branch` (default `main`), `origin/<base>` its remote-tracking ref; never hardcode a branch name. Reply in `config.language`. If a ddaro script exits non-zero or python is missing, print `[ddaro] <script> <subcommand> failed (exit N): <first stderr line>` and continue; never hand-write `.ddaro/context/*`, `CURRENT.md`, or the config keys `base_branch` / `auto_snapshot` / `schema_version`.
<!-- /step0 -->

1. **Doc**: 8 agents in one parallel message: prism's 5 design angles (conflict & reuse, claim accuracy, devil's advocate, robustness 4-axis, improvement: "is it sound?") + triad's 3 lenses (LLM implementability, architecture longevity, decision-maker comprehension: "is it well written?"). Every agent verifies the doc's file:line and behavior claims against the real code.
2. **`--diff`**: prism's 5 defect lenses on the branch diff (hunks + pre-change code + direct callers/callees + touched tests) with its evidence pass, plus triad on each changed markdown file only (triad >= 0.2.0 refuses code; a code-only diff gets prism alone, say so).
3. Installed skills: `/prism <doc>` (prism >= 0.3.1) or `/prism --diff`, and `/triad <doc>`, with the same verify-against-code instruction; if prism refuses a doc (0.3.0), run the 5 angles inline and note it. Not installed: run the agents directly.
4. Triage CRIT/HIGH/MED/LOW; promote findings raised by 2+ angles; list real contradictions for the user; re-verify every CRIT before acting.
5. Append `## Review findings (<date> - prism + triad)` (table: severity | finding | fix + a short what-changed note) to the target; for a doc also apply the fixes unless `--review-only`. Date from session context.
6. `--codex`: also run prism-all / triad-all (doc) or prism-all on the diff + triad-all on changed docs; without it, note that Codex is deferred to the implementation PR.
7. Output the top CRIT/HIGH and "implement, then /ddaro:check".
