---
name: ddaro
description: "Worktree-based parallel workflow. Create isolated worktree + branch, commit with deletion-aware checks, review and merge to main by diff size, recover from session/IDE crashes via per-commit context MD. Subcommands: start / resume / commit / merge / clear / status / list / summary / abandon / setting / config. Language: english or korean (config). Korean triggers: 따로, 병렬로, 분리해서, main 건드리지 마. English: parallel, isolated, separate branch."
version: "0.2.1"
author: "haroom"
repository: "https://github.com/minwoo-data/ddaro"
license: "MIT"
---

# /ddaro - Worktree-Based Parallel Workflow

> Isolated work. Deletion-aware commits. Size-based merge review. Crash-recoverable context.

Main worktree is never touched. Work happens in dedicated worktrees, one branch each, with lock files and on-disk context snapshots. Designed for parallel Claude Code sessions that must not stomp on each other.

**Design principle**: 1 worktree = 1 branch = 1 Claude session. Physical isolation prevents file collisions. Context MDs survive VS Code crashes and session restarts.

---

## Why this exists

Running two Claude Code sessions at once on the same repo? They both write to the working tree and overwrite each other's edits. Close VS Code mid-task? The plan Claude had in its head is gone. ddaro fixes both:

- Each session gets its own isolated folder (a git worktree on its own branch). Two sessions can edit in parallel without collisions.
- Every commit writes a plain-text recap to disk, so a new session can pick up where the last one died.

A **git worktree** is a second working folder that shares the same repository but checks out a different branch - so two Claude sessions can edit independently without flipping branches back and forth.

---

## Quick start

```
/ddaro:start                     # creates isolated worktree + branch (e.g. d-1)
                                 # first run prompts a 5-step setup
cd <project>-d-1                 # open in a new terminal
claude                           # start a Claude Code session there

# ... edit code ...

/ddaro:commit "fix login bug"    # safe commit + push + context snapshot
/ddaro:merge                     # size-based review -> PR -> cleanup
```

First-time users: `/ddaro:start` walks you through the 5-step setup on first invocation.

---

## Commands (frequency order)

| Command | Purpose | When |
|---|---|---|
| `/ddaro:start [name]` | Create worktree + branch + lock | Starting new work |
| `/ddaro:commit [msg]` | Safe commit + push + context snapshot | After each edit chunk (repeat) |
| `/ddaro:merge` | Pre-flight check + review + merge + cleanup | Work complete |
| `/ddaro:status` | Current worktree state | Quick check |
| `/ddaro:list` | All ddaro worktrees, technical state | Overview |
| `/ddaro:summary [name]` | Content recap from commits + context | Read-only "what did I do?" |
| `/ddaro:resume` | Pick a worktree + recap + cd + paste prompt | Crash recovery / returning after days |
| `/ddaro:clear [name]` | Delete merged worktree post-hoc | After `merge` with "keep" choice |
| `/ddaro:abandon <name>` | 3-layer guarded force-discard | Work went wrong |
| `/ddaro:setting` | Interactive settings menu | Browse and change config |
| `/ddaro:config [key] [val]` | Direct config access | Known key, fast change |

Also callable as `/ddaro <subcommand> [args]`.

---

## Naming Convention

- **Worktree folder**: `<project>-d-<name>` (e.g. `myapp-d-1`, `myapp-d-fox`)
- **Branch**: `d-<name>` (e.g. `d-1`, `d-fox`) - identical `<name>` as the worktree
- **Default `<name>`**: auto-incrementing number (1, 2, …). Not reused after cleanup - next gets the next number.
- **Optional `<name>`**: user-supplied - animal, place, topic slug, anything.
- **No dates in names**: git log + context MDs already track time.

### Naming strategies (configurable)

