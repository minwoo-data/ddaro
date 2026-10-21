---
name: ddaro:merge
description: "Ship the branch: conflict pre-check, size check, PR through CI, squash, sync."
argument-hint: "[--local] [--review=prism|triad] (gate: PASS for the head commit required)"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, Agent]
disable-model-invocation: true
---

# /ddaro:merge

<!-- step0 -->
**Step 0.** Find `.ddaro/config.json` in cwd or a parent; in a linked worktree with none, use the main worktree's (`git rev-parse --path-format=absolute --git-common-dir`, then its parent). None found: say "not a ddaro project - run /ddaro:start" and stop (`/ddaro:start` runs first-time setup instead). Then run `python "${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py" ensure-schema <main_worktree>` once (`<main_worktree>` = cwd if in main, else `.ddaro/LOCK` `main_worktree`, else `config.main_worktree`) and show its line if it prints one. Terms: "main worktree" = the folder `config.main_worktree` (receives merges only); `<base>` = `config.base_branch` (default `main`), `origin/<base>` its remote-tracking ref; never hardcode a branch name. Reply in `config.language`. If a ddaro script exits non-zero or python is missing, print `[ddaro] <script> <subcommand> failed (exit N): <first stderr line>` and continue; never hand-write `.ddaro/context/*`, `CURRENT.md`, or the config keys `base_branch` / `auto_snapshot` / `schema_version`.
<!-- /step0 -->

Run inside the owned/adopted worktree being shipped. **Lock check**: if the checked-out branch differs from `.ddaro/LOCK` `branch`, show both and ask y/n (default abort). Never delete this worktree here; cleanup is `/ddaro:clear` from main.

**Gate** (only when `<main_worktree>/.ddaro/config.json` has `merge_gate` warn or strict; `<main>` = that folder, `<branch>` = `LOCK.branch`): `python "${CLAUDE_PLUGIN_ROOT}/hooks/gate.py" status <main> --branch <branch>`. Print its `summary` verbatim. `mergeable` false -> show `next` and stop (the usual answer is `/ddaro check`). Steps 1, 7, 8, 9 below have gate variants marked **(gate)**.

1. Uncommitted changes -> offer `/ddaro:commit` first (default) / stash, merge, pop / abort. **(gate)** do not commit for the user: print "commit -> /ddaro check -> /ddaro merge" and stop.
2. `git fetch origin`. Conflict dry-run: `git merge-tree $(git merge-base HEAD origin/<base>) HEAD origin/<base>`; conflicts -> list files, stop (rebase or resolve first).
3. Size of `<base>..HEAD`: small (<=50 lines and <=2 files), medium (<=300 lines and <=10 files), large (otherwise). All sizes: re-confirm any pure deletions; medium/large: print a size warning; large: re-scan the whole diff for anything that exists on `<base>` and disappears.
4. `--review=prism`: if installed (`~/.claude/plugins/cache/haroom_plugins/prism/` or `~/.claude/skills/prism/`) run `/prism --diff <base>...HEAD`. `--review=triad`: only the markdown files the diff touches (code-only diff: say so, suggest prism). Not installed: print `/plugin marketplace add https://github.com/minwoo-data/haroom_plugins.git` + `/plugin install <name>` and stop. Never run a review that was not asked for.
5. Final y/n.
6. `--local`: print `cd <main_worktree>`, `git merge <branch>`, `git push` for the user and stop. **(gate)** strict: a local merge bypasses the gate; only print the commands as a person's path and stop.
7. **PR path**: reuse an open PR (`gh pr list --head <branch> --state open`) or `gh pr create --base <base>` (body may include the CURRENT.md Journey; **(gate)** always write the body to a temp file and pass `--body-file`). Poll `gh pr view <N> --json statusCheckRollup,mergeStateStatus` every 20 s, one progress line each, 20 min cap. **(gate)** the check set is `statusCheckRollup` minus any `ddaro/check` entry; an auto-merge PR is handled commit -> `/ddaro check` -> push:
   - no checks after 60 s -> CI_STUCK: offer `w` wait 60 s more / `d` `gh workflow run` / `e` stop with the PR URL (does not count as a fix attempt).
   - any failure -> show each failed check, offer `a` analyze (`gh run view --log-failed`), propose a fix, apply after confirm, commit it per `${CLAUDE_PLUGIN_ROOT}/commands/ddaro-commit.md`, `git push --force-with-lease`, poll again (max `config.ci_fix_cap`, default 3, then only s/e) / `s` print the `gh pr merge --admin` command for the user / `e` stop with the PR URL. **(gate)** after a fix commit is pushed, stop with "재확인 필요: /ddaro check, then /ddaro merge (resumes at step 8)".
   - all success -> step 8.
8. Re-check `gh pr view <N> --json state`; already MERGED -> skip to 9. **(gate)** read `headRefOid` too and run `python "${CLAUDE_PLUGIN_ROOT}/hooks/gate.py" status <main> --branch <branch> --head <headRefOid>`; not `mergeable` -> show `next`, stop; `questions` present -> print "확인되지 않은 의심 N건" with each severity / location / claim before asking. Then print `gh pr merge <N> --squash --delete-branch=false` (**(gate)** `... --match-head-commit <headRefOid>`; keep the user's merge method flag if they chose another), branch -> `<base>`, commits, `+X -Y` and ask "Proceed? [y/n] (default n)". `n` = stop.
9. **Sync preview**: after the squash, show squash sha vs local head, files differing between `origin/<base>` and the branch, and files the branch has that `origin/<base>` lacks (non-empty = the work is not in the squash: stop and investigate). Ask "Reset local branch to origin/<base>? [y/n] (default y)"; on y: `git fetch origin <base> && git reset --hard origin/<base>` (the only reset ddaro does outside abandon). **(gate)** then `python "${CLAUDE_PLUGIN_ROOT}/hooks/gate.py" close <main> <branch> --merged --pr <N>` and show its line. Then print:
```
Cleanup must run from the main worktree:
    cd <main_worktree>
    /ddaro:clear <name>
```
Any re-run after an error re-queries the PR first and skips steps already done. All pushes here use `--force-with-lease`, never `--force`.
