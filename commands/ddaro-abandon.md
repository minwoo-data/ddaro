---
name: ddaro:abandon
description: "Force-discard a ddaro-owned worktree even if its commits are unmerged. Requires cwd == main. Tier 1 (owned) only - Tier 2 (adopted) is refused (use git worktree remove --force from main instead). 3-layer protection + typed confirmation."
argument-hint: "<name>"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## /ddaro:abandon <name>" and execute with `$ARGUMENTS` as the required name.

- Refuse if `$ARGUMENTS` is empty.
- **Precondition - cwd must equal `config.main_worktree`**. If not, refuse with:
  ```
  ✗ /ddaro:abandon must run from main.
    cd <config.main_worktree>
    /ddaro:abandon <name>
  ```
  Do not execute any destruction on mismatch.
- **Tier gate - Tier 1 (owned) only**:
  - Target is adopted (LOCK.adopted=true) → refuse, print the git-only recipe:
    ```
    cd <main_worktree>
    git worktree remove --force <path>
    git branch -D <branch>
    # optional: git push origin --delete <branch>
    ```
  - Target is protected / main / unmanaged / external → refuse with a tier-appropriate message.
- **Layer 1**: reject if the target path is in `protected_worktrees` (covered by the tier gate; belt-and-braces).
- **Layer 2**: reject if `<path>/.ddaro/OWNED` is absent or `LOCK.adopted=true` (covered; belt-and-braces).
- **Layer 3**: show destruction preview (commits lost, unpushed count, context snapshots lost, remote branch deletion opt-in), then require the user to type exactly `yes, I'm sure`.
- Execute on full confirmation:
  - `git worktree remove <path> --force`
  - `git branch -D d-<name>`
  - Optional: `git push origin --delete d-<name>` (if user said yes earlier)
- After success, cwd is still main - no stranded shell.
