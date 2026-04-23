---
name: ddaro:resume
description: "Pick a ddaro worktree (owned OR adopted) to re-enter, with an auto-generated recap + cd instructions + paste-ready prompt. For crash recovery or days-later returns. Pass --recap-only to just print the summary without the cd/paste block (replaces the former /ddaro:summary)."
argument-hint: "[name] [--recap-only] [--all]"
allowed-tools: [Bash, Read, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## /ddaro:resume" and execute with `$ARGUMENTS` as optional name + flags.

- Scan **both Tier 1 (ddaro-owned) and Tier 2 (adopted)** worktrees and classify each:
  - `active` - uncommit present (edit in progress)
  - `ready`  - all committed + pushed, waiting on /ddaro:merge
  - `stale`  - older than stale_days (from config)
  - `merged` - already merged; surface but suggest /ddaro:clear instead of resume
- Show a numbered picker listing each resumable worktree with short status, plus a 'cancel' option and an 'all' option for one-line recap of every worktree.
- **If `$ARGUMENTS` contains `--all`**, skip the picker and print the one-line recap for every worktree directly.
- **If a `[name]` is given as positional arg**, skip the picker and resume that worktree directly.
- On user selection of one worktree (or direct-name path):
  1. Build the recap from these sources (this is the former `/ddaro:summary` logic, now inline):
     - `git log main..HEAD` commit messages
     - `git diff --stat main..HEAD`
     - `.ddaro/context/*.md` "What was done" sections
     - `.ddaro/CURRENT.md` Resume hint
     - `git status --porcelain` for uncommit
  2. Validate lock file against current branch; warn on mismatch but continue if user confirms.
  3. Print a resume block containing:
     - Branch, topic, created_at
     - Progress (commits, uncommit files, push state)
     - "Where you stopped" (last commit message, uncommit files, inferred next step from TODOs / unfinished tests)
     - "Next recommended" command list (typically /ddaro:commit for active, /ddaro:merge for ready, /ddaro:clear for merged)
     - **Unless `--recap-only`** — "Copy-paste to resume" block with:
         cd <worktree-path>
         claude
       followed by a paste-ready prompt that restates the topic + last state + next planned step.
- On user selection 'all' (or `--all` flag): print a 1-2 line recap per worktree, no paste prompts.
- `--recap-only` + `[name]`: print the detailed recap only (no cd/paste). Used when the user just wants to know where a worktree stands without re-entering it.
- Edge cases:
  - No ddaro-managed worktrees (owned + adopted both empty) -> print "Nothing to resume. Use /ddaro:start to begin new work."
  - cwd already inside a ddaro worktree -> warn that /ddaro:status may fit better; continue with picker if user confirms.
  - cwd is main_worktree -> normal picker (most common entry).
  - Selected worktree has no .ddaro/context/ (manually deleted or context_persistence=false) -> rebuild recap from git log only, flag "context unavailable".
  - Lock file disagrees with current branch of the worktree -> warn, show discrepancy, proceed only on user confirmation.
