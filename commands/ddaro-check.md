---
name: ddaro:check
description: "Pre-merge gate: tests, then prism on the diff -> PASS/BLOCK (scripted when merge_gate is on)."
argument-hint: "[--full] (merge_gate off: [branch|--staged])"
allowed-tools: [Bash, Read, Glob, Grep, Agent, Skill]
disable-model-invocation: true
---

# /ddaro:check

<!-- step0 -->
**Step 0.** Find `.ddaro/config.json` in cwd or a parent; in a linked worktree with none, use the main worktree's (`git rev-parse --path-format=absolute --git-common-dir`, then its parent). None found: say "not a ddaro project - run /ddaro:start" and stop (`/ddaro:start` runs first-time setup instead). Then run `python "${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py" ensure-schema <main_worktree>` once (`<main_worktree>` = cwd if in main, else `.ddaro/LOCK` `main_worktree`, else `config.main_worktree`) and show its line if it prints one. Terms: "main worktree" = the folder `config.main_worktree` (receives merges only); `<base>` = `config.base_branch` (default `main`), `origin/<base>` its remote-tracking ref; never hardcode a branch name. Reply in `config.language`. If a ddaro script exits non-zero or python is missing, print `[ddaro] <script> <subcommand> failed (exit N): <first stderr line>` and continue; never hand-write `.ddaro/context/*`, `CURRENT.md`, or the config keys `base_branch` / `auto_snapshot` / `schema_version`.
<!-- /step0 -->

A gate, not a fixer. Read `merge_gate` from `<main_worktree>/.ddaro/config.json` only (a nearer config never counts).

**`merge_gate` warn or strict** (scripted gate, 0.10.0). `<wt>` = this worktree's root. `$1` and `--staged` are not accepted here; the only flag is `--full`.
1. `python "${CLAUDE_PLUGIN_ROOT}/hooks/gate.py" check-begin <wt> [--full]` (Bash timeout 600000: it runs the project's tests first). If the JSON has `finalized`, show those entries first. If `outcome` is not `OK`, print its `summary` lines verbatim and stop (REFUSED, a test BLOCK, or a tests-only PASS all end here).
2. Call the **Skill tool** with skill `prism:prism` and args = the `prism_skill_args` string from step 1, byte for byte: add nothing, remove nothing. No `prism_skill_args` key -> skip 2 and 3.
3. `python "${CLAUDE_PLUGIN_ROOT}/hooks/gate.py" check-record <wt> --run <run>` (`run` from step 1).
4. Print the script's `summary` lines verbatim; never summarize, soften or rewrite the verdict. PASS -> "next: /ddaro merge". BLOCK -> fix, commit, `/ddaro check` again. STALE or ERROR -> `/ddaro check` again. Never proceed past a BLOCK; approvals and gate changes are a person's `!` commands (`${CLAUDE_PLUGIN_ROOT}/reference/config.md`).

**`merge_gate` off** (unchanged flow):
1. Diff: `$1` vs `origin/<base>`, or `--staged`, else this worktree's `LOCK.branch` vs `origin/<base>`.
2. prism-all on the diff with `--no-ideas` (a gate wants defects only; prism >= 0.5.0 would otherwise add its idea pass) (correctness, security, regressions, concurrency, data integrity); verify every HIGH+ adversarially (skeptic agents try to refute; keep survivors).
3. Ship checklist from `.claude/CLAUDE.md` + `.claude/rules/`, each rule that applies: tests pass (run them), route-map drift if routes changed, CHANGELOG updated (and its mirror if declared), schema change additive or flagged, no synthetic accounts / secrets / hardcoded config / em-dash where the rules ban them, docs-vs-code drift on touched specs.
4. Verdict BLOCK (every blocker + its one fix) or PASS. PASS -> "/ddaro:commit then /ddaro:merge". Never proceed past a BLOCK.
