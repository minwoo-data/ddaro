---
name: ddaro:check
description: "Pre-merge gate: prism-all on the diff + project ship checklist -> PASS/BLOCK."
argument-hint: "[branch|--staged]"
allowed-tools: [Bash, Read, Glob, Grep, Agent]
disable-model-invocation: true
---

# /ddaro:check

<!-- step0 -->
**Step 0.** Find `.ddaro/config.json` in cwd or a parent; in a linked worktree with none, use the main worktree's (`git rev-parse --path-format=absolute --git-common-dir`, then its parent). None found: say "not a ddaro project - run /ddaro:start" and stop (`/ddaro:start` runs first-time setup instead). Then run `python "${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py" ensure-schema <main_worktree>` once (`<main_worktree>` = cwd if in main, else `.ddaro/LOCK` `main_worktree`, else `config.main_worktree`) and show its line if it prints one. Terms: "main worktree" = the folder `config.main_worktree` (receives merges only); `<base>` = `config.base_branch` (default `main`), `origin/<base>` its remote-tracking ref; never hardcode a branch name. Reply in `config.language`. If a ddaro script exits non-zero or python is missing, print `[ddaro] <script> <subcommand> failed (exit N): <first stderr line>` and continue; never hand-write `.ddaro/context/*`, `CURRENT.md`, or the config keys `base_branch` / `auto_snapshot` / `schema_version`.
<!-- /step0 -->

A gate, not a fixer.

1. Diff: `$1` vs `origin/<base>`, or `--staged`, else this worktree's `LOCK.branch` vs `origin/<base>`.
2. prism-all on the diff (correctness, security, regressions, concurrency, data integrity); verify every HIGH+ adversarially (skeptic agents try to refute; keep survivors).
3. Ship checklist from `.claude/CLAUDE.md` + `.claude/rules/`, each rule that applies: tests pass (run them), route-map drift if routes changed, CHANGELOG updated (and its mirror if declared), schema change additive or flagged, no synthetic accounts / secrets / hardcoded config / em-dash where the rules ban them, docs-vs-code drift on touched specs.
4. Verdict BLOCK (every blocker + its one fix) or PASS. PASS -> "/ddaro:commit then /ddaro:merge". Never proceed past a BLOCK.
