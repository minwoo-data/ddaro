---
name: ddaro:start
description: "Create a new isolated worktree + branch for one session (first run: setup)."
argument-hint: "[name] [topic]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
disable-model-invocation: true
---

# /ddaro:start

<!-- step0 -->
**Step 0.** Find `.ddaro/config.json` in cwd or a parent; in a linked worktree with none, use the main worktree's (`git rev-parse --path-format=absolute --git-common-dir`, then its parent). None found: say "not a ddaro project - run /ddaro:start" and stop (`/ddaro:start` runs first-time setup instead). Then run `python ${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py ensure-schema <main_worktree>` once (`<main_worktree>` = cwd if in main, else `.ddaro/LOCK` `main_worktree`, else `config.main_worktree`) and show its line if it prints one. Terms: "main worktree" = the folder `config.main_worktree` (receives merges only); `<base>` = `config.base_branch` (default `main`), `origin/<base>` its remote-tracking ref; never hardcode a branch name. Reply in `config.language`. If a ddaro script exits non-zero or python is missing, print `[ddaro] <script> <subcommand> failed (exit N): <first stderr line>` and continue; never hand-write `.ddaro/context/*`, `CURRENT.md`, or the config keys `base_branch` / `auto_snapshot` / `schema_version`.
<!-- /step0 -->

Run from the main worktree. With a config and cwd != `config.main_worktree`, refuse and print `cd <main_worktree>` + `/ddaro:start`. With no config, run "First-time setup" in `${CLAUDE_PLUGIN_ROOT}/reference/config.md` first.

1. **Existing worktrees** (classify per `${CLAUDE_PLUGIN_ROOT}/reference/tiers.md` order: main, external, protected, OWNED -> adopted/owned, unmanaged). Owned/adopted: offer `/ddaro:resume <name>` instead (if chosen, stop). Unmanaged: per entry offer `/ddaro:adopt <path>` / finish in place (print cd + `git status`) / ignore (default; never auto-adopt).
2. **Limits**: refuse at `max_concurrent` owned+adopted; at `warn_threshold` warn and list entries older than `stale_days`.
3. **Dirty main**: split uncommitted files into planning (`planning_patterns`) and code, show both, offer 1) commit all first (default) 2) commit planning only 3) carry code over (stash, create, stash pop inside) 4) start anyway (they stay on main) 5) cancel. Unpushed commits on main: warn once, do not block.
4. **Name**: given -> slugify; else per `naming_strategy` (`d-number`: next number never used before; `d-pool`: first unused `name_pools[name_pool]` entry; `ddaro-*`: same with prefix `ddaro-`). Collision -> `-2`, `-3`. Branch `<prefix><name>`, folder `<main_worktree>/../<project>-<prefix><name>` (prefix `d-` or `ddaro-`).
5. **Topic**: one line from the user (ask if not given).
6. **Create** (anchored to main, never cwd):
```bash
git -C <main_worktree> worktree add <main_worktree>/../<project>-d-<name> -b d-<name> <base>
```
7. **Plant**: `mkdir -p <wt>/.ddaro/context`, `touch <wt>/.ddaro/OWNED`, write `<wt>/.ddaro/LOCK` = `{"branch", "topic", "created_at", "main_worktree", "language"}`, append `.ddaro/` to `<main_worktree>/.gitignore` if that line is missing, then `python ${CLAUDE_PLUGIN_ROOT}/hooks/context_md.py init <wt> --topic "<topic>"`.
8. **Report**:
```
✓ Worktree created: <path>
✓ Branch:           d-<name>

Next (new terminal):
  cd <path>
  claude
Paste: Continue work on d-<name>. topic: <topic>
```
Add: "edit -> /ddaro:commit -> /ddaro:merge; after a crash or days later: /ddaro:resume".
