---
name: ddaro:check
description: "Pre-merge review-list gate on the implementation diff: fire prism-all on the changes (bugs/security/regressions) + run the project ship checklist (tests, route-map drift, CHANGELOG sync, schema-additive, project rules), then BLOCK or PASS. On PASS, hand off to /ddaro:commit + /ddaro:merge. Back half of the dev cycle."
argument-hint: "[branch|--staged] - default: this worktree's branch vs main"
allowed-tools: [Agent, Bash, Read, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## /ddaro:check [branch]" and execute with `$ARGUMENTS`.

- Resolve the diff: `$1` branch vs main, or `--staged`, else current `d-<name>` branch vs `origin/main`.
- Fire prism-all on the diff (focus: correctness, security, regressions, concurrency, data integrity). Adversarially verify each HIGH+ before reporting.
- Run the SHIP CHECKLIST, discovering project rules from `.claude/CLAUDE.md` + `.claude/rules/`:
  - tests pass (run the project test command);
  - route-map drift (if `src/routes` or `app.py` touched -> regenerate + diff);
  - CHANGELOG updated AND its central mirror synced (if the project declares one);
  - schema change is additive (no data-rewrite that blocks auto-promote) or flagged;
  - no synthetic test accounts / no secrets / no em-dash / config not hardcoded (per rules);
  - docs-vs-code drift on any touched spec.
- Verdict: **BLOCK** (list every blocker + the one fix each) or **PASS**.
- On PASS, recommend / hand off to `/ddaro:commit` then `/ddaro:merge`. Never auto-merge on BLOCK.
- Output: the verdict table + blocker list. This is a gate, not a fixer - it reports, the operator (or a follow-up) fixes.