| Strategy key | Default name example |
|---|---|
| `d-number` (default) | `d-1`, `d-2` |
| `d-pool` | Uses `name_pool` (e.g. `d-seoul`, `d-fox`) |
| `ddaro-number` | `ddaro-1`, `ddaro-2` |
| `ddaro-pool` | `ddaro-seoul`, `ddaro-fox` |

### Name pools (used only when strategy is `-pool`)

| Pool key | Examples | Size |
|---|---|---|
| `animal` | otter, panda, fox | 18 |
| `korea_city` (default pool) | seoul, busan, pohang | 20 |
| `us_state` | ca, ny, tx | 20 |
| `fruit` | peach, kiwi, mango | 10 |
| `greek` | alpha, beta, gamma | 10 |

Change via `/ddaro:setting` or `/ddaro:config naming <key>` / `/ddaro:config pool <key>`.

---

## Config File

**Path**: `<main worktree>/.ddaro/config.json`

```json
{
  "schema_version": 1,
  "main_worktree": "C:\\path\\to\\myapp",
  "project_name": "myapp",
  "protected_worktrees": [
    "C:\\path\\to\\myapp",
    "C:\\path\\to\\myapp-experiments"
  ],
  "max_concurrent": 10,
  "warn_threshold": 5,
  "stale_days": 7,
  "naming_strategy": "d-number",
  "name_pool": "korea_city",
  "name_pools": {
    "animal": ["otter","panda","fox","owl","seal","koala","squirrel","whale","hedgehog","penguin","sloth","beaver","rabbit","finch","bear","wolf","deer","mole"],
    "korea_city": ["seoul","busan","incheon","daegu","daejeon","gwangju","ulsan","suwon","jeju","pohang","gyeongju","jeonju","andong","chuncheon","gangneung","mokpo","sokcho","yeosu","tongyeong","jinju"],
    "us_state": ["ca","ny","tx","fl","wa","or","co","az","ma","il","pa","oh","mi","ga","nc","va","nj","tn","in","md"],
    "fruit": ["peach","kiwi","mango","plum","lime","berry","fig","guava","lychee","apricot"],
    "greek": ["alpha","beta","gamma","delta","epsilon","zeta","eta","theta","iota","kappa"]
  },
  "language": "english",
  "context_persistence": true
}
```

### Field reference

- **`schema_version`**: integer, currently `1`. Required for future migrations; on load, if the value does not match the current schema, ddaro runs a named migration before use.
- **`main_worktree`**: absolute path to the clean main-branch worktree. ddaro never mutates this.
- **`protected_worktrees`**: paths ddaro will refuse to create in or delete. Auto-populated during init setup plus sibling folders user flags.
- **`max_concurrent`**: hard ceiling. `/ddaro:start` rejects beyond this.
- **`warn_threshold`**: soft warning at this count.
- **`stale_days`**: `/ddaro:list` marks worktrees older than this as `STALE`.
- **`naming_strategy`** + **`name_pool`**: control auto-generated names.
- **`language`**: `english` (default) or `korean`. Affects all subcommand output.
- **`context_persistence`**: `true` (default) writes `.ddaro/context/*.md` per commit.

If config is missing, **the first `/ddaro:start` triggers the 5-step setup prompt**.

---

## 3-Layer Protection

Why three layers? Because `abandon` and `clear` delete real work, and a single confirmation has caused data loss in practice. Each layer catches a different mistake (wrong path, wrong kind of worktree, wrong intent). Before any destructive operation (worktree remove, branch delete), all 3 layers must pass:

### Layer 1 - `protected_worktrees` list
Paths declared in config are never written to or deleted. Protects user-managed worktrees.

### Layer 2 - `.ddaro/OWNED` flag
ddaro only plants this file in worktrees it created. **Absent → not a cleanup candidate.** Even if a user-made worktree accidentally has a `-d-*` name, this flag prevents its destruction. The flag lives inside `<worktree>/.ddaro/` (alongside `LOCK` and `context/`) rather than under `<worktree>/.git/`, because in a `git worktree` setup `<worktree>/.git` is a FILE pointer to the main repo's per-worktree gitdir - third-party files placed there are not guaranteed stable across `git worktree remove`, `git gc`, or future git versions.

