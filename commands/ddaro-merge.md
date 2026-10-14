---
name: ddaro:merge
description: "Ship the branch: conflict pre-check, size check, PR through CI, squash, sync."
argument-hint: "[--local] [--review=prism|triad]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, Agent]
disable-model-invocation: true
---

# /ddaro:merge

<!-- step0 -->
**Step 0.** Find `.ddaro/config.json` in cwd or a parent; in a linked worktree with none, use the main worktree's (`git rev-parse --path-format=absolute --git-common-dir`, then its parent). None found: say "not a ddaro project - run /ddaro:start" and stop (`/ddaro:start` runs first-time setup instead). Then run `python ${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py ensure-schema <main_worktree>` once (`<main_worktree>` = cwd if in main, else `.ddaro/LOCK` `main_worktree`, else `config.main_worktree`) and show its line if it prints one. Terms: "main worktree" = the folder `config.main_worktree` (receives merges only); `<base>` = `config.base_branch` (default `main`), `origin/<base>` its remote-tracking ref; never hardcode a branch name. Reply in `config.language`. If a ddaro script exits non-zero or python is missing, print `[ddaro] <script> <subcommand> failed (exit N): <first stderr line>` and continue; never hand-write `.ddaro/context/*`, `CURRENT.md`, or the config keys `base_branch` / `auto_snapshot` / `schema_version`.
<!-- /step0 -->

Run inside the owned/adopted worktree being shipped. **Lock check**: if the checked-out branch differs from `.ddaro/LOCK` `branch`, show both and ask y/n (default abort). Never delete this worktree here; cleanup is `/ddaro:clear` from main.

1. Uncommitted changes -> offer `/ddaro:commit` first (default) / stash, merge, pop / abort.
2. `git fetch origin`. Conflict dry-run: `git merge-tree $(git merge-base HEAD origin/<base>) HEAD origin/<base>`; conflicts -> list files, stop (rebase or resolve first).
3. Size of `<base>..HEAD`: small (<=50 lines and <=2 files), medium (<=300 lines and <=10 files), large (otherwise). All sizes: re-confirm any pure deletions; medium/large: print a size warning; large: re-scan the whole diff for anything that exists on `<base>` and disappears.
4. `--review=prism`: if installed (`~/.claude/plugins/cache/haroom_plugins/prism/` or `~/.claude/skills/prism/`) run `/prism --diff <base>...HEAD`. `--review=triad`: only the markdown files the diff touches (code-only diff: say so, suggest prism). Not installed: print `/plugin marketplace add https://github.com/minwoo-data/haroom_plugins.git` + `/plugin install <name>` and stop. Never run a review that was not asked for.
5. Final y/n.
6. `--local`: print `cd <main_worktree>`, `git merge <branch>`, `git push` for the user and stop.
7. **PR path**: reuse an open PR (`gh pr list --head <branch> --state open`) or `gh pr create --base <base>` (body may include the CURRENT.md Journey). Poll `gh pr view <N> --json statusCheckRollup,mergeStateStatus` every 20 s, one progress line each, 20 min cap:
   - no checks after 60 s -> CI_STUCK: offer `w` wait 60 s more / `d` `gh workflow run` / `e` stop with the PR URL (does not count as a fix attempt).
   - any failure -> show each failed check, offer `a` analyze (`gh run view --log-failed`), propose a fix, apply after confirm, commit it per `${CLAUDE_PLUGIN_ROOT}/commands/ddaro-commit.md`, `git push --force-with-lease`, poll again (max `config.ci_fix_cap`, default 3, then only s/e) / `s` print the `gh pr merge --admin` command for the user / `e` stop with the PR URL.
   - all success -> step 8.
8. Re-check `gh pr view <N> --json state`; already MERGED -> skip to 9. Else print `gh pr merge <N> --squash --delete-branch=false`, branch -> `<base>`, commits, `+X -Y` and ask "Proceed? [y/n] (default n)". `n` = stop.
9. **Sync preview**: after the squash, show squash sha vs local head, files differing between `origin/<base>` and the branch, and files the branch has that `origin/<base>` lacks (non-empty = the work is not in the squash: stop and investigate). Ask "Reset local branch to origin/<base>? [y/n] (default y)"; on y: `git fetch origin <base> && git reset --hard origin/<base>` (the only reset ddaro does outside abandon). Then print:
```
Cleanup must run from the main worktree:
    cd <main_worktree>
    /ddaro:clear <name>
```
Any re-run after an error re-queries the PR first and skips steps already done. All pushes here use `--force-with-lease`, never `--force`.
