---
name: ddaro:merge
description: "Merge ddaro branch to main with pre-flight conflict check, size-based review (triad/prism), pure-deletion scan, and y/n cleanup of worktree + branch."
argument-hint: "[--review=auto|skip|triad|prism|mangchi] [--local] [--pr]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## `/ddaro merge`" and execute with `$ARGUMENTS` as flags.

- Validate lock.
- If uncommitted changes exist, offer: (a) `/ddaro:commit` first (recommended), (b) stash + merge + pop, (c) abort.
- `git fetch origin`.
- Dry-run merge with `git merge-tree` base HEAD origin/main. If conflicts, list files and stop.
- Measure diff size (`main..HEAD`):
  - small (<50 lines, ≤2 files) → deletion re-confirm only
  - medium (50-300 lines, 3-10 files) → deletion re-confirm + size warning
  - large (>300 lines or >10 files) → deletion re-confirm + size warning + pure-deletion re-scan
  - `--review=<triad|prism>` (optional, opt-in): if the named plugin is installed on disk, pass the diff to it. If not installed, stop and print install hint. Never auto-invoked from size band alone.
- Scan pure deletions across `main..HEAD`.
- Final `y/n` to user.
- Merge method: default `gh pr create` (PR path) unless `--local` (switch to main worktree + provide copy-paste merge prompt).
- After merge success, ask `y/n` to clean up worktree:
  - `y` (default): `git branch -d d-<name>`, `git push origin --delete d-<name>`, `git worktree remove <path>`
  - `n`: keep worktree, advise `/ddaro:clear` later
- Optional hint: if the `prism` plugin is installed (check existence of `${HOME}/.claude/plugins/cache/haroom_plugins/prism/` or `${HOME}/.claude/skills/prism/`), append a one-line suggestion before the final y/n:
  "`Tip: for a deeper multi-angle review of this diff, run /prism after merging.`"
  This is purely informational - ddaro never calls prism and does not require it installed.