### Layer 3 - Typed confirmation (abandon only)
`/ddaro:abandon` requires the user to type `yes, I'm sure` verbatim. No shortcuts.

### Hard prohibitions

- Committing / merging from the main worktree (it is a receiver only)
- Bypassing pre-commit hooks via `--no-verify`
- Using `git reset --hard` or `git branch -D` outside `/ddaro:abandon`
- Committing 100+ pure-deletion lines without user confirmation
- Auto-deleting remote branches without explicit prompt

---

## Lock File & Context Directory

### Lock (`<worktree>/.ddaro/LOCK`)

```json
{
  "branch": "d-fox",
  "topic": "user-supplied topic string or slug",
  "created_at": "2026-04-23T10:00:00",
  "main_worktree": "C:\\path\\to\\myapp",
  "language": "english"
}
```

Every subcommand validates `current branch == lock.branch`. On mismatch, it prints the discrepancy, prompts y/n, and defaults to abort. This catches the user having manually switched branches inside a ddaro worktree.

### Context Directory (`<worktree>/.ddaro/`)

```
<worktree>/.ddaro/
├── OWNED                                      # empty flag - proves ddaro created this worktree
├── LOCK                                       # branch/topic/created_at/language JSON
├── CURRENT.md                                 # latest running state, overwritten each commit
└── context/
    ├── 2026-04-23T10-00-00-a1b2c3d.md        # commit 1 snapshot
    ├── 2026-04-23T11-15-00-b2c3d4e.md        # commit 2 snapshot
    └── 2026-04-23T12-30-00-c3d4e5f.md        # commit 3 snapshot
```

The `.ddaro/` directory is kept out of git by appending a single `.ddaro/` line to the project's root `.gitignore` at `<main_worktree>/.gitignore` on first `/ddaro:start` (added once if absent).

**Crash recovery**: after VS Code dies or Claude Code session ends, `/ddaro:summary` reads these files to rebuild context. No user setup needed.

---

## Context MD Formats

### Per-commit snapshot

```markdown
# d-fox - Commit a1b2c3d

**Time**: 2026-04-23 10:00:00
**Branch**: d-fox
**Ahead of main**: 1 commit

## Commit message
<commit message>

## Files changed (N files, +X -Y)
- <file1> (+X -Y)
- <file2> (+X -Y)

## What was done
<Claude-generated one-line summary of this commit's intent>

## Next planned (inferred)
<TODOs found in code, unfinished tests, obvious next steps>

## Review flags raised
<FLAG entries from deletion classifier, or "None">
```

### CURRENT.md

```markdown
# d-fox - Current State

**Last updated**: 2026-04-23 12:30:00
**Branch**: d-fox
**Total commits**: 3 ahead of main
**Push status**: origin/d-fox up to date
**Uncommit**: none

## Journey so far
1. [10:00] Worktree created, branch d-fox from main@<sha>
2. [11:15] Commit b2c3d4e - <message>
3. [12:30] Commit c3d4e5f - <message>

## Currently
Idle (last commit N min ago). Ready for next edit or /ddaro:merge.

## Resume hint
If this session restarts:
- cwd: <worktree path>
- Last goal: <topic from lock + recent commit intent>
- Next expected: <inferred from last commit + TODOs>
```

---

## /ddaro:start [name]

1. **Config check**: if `.ddaro/config.json` missing, run initial 5-step setup (language → main worktree → protected list → naming strategy → name pool).
2. **Existing-worktree scan**: if any ddaro-owned worktrees already exist, offer to resume one instead of creating new:
   ```
   ⚠ Existing ddaro worktrees:
     1) new worktree (default)
     2) resume d-fox      (2h ago, 3 commits, uncommit)
     3) resume d-billing  (1d ago, pushed, ready to merge)
     4) cancel
   ```

   > Tip: if you already know you want to re-enter an existing worktree (e.g. after a crash or a days-later return), `/ddaro:resume` is the direct path - it generates a recap + cd + paste prompt in one step.
