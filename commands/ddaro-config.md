---
name: ddaro:config
description: "Show or change ddaro settings and hook modes."
argument-hint: "[show|init|migrate|<key> <value>] (merge_gate off|warn|strict)"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
disable-model-invocation: true
---

# /ddaro:config

<!-- step0 -->
**Step 0.** Find `.ddaro/config.json` in cwd or a parent; in a linked worktree with none, use the main worktree's (`git rev-parse --path-format=absolute --git-common-dir`, then its parent). None found: say "not a ddaro project - run /ddaro:start" and stop (`/ddaro:start` runs first-time setup instead). Then run `python "${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py" ensure-schema <main_worktree>` once (`<main_worktree>` = cwd if in main, else `.ddaro/LOCK` `main_worktree`, else `config.main_worktree`) and show its line if it prints one. Terms: "main worktree" = the folder `config.main_worktree` (receives merges only); `<base>` = `config.base_branch` (default `main`), `origin/<base>` its remote-tracking ref; never hardcode a branch name. Reply in `config.language`. If a ddaro script exits non-zero or python is missing, print `[ddaro] <script> <subcommand> failed (exit N): <first stderr line>` and continue; never hand-write `.ddaro/context/*`, `CURRENT.md`, or the config keys `base_branch` / `auto_snapshot` / `schema_version`.
<!-- /step0 -->

No args: numbered menu of language, naming_strategy, name_pool, max_concurrent, warn_threshold, stale_days, context_persistence, protected_worktrees, main_worktree (current values in brackets); each choice opens its sub-menu and saves immediately; `0`/Enter exits.

- `show`: print the config (read-only).
- `init`: rerun "First-time setup" from `${CLAUDE_PLUGIN_ROOT}/reference/config.md`.
- `migrate`: follow `${CLAUDE_PLUGIN_ROOT}/reference/hooks.md` ("/ddaro:config migrate").
- `base_branch <name>` / `auto_snapshot <on|off>` / `merge_gate <off|warn|strict>` / `gate_block_severity <CRIT|HIGH|MED>` / `gate_verify <auto|none>` / `planning_patterns <JSON array>`: `python "${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py" set <main_worktree> <key> <value>` (never edit these by hand). Raising `merge_gate` (off -> warn -> strict) is fine; weakening it, raising `gate_block_severity`, `gate_verify none`, or any `base_branch` change while the gate is on is a person's command: print `! python "${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py" set <main_worktree> <key> <value>` for them (the merge-gate hook blocks it otherwise). Before `merge_gate strict`: `<main_worktree>/.ddaro/verify.json` must exist (test commands, see `${CLAUDE_PLUGIN_ROOT}/reference/config.md`) or a person records `gate_verify none`; other open Claude sessions need a restart.
- `main <path>`, `protect <path>`, `unprotect <path>`, `external <glob>`, `naming <d-number|d-pool|ddaro-number|ddaro-pool>`, `pool <animal|korea_city|us_state|fruit|greek>`, `language <english|korean>`, `context <true|false>`, `max <N>`, `ci_fix_cap <1..10>`, `evidence_token_ttl_seconds <30..86400>`: edit that key in `<main_worktree>/.ddaro/config.json`, keeping every other key.
- Hook modes `main_protection`, `branch_naming`, `branch_worktree_match`, `evidence_check` (`off|warn|strict`), `cross_worktree_check`, `fetch_before_check` (`on|off`): write the key only; meanings and bypass variables in `${CLAUDE_PLUGIN_ROOT}/reference/hooks.md`. Never touch `.claude/settings.json` (except `migrate`).
- Unknown action: list the valid ones. Removing other keys: edit the file by hand.
