# ddaro per-worktree files (`<worktree>/.ddaro/`, git-ignored)

- `OWNED` - empty flag: this worktree is ddaro-managed.
- `LOCK` - `{"branch", "topic", "created_at", "main_worktree", "language"}`; adopted worktrees add `"adopted": true, "original_branch", "adopted_at"`. A LOCK without `adopted` means owned.
- `context/<ts>-<sha7>.md` - one snapshot per commit. `CURRENT.md` - latest state.
- `lifecycle.json` - `/ddaro:go` stage `{stage, doc, updated}`.

Only `${CLAUDE_PLUGIN_ROOT}/hooks/context_md.py` writes `context/*` and `CURRENT.md` (`hook` after every `git commit` made through the Bash tool, `init` from start/adopt, `write <root>` to fill a missed commit, `enrich <root> <sha7>` with stdin JSON from /ddaro:commit). Headings are exact strings; files start with `<!-- ddaro-context v1 -->`.

```markdown
<!-- ddaro-context v1 -->
# d-fox - Commit a1b2c3d

**Time**: 2026-04-23 10:00:00
**Branch**: d-fox
**Ahead of base (<base>)**: 1 commit(s)

## Commit message
<commit message>

## Files changed
N files, +X -Y
- <file1> (+X -Y)

## What was done
<first line of the message until /ddaro:commit enriches it>

## Next planned (inferred)
(auto) run /ddaro:commit to enrich, or /ddaro:resume

## Review flags raised
(auto) not analyzed
```

```markdown
<!-- ddaro-context v1 -->
# d-fox - Current State

**Last updated**: 2026-04-23 12:30:00
**Branch**: d-fox
**Total commits**: 3 ahead of base (<base>)
**Push status**: origin/d-fox up to date
**Uncommit**: none

## Journey so far
1. [10:00] Worktree created, branch d-fox from <base>@<sha7>
2. [11:15] Commit b2c3d4e - <message>

## Currently
(auto) committed b2c3d4e just now

## Resume hint
If this session restarts:
- cwd: <worktree path>
- Last goal: <LOCK.topic>
- Next expected: (auto) see /ddaro:resume
```