3. **Concurrency check**: reject at `max_concurrent`; warn at `warn_threshold` and list stale candidates.
4. **Name resolution**:
   - If user supplied `<name>` → slugify + collision check
   - Else → auto-generate per `naming_strategy` + `name_pool`
   - Collision → append `-2`, `-3`
5. **Main-worktree state check**: if main is dirty, warn and confirm before proceeding.
6. **Create worktree** (path is always anchored to `main_worktree`, never cwd - worktree is created as a sibling of `main_worktree`):
   ```bash
   git -C <main_worktree> worktree add \
     <main_worktree>/../<project>-d-<name> \
     -b d-<name> main
   ```
7. **Plant ownership + lock + context dir**:
   - `mkdir <worktree>/.ddaro/context/`
   - `touch <worktree>/.ddaro/OWNED`
   - Write `<worktree>/.ddaro/LOCK` (JSON with branch, topic, created_at, main_worktree, language)
   - Append `.ddaro/` to `<main_worktree>/.gitignore` if the line is not already present (once per project).
   - Write initial `<worktree>/.ddaro/CURRENT.md`
8. **Output copy-paste prompt** (in config language):
   ```
   ✓ Worktree created: <path>
   ✓ Branch:           d-<name>

   Next steps (new terminal):
     cd <path>
     claude

   Paste this:
     ──────────────────────────────────
     Continue work on d-<name>. topic: <describe>
     ──────────────────────────────────
   ```

---

## /ddaro:commit [message]

Repeatable per edit chunk. Each call writes a context snapshot.

1. **Lock validation**: if current branch ≠ lock.branch, print the discrepancy, prompt y/n, default abort.
2. **Main-worktree refusal**: if cwd is `main_worktree`, stop and tell the user to run `/ddaro:start`.
3. **Stage**: `git add -A` (the `.ddaro/` directory is excluded via `<main_worktree>/.gitignore`).
4. **Deletion analysis**:

   | Pattern | Verdict | User confirm |
   |---|---|---|
   | Replacement (nearby same symbol added) | OK | silent |
   | Whitespace / indent only | OK | silent |
   | Pure deletion, no replacement | FLAG | listed |
   | Function / class / export removal | ALWAYS CONFIRM | always |
   | >100 lines pure deletion | ALWAYS CONFIRM | always |

5. **Confirm prompt** if any FLAG or ALWAYS CONFIRM present:
   ```
   Diff summary:  +X -Y (N files)
   
   Deletions to review:
     [replace] <file>:<line>   <short description>
     [confirm] <file>:<line>   <short description> - no replacement, intentional?
   
   y / n / abort
   ```
6. **Commit**: `git commit -m "<message>"`. If no message, auto-generate `ddaro: d-<name> - N files (+X -Y)` (ASCII hyphen so pre-commit hooks rejecting non-ASCII do not choke). If the hook still rejects, stop and ask the user for a message - never retry with `--no-verify`.
7. **Push**: `git push origin d-<name>`. Every commit backs up to remote.
8. **Context write** (if `context_persistence: true`):
   - Create `<worktree>/.ddaro/context/<ISO-timestamp>-<sha7>.md` with:
     - Commit message, diff stat, file list
     - "What was done" (Claude reads diff → one-line summary)
     - "Next planned" (TODO comments, unfinished tests scan)
     - Review flags raised during this commit
   - Overwrite `<worktree>/.ddaro/CURRENT.md`:
     - Append this commit to Journey
     - Refresh Currently / Resume hint
