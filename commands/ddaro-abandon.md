---
name: ddaro:abandon
description: "Force-discard a ddaro-managed worktree (owned or adopted) even if its commits are unmerged. Requires cwd == main. 3-layer protection + typed confirmation. Adopted targets require explicit --force (extra guard since the branch may pre-exist the adopt)."
argument-hint: "<name> [--force] [--delete-remote]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## /ddaro:abandon <name>" and execute with `$ARGUMENTS` as name + flags.

- Refuse if `$ARGUMENTS` is empty or no `<name>` positional given.
- **Precondition — cwd must equal `config.main_worktree`**. If not, refuse with:
  ```
  ✗ /ddaro:abandon must run from main.
    cd <config.main_worktree>
    /ddaro:abandon <name>
  ```
  Do not execute any destruction on mismatch.
- **Tier gate**:
  - Target is **Tier 1 (owned)** → proceed to 3-layer.
  - Target is **Tier 2 (adopted)** → require `--force` flag. Without it, refuse with:
    ```
    ✗ <name> is adopted (its branch existed before ddaro took over).
      If you really want to discard it, re-run with:

        /ddaro:abandon <name> --force

      This will delete the worktree, the branch, and (with --delete-remote) the remote branch.
    ```
    With `--force`, continue to 3-layer with an extra banner "ADOPTED target — original_branch: <LOCK.original_branch>" in the preview.
  - Target is protected / main / unmanaged / external → refuse with a tier-appropriate message.
- **Layer 1**: reject if the target path is in `protected_worktrees` (belt-and-braces; usually caught by tier gate).
- **Layer 2**: reject if `<path>/.ddaro/OWNED` is absent AND LOCK has no `adopted=true` (not a ddaro-managed path at all).
- **Layer 3**: show destruction preview (commits lost, unpushed count, context snapshots lost, adopted-flag banner if applicable, remote branch deletion opt-in via `--delete-remote`), then require the user to type exactly `yes, I'm sure`.
- Execute on full confirmation:
  - `git worktree remove <path> --force`
  - `git branch -D <branch>` (branch name from LOCK.branch; for owned it's `d-<name>`, for adopted it's the original name)
  - If `--delete-remote` or user opted in during Layer 3: `git push origin --delete <branch>`
- After success, cwd is still main — no stranded shell.
