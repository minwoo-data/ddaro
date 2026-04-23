---
name: ddaro:adopt
description: "Bring an existing non-ddaro worktree under ddaro management. Plants .ddaro/ overlay without renaming branch, moving files, or recreating the worktree. Marks LOCK as adopted=true so /ddaro:abandon is refused for safety; /ddaro:clear still works normally once merged."
argument-hint: "<path>"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## /ddaro:adopt <path>" and execute with `$ARGUMENTS` as the required path.

- Refuse if `$ARGUMENTS` is empty — print "/ddaro:adopt <path>" usage hint.
- **Path validation**: must be a real `git worktree list` entry. If not, stop with an error.
- **Tier check** — refuse in any of these cases, printing the tier and a remediation suggestion:
  - Target path equals `config.main_worktree` → "main can't be adopted; it's the receiver by design"
  - Target path is in `config.protected_worktrees` → "run /ddaro:config unprotect <path> first if you mean it"
  - Target path matches any glob in `config.external_patterns` (e.g. `.claude/worktrees/agent-*`) → "owned by another tool; ddaro won't touch"
  - Target already has `<path>/.ddaro/OWNED` → "already ddaro-managed; use /ddaro:status"
- **State snapshot**: inspect and display (branch, commits ahead of main, uncommitted count, push status).
- **Topic prompt**: ask the user for a short topic string (`LOCK.topic`). User-typed, not auto-generated.
- **Plant ddaro files** (none of this mutates the user's code):
  - `mkdir <path>/.ddaro/context/`
  - `touch <path>/.ddaro/OWNED`
  - Write `<path>/.ddaro/LOCK` as JSON with `branch`, `topic`, `created_at`, `main_worktree`, `language`, and `adopted: true`, `original_branch: <same branch name>`, `adopted_at: <now>`.
  - Append `.ddaro/` to `<main_worktree>/.gitignore` if the line is not already there (shared with `/ddaro:start`).
  - Write initial `<path>/.ddaro/CURRENT.md` noting "adopted from external worktree".
- **Output summary**: confirm path + branch + state + list of ddaro commands now applicable. Remind that `/ddaro:abandon` is refused for adopted worktrees (force-discard via `git worktree remove --force` from main).

After adopt, the worktree is Tier 2. `/ddaro:commit`, `/ddaro:merge`, `/ddaro:resume`, `/ddaro:clear` all treat it identically to a Tier 1 owned worktree. Only `/ddaro:abandon` refuses.