9. **Report**:
   ```
   ✓ Commit:         <sha7>
   ✓ Changes:        N files (+X -Y)
   ✓ Push:           origin/d-<name> (up to date)
   ✓ Ahead of main:  K commits
   ✓ Context saved:  .ddaro/context/<filename>
   ```

---

## /ddaro:merge

Work complete, time to ship.

1. **Lock validation**.
2. **Uncommitted check**: if present, offer:
   - Run `/ddaro:commit` first (recommended)
   - Stash → merge → pop
   - Abort
3. **Origin refresh**: `git fetch origin`.
4. **Pre-flight conflict check**:
   ```bash
   git merge-tree $(git merge-base HEAD origin/main) HEAD origin/main
   ```
   If conflicts reported, list files and stop. User must rebase or resolve before retry.
5. **Diff size measurement** (`main..HEAD`):
   - small: `lines ≤ 50 AND files ≤ 2`
   - medium: not small, and `lines ≤ 300 AND files ≤ 10`
   - large: `lines > 300 OR files > 10`
6. **Size-based handling** (standalone - no automatic runtime dependency on other plugins):
   - small → deletion re-confirm only
   - medium → deletion re-confirm + size warning printed to user
   - large → deletion re-confirm + size warning + pure-deletion re-scan across the full diff
   - `--review=<triad|prism>` (optional, opt-in only): if the named plugin is detected on disk (stat-check `${HOME}/.claude/plugins/cache/haroom_plugins/<name>/` or `${HOME}/.claude/skills/<name>/`), pass the diff to it. If the plugin is not installed, stop and print the install hint (`/plugin marketplace add https://github.com/minwoo-data/haroom_plugins.git` then `/plugin install <name>`). Never auto-invoked from the size band alone.
7. **Pure-deletion re-scan**: whole-diff check - anything that existed on main but disappears in the merge gets flagged.
8. **Final y/n** from user.
9. **Merge method**:
   - **PR path (default)**: `gh pr create` → print PR URL → human reviews/merges on GitHub.
     - Optional: include CURRENT.md's Journey section in PR body.
   - **Local path** (`--local` flag): output the following copy-paste block to the user:
     ```
     Local merge - run in the main worktree:
       cd <main_worktree>
       git merge d-<name>
       git push
     ```
10. **Post-merge cleanup prompt**:
    ```
    ✓ Merge complete: d-<name> → main (K commits, +X -Y)
    ✓ Pushed to remote
    
    Clean up worktree <path>?
      y (default) - delete branch + worktree (and .ddaro/context)
      n           - keep (further edits possible; `/ddaro:clear` later)
    
    y/n [y]:
    ```
11. **`y` path**:
    - `git branch -d d-<name>` (safe; refuses if unmerged)
    - `git push origin --delete d-<name>`
    - `git worktree remove <path>` (context dir disappears with it)

> **Archive option**: you may copy `.ddaro/context/` into `<main>/.ddaro/archive/d-<name>/` before removal. Default behavior skips archiving - commit log is the canonical history.

---

## /ddaro:clear [name]

Clean up ddaro worktrees whose branches are already merged to main. (Renamed from `/ddaro:clean` in v0.1.2; the deprecated alias was removed in v0.2.0.)

1. No name → list all merged ddaro-owned worktrees as candidates.
2. Confirm via `git branch --merged main`.
3. Unmerged → refuse; suggest `/ddaro:merge` first or `/ddaro:abandon` to force-discard.
4. Merged → `git branch -d`, `git push origin --delete`, `git worktree remove`.

---

## /ddaro:status

Read-only. Based on current cwd.

If cwd is a ddaro worktree (has `.ddaro/OWNED`):

```
Current worktree: <path>
Branch:           d-<name>  (lock matches ✓)
Topic:            <topic>
Created:          <timestamp> (Nh ago)

Commits:          K ahead of main
Uncommit:         N files modified
Push status:      origin/d-<name> up to date
Context saved:    M snapshots in .ddaro/context/

Suggested next:
  • <based on state - commit / merge / continue editing>
```

