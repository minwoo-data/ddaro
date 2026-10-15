---
name: ddaro:adopt
description: "Bring an existing non-ddaro worktree under ddaro without touching its code."
argument-hint: "<path>"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
disable-model-invocation: true
---

# /ddaro:adopt

<!-- step0 -->
**Step 0.** Find `.ddaro/config.json` in cwd or a parent; in a linked worktree with none, use the main worktree's (`git rev-parse --path-format=absolute --git-common-dir`, then its parent). None found: say "not a ddaro project - run /ddaro:start" and stop (`/ddaro:start` runs first-time setup instead). Then run `python "${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py" ensure-schema <main_worktree>` once (`<main_worktree>` = cwd if in main, else `.ddaro/LOCK` `main_worktree`, else `config.main_worktree`) and show its line if it prints one. Terms: "main worktree" = the folder `config.main_worktree` (receives merges only); `<base>` = `config.base_branch` (default `main`), `origin/<base>` its remote-tracking ref; never hardcode a branch name. Reply in `config.language`. If a ddaro script exits non-zero or python is missing, print `[ddaro] <script> <subcommand> failed (exit N): <first stderr line>` and continue; never hand-write `.ddaro/context/*`, `CURRENT.md`, or the config keys `base_branch` / `auto_snapshot` / `schema_version`.
<!-- /step0 -->

`<path>` is required (else print the usage). Adopt never renames the branch, moves files, or runs git writes; it only plants `.ddaro/`.

1. `<path>` must be a `git worktree list` entry. Refuse (say why and what to do) if it is the main worktree ("main is the receiver"), in `protected_worktrees` ("`/ddaro:config unprotect <path>` first"), matches `external_patterns` ("owned by another tool"), or already has `.ddaro/OWNED` ("already managed; /ddaro:status").
2. Show: path, branch (kept as-is), commits ahead of `<base>`, uncommitted count, push state.
3. Ask the user for a one-line topic.
4. Plant: `mkdir -p <path>/.ddaro/context`, `touch <path>/.ddaro/OWNED`, write `<path>/.ddaro/LOCK` = `{"branch", "topic", "created_at", "main_worktree", "language", "adopted": true, "original_branch": <branch>, "adopted_at"}`, append `.ddaro/` to `<main_worktree>/.gitignore` if missing, then `python "${CLAUDE_PLUGIN_ROOT}/hooks/context_md.py" init <path> --topic "<topic>" --adopted`.
5. Report the summary and that `/ddaro:commit`, `/ddaro:merge`, `/ddaro:resume`, `/ddaro:clear` now apply; `/ddaro:abandon` needs `--force` for adopted worktrees (or plain `git worktree remove --force <path>` from main).