If cwd is not a ddaro worktree: inform user and suggest `/ddaro:list`.

---

## /ddaro:list

Walk all worktrees, filter to ddaro-owned.

```
ddaro worktrees (4 / 10):

Summary:
  Active:      2 (uncommit)
  Ready:       1 (pushed, mergeable)
  Merged:      1 (clean recommended)

List:
  d-fox        active    1 uncommit, 2 commits       2h ago
  d-billing    active    3 uncommit                   30m ago
  d-statement  ready     4 commits, pushed            1d ago
  d-auth       merged    merged → main                8d ago  ⚠ /ddaro:clear
```

Warnings:
- At/over `warn_threshold`: "⚠ 5+ worktrees active - consider cleaning stale ones"
- Stale entries (past `stale_days`): flagged inline

---

## /ddaro:summary [name]

Content-based recap. **User supplies no goal at `start` time** - Claude reconstructs from commits, diffs, and context MDs.

### Data sources

| Output | From |
|---|---|
| What was worked on | `git log main..HEAD` + `git diff --stat` + `.ddaro/context/*.md` "What was done" |
| Where it stopped | `git status` + `.ddaro/CURRENT.md` Resume hint + minutes since last commit |
| Next recommended | Context MD "Next planned" + TODO scan + unfinished tests |

### No arg → brief summary per worktree

```
ddaro worktrees (3 / 10):

━━━ d-fox (2h ago) ━━━━━━━━━━━━━━━━━━━━━
  <one-line recap>
  → 1 uncommit, 3 commits pushed

━━━ d-billing (30m ago) ━━━━━━━━━━━━━━━━
  <one-line recap>
  → 1 uncommit, 5 commits pushed

━━━ d-auth (8d ago) ⚠ STALE ━━━━━━━━━━━━
  [merged → main] <recap>
  → /ddaro:clear recommended
```

### With name → detailed recap

```
━━━ d-fox ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Branch:   d-fox
Created:  2026-04-23 10:00 (2h ago)
Lock:     matches ✓

Progress:
  Commits:  3 ahead of main · pushed
  Uncommit: 1 file modified

━ What was being worked on ━
  <Claude reads commits + context, generates 2-3 line synthesis>

━ Where it stopped ━
  Currently editing: <file>
  (Nm since last commit, uncommit present)
  Most recent edit: <snippet>
  Inferred: <what the user appears to be doing>

━ Next recommended ━
  • Finish uncommit → /ddaro:commit
  • Then /ddaro:merge (size: medium → triad review)
```

### Crash recovery usage

For actively resuming a dead session, `/ddaro:resume` is the higher-level entry point - it runs summary internally and produces a cd + paste block. Use `/ddaro:summary` directly when you only want a read-only recap without re-entering.

---

## /ddaro:resume

Re-enter a ddaro worktree after a session ends, a crash, or a days-later return. Combines the existing-worktree scan from `/ddaro:start`, the recap from `/ddaro:summary`, and an auto-generated paste prompt, so one command covers the whole "where was I?" flow.

### Flow

1. **Scan**: enumerate ddaro-owned worktrees and classify each:
   - `active` - uncommit present (edit in progress)
   - `ready`  - all committed + pushed, waiting on `/ddaro:merge`
   - `stale`  - older than `stale_days`
   - `merged` - already merged; surfaced but suggests `/ddaro:clear` instead of resume
2. **Picker**:
   ```
   Resumable ddaro worktrees:
     1) d-billing   active    2 uncommit, 3 commits    2h ago
     2) d-fox       ready     4 commits pushed         1d ago - ready to merge
     3) d-auth      stale     5 commits                9d ago ⚠
     4) cancel

     Select (or 'all' for one-line recap of each):
   ```
3. **On selection**: internally run `/ddaro:summary <name>`, then print a resume block combining the recap with cd + paste prompt:
   ```
   ━━━ d-billing - resume plan ━━━━━━━━━━━━━━━━━━━━━━━
   Branch:        d-billing  (lock ✓)
   Topic:         fix statement totals
   Created:       2026-04-23 09:00 (2h ago)
   Progress:      3 commits, 2 uncommit files

   ━ Where you stopped ━
     Last commit:  "add tax handling" (25m ago)
     Uncommit:     src/services/statement.py:142
     Inferred:     finishing TODO at line 156

   ━ Next recommended ━
     • /ddaro:commit  (stage uncommit first)
     • /ddaro:merge   (size: medium → triad review)

   ━━━ Copy-paste to resume ━━━━━━━━━━━━━━━━━━━━━━━━━━

     cd <worktree path>
     claude

     Then paste:
     ──────────────────────────────────────────────
     Resuming d-billing - topic: fix statement totals.
     Last state: 3 commits, 2 uncommit on src/services/statement.py.
     Next: finish TODO at line 156 → /ddaro:commit → /ddaro:merge.

     Run /ddaro:summary first to confirm state, then continue.
     ──────────────────────────────────────────────
   ```
4. **`all` selection**: one-line recap per worktree; no paste prompts.

### Edge cases

| Situation | Behavior |
|---|---|
| No ddaro-owned worktrees | Print "Nothing to resume. Use `/ddaro:start` to begin new work." |
| cwd already inside a ddaro worktree | Warn that `/ddaro:status` may fit better; still allow picker if user confirms |
| cwd is `main_worktree` | Normal picker (most common entry) |
| Selected worktree has no `.ddaro/context/` (manually deleted or `context_persistence: false`) | Rebuild recap from `git log` only; flag "context unavailable" |
| Lock file disagrees with current branch | Warn, show discrepancy, proceed on user confirmation |

### When to use what

|  | `/ddaro:summary` | `/ddaro:resume` | `/ddaro:start` |
|---|---|---|---|
| Purpose | Read-only recap | Recap + re-entry plan | New work (with optional resume offer) |
| Side effect | None | None | Creates worktree |
| Paste prompt | No | Yes | Yes (new topic) |
| Best for | "What did I do?" | "I died, put me back" | "Start something new" |

---

## /ddaro:abandon <name>

Destructive. 3-layer protection required.

```
⚠ Abandon d-<name> completely:
  • N commits will be lost forever (M unpushed, K pushed)
  • Worktree will be removed: <path>
  • Context MD files will be deleted (S snapshots)
  • Delete remote branch too? y/n

Confirm: type exactly 'yes, I'm sure':
```

On full confirmation:
- `git worktree remove <path> --force`
- `git branch -D d-<name>`
- Optional: `git push origin --delete d-<name>`

---

## /ddaro:setting - Interactive menu

```
⚙ ddaro settings

  1) Language                 [english]
  2) Naming strategy          [d-number]
  3) Name pool                [korea_city]
  4) Max concurrent           [10]
  5) Warn threshold           [5]
  6) Stale days               [7]
  7) Context persistence      [true]
  8) Protected worktrees      [5 paths]
  9) Main worktree            [<path>]
  0) Done

  Select:
```

Each selection opens a sub-menu. On change, write back to `<main>/.ddaro/config.json` immediately.

### Sub-menus

| # | Item | Sub options |
|---|---|---|
| 1 | Language | 1) english  2) korean |
| 2 | Naming strategy | 1) d-number  2) d-pool  3) ddaro-number  4) ddaro-pool |
| 3 | Name pool | 1) animal  2) korea_city  3) us_state  4) fruit  5) greek  6) custom |
| 4 | Max concurrent | numeric 1-30 |
| 5 | Warn threshold | numeric, ≤ max_concurrent |
| 6 | Stale days | numeric 1-90 |
| 7 | Context persistence | 1) true  2) false |
| 8 | Protected worktrees | add path / remove / show |
| 9 | Main worktree | auto-detected candidates + manual path |

---

## /ddaro:config [action] [value]

Direct, script-friendly, one-line.

| Command | Effect |
|---|---|
| `/ddaro:config` | Print full current config |
| `/ddaro:config init` | Relaunch 5-step setup wizard |
| `/ddaro:config main <path>` | Change main worktree |
| `/ddaro:config protect <path>` | Add to protected list |
| `/ddaro:config naming <key>` | Change naming strategy |
| `/ddaro:config pool <key>` | Change name pool |
| `/ddaro:config language <en\|ko>` | Change language |
| `/ddaro:config context <true\|false>` | Toggle context MD writes |
| `/ddaro:config max <N>` | Change max concurrent |

Other removals / fine edits: edit config file manually.

### config vs setting

|  | config | setting |
|---|---|---|
| UX | Single command line | Interactive menu |
| Prerequisite | Know key + value | Pick numbers |
| Speed | Fast | Guided |
| Use case | Scripts, known values | Browse, uncertain |

---

## First-run setup prompt (when config missing)

```
user> /ddaro:start

claude> ⚠ .ddaro/config.json not found - running initial setup

        [1/5] Choose output language:
          1) english (default)
          2) korean
        Select:

user> 1

claude> [2/5] Specify the main worktree path (ddaro will never touch this).
        Auto-detected candidates:
          1) <path1>           (main branch, clean)
          2) <path2>           (main branch)
        Choose (1/2) or enter path:

user> 1

claude> [3/5] Detected sibling folders. Select ones to protect:
          1) <sibling1>
          2) <sibling2>
          3) <sibling3>
        'all' / comma-list / 'none':

user> all

claude> [4/5] Default naming strategy:
          1) d-number     (d-1, d-2)   ← default
          2) d-pool       (uses name pool)
          3) ddaro-number (ddaro-1)
          4) ddaro-pool   (ddaro-<pool>)
        Select:

user> 1

claude> [5/5] Name pool (only used for `-pool` strategies):
          1) animal       (otter, panda, fox)
          2) korea_city   (seoul, busan, pohang)  ← default
          3) us_state     (ca, ny, tx)
          4) fruit        (peach, kiwi, mango)
          5) greek        (alpha, beta, gamma)
        Select:

user> 2

claude> ✓ Config saved: <main>/.ddaro/config.json
        Proceeding with /ddaro:start...
```

If `language=korean`, all subsequent output is in Korean.

---

## Limits (honest)

What this plugin protects against:
- ✓ File collisions between parallel Claude sessions (worktree isolation)
- ✓ Accidental main commits (main worktree is write-locked)
- ✓ Unintended deletions (diff classifier + confirmation)
- ✓ Pre-merge conflicts (dry-run before merge)
- ✓ Work loss on crash (every commit → push + context MD)
- ✓ Unreviewed merges (size-based auto review)
- ✓ Context loss across sessions / IDE restarts (context MDs + `/ddaro:summary`)

What this plugin cannot protect against:
- ✗ User manually force-checking out the same branch in two worktrees (`git worktree add --force`)
- ✗ Direct `git reset --hard` on the main worktree
- ✗ Simultaneous merges from multiple worktrees (merge one at a time)
- ✗ Manual deletion of `<worktree>/.ddaro/` (context loss)

---

## Related files

- `<main>/.ddaro/config.json` - per-project settings (language, protect, naming, pool)
- `<worktree>/.ddaro/OWNED` - empty flag file; presence proves ddaro created the worktree
- `<worktree>/.ddaro/LOCK` - branch/topic/created_at/language JSON
- `<worktree>/.ddaro/context/*.md` - per-commit snapshots (crash recovery)
- `<worktree>/.ddaro/CURRENT.md` - running state, overwritten each commit
- `<main_worktree>/.gitignore` - contains a `.ddaro/` line that keeps the directory out of git (added once by `/ddaro:start`)
