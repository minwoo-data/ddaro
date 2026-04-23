---
name: ddaro
description: "Worktree-based parallel workflow. Create isolated worktree + branch, adopt existing worktrees, commit with deletion-aware checks, review and merge to main by diff size, recover from session/IDE crashes via per-commit context MD. Subcommands: start / adopt / resume / commit / merge / clear / status / list / summary / abandon / setting / config. Language: english or korean (config). Korean triggers: 따로, 병렬로, 분리해서, main 건드리지 마. English: parallel, isolated, separate branch."
version: "0.2.4"
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

## Worktree tiers

Not every folder git reports as a worktree belongs to ddaro. ddaro classifies every worktree it sees into one of six tiers, and each tier has its own permission set. This is how ddaro coexists with main, with long-lived feature worktrees, with GSD, and with Claude Code agent worktrees - without stomping on any of them.

```
┌─────────────────────────────────────────────────────────────────┐
│ Tier 0: main                   (config.main_worktree)           │
│   Receiver of merges + canonical state. ddaro never mutates it. │
├─────────────────────────────────────────────────────────────────┤
│ Tier 1: ddaro-owned            (.ddaro/OWNED, adopted=false)    │
│   Created by /ddaro:start. Full life cycle under ddaro.         │
├─────────────────────────────────────────────────────────────────┤
│ Tier 2: adopted                (.ddaro/OWNED, adopted=true)     │
│   External worktree brought under ddaro via /ddaro:adopt.       │
│   Same commands as owned EXCEPT /ddaro:abandon is refused.      │
├─────────────────────────────────────────────────────────────────┤
│ Tier 3: protected              (config.protected_worktrees)     │
│   User-declared "do not touch". ddaro shows read-only only.     │
├─────────────────────────────────────────────────────────────────┤
│ Tier 4: unmanaged              (no .ddaro, not in config)       │
│   Visible via /ddaro:list, but ddaro never acts on it until     │
│   the user adopts or removes it manually.                       │
├─────────────────────────────────────────────────────────────────┤
│ Tier 5: external               (config.external_patterns)       │
│   Owned by other tools (e.g. `.claude/worktrees/agent-*`).      │
│   ddaro ignores these entirely.                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Classification algorithm

ddaro classifies a worktree path in this priority order (first match wins):

1. `path == config.main_worktree`                     → **main**
2. `path` matches any glob in `config.external_patterns` → **external**
3. `path` is in `config.protected_worktrees`          → **protected**
4. `<path>/.ddaro/OWNED` exists
   - `LOCK.adopted == true`                            → **adopted**
   - else                                              → **ddaro-owned**
5. else                                                → **unmanaged**

Ordering matters: a stray `.ddaro/OWNED` file in the main worktree does not grant ddaro access to main, because the main check runs first. Likewise, an unmanaged worktree can be protected by simply adding it to `protected_worktrees`.

### Permission matrix

| Command                 | main | owned | adopted | protected | unmanaged | external |
|-------------------------|------|-------|---------|-----------|-----------|----------|
| `/ddaro:start` (create) | n/a  | n/a   | n/a     | reject    | n/a       | reject   |
| `/ddaro:adopt`          | ✗    | ✗     | ✗       | ✗         | **✓**     | ✗        |
| `/ddaro:commit`         | ✗    | ✓     | ✓       | ✗         | ✗         | ✗        |
| `/ddaro:merge`          | ✗    | ✓     | ✓       | ✗         | ✗         | ✗        |
| `/ddaro:clear`          | ✗    | ✓     | ✓       | ✗         | ✗         | ✗        |
| `/ddaro:abandon`        | ✗    | ✓     | **✗**   | ✗         | ✗         | ✗        |
| `/ddaro:resume`         | ✗    | ✓     | ✓       | ✗         | ✗         | ✗        |
| `/ddaro:summary`        | n/a  | ✓     | ✓       | n/a       | git-log only | ✗      |
| `/ddaro:list`           | show | show  | show    | show      | show      | show (optional section) |
| `/ddaro:status`         | show | ✓     | ✓       | show      | show      | ✗        |

The only meaningful difference between **owned** and **adopted** is `/ddaro:abandon`: ddaro never force-discards a worktree it did not create. For adopted, force removal is the user's call via plain `git worktree remove --force`.

---

## cwd rules (destructive commands)

Destructive commands must be run from the **main worktree**, not from inside the worktree being removed. If ddaro removed a worktree from within itself, the shell's cwd would point at a deleted folder on Linux/macOS, and on Windows the delete would fail outright because the folder is in use.

| Command               | Required cwd                       | On violation |
|-----------------------|------------------------------------|--------------|
| `/ddaro:start`        | any                                | — |
| `/ddaro:adopt`        | any                                | — |
| `/ddaro:commit`       | the target ddaro/adopted worktree  | lock-check warning |
| `/ddaro:merge`        | the target ddaro/adopted worktree  | lock-check warning; merge stays here, cleanup is **handed off** to `/ddaro:clear` at main |
| `/ddaro:clear`        | **`config.main_worktree`**         | refuse + print `cd <main>` and the exact `/ddaro:clear` command to re-run |
| `/ddaro:abandon`      | **`config.main_worktree`**         | same as clear |
| `/ddaro:list` / `:status` / `:summary` / `:resume` | any | — |

By forcing clear/abandon to run at main, the "where do I go after the folder disappears?" problem is solved structurally: the user is already in main when the delete happens, so there is no stale cwd.

`/ddaro:merge`'s cleanup prompt follows the same rule. Instead of deleting from inside the target, it prints a hand-off block:

```
✓ Merge complete.

Cleanup must run from main. Copy-paste:

    cd <main_worktree>
    /ddaro:clear <branch-or-name>
```

One removal code path (`/ddaro:clear`) instead of two reduces surface area for bugs.

---

## Commands (frequency order)

| Command | Purpose | When |
|---|---|---|
| `/ddaro:start [name]` | Create worktree + branch + lock | Starting new work |
| `/ddaro:adopt <path>` | Bring an existing worktree under ddaro management | You already have a non-ddaro worktree and want ddaro's commit/merge/context flow on top |
| `/ddaro:commit [msg]` | Safe commit + push + context snapshot | After each edit chunk (repeat) |
| `/ddaro:merge` | Pre-flight check + review + merge + cleanup hand-off | Work complete |
| `/ddaro:status` | Current worktree state | Quick check |
| `/ddaro:list` | All worktrees, grouped by tier | Overview |
| `/ddaro:summary [name]` | Content recap from commits + context | Read-only "what did I do?" |
| `/ddaro:resume` | Pick a worktree + recap + cd + paste prompt | Crash recovery / returning after days |
| `/ddaro:clear [name]` | Delete merged worktree post-hoc (run from main) | After `merge` with "keep" choice, or any cleanup |
| `/ddaro:abandon <name>` | 3-layer guarded force-discard (owned only, run from main) | Work went wrong |
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
  "schema_version": 2,
  "main_worktree": "C:\\path\\to\\myapp",
  "project_name": "myapp",
  "protected_worktrees": [
    "C:\\path\\to\\myapp",
    "C:\\path\\to\\myapp-experiments"
  ],
  "external_patterns": [
    ".claude/worktrees/agent-*",
    ".git/worktrees/*"
  ],
  "planning_patterns": [
    ".planning/**",
    ".gsd/**",
    "STATE.md",
    "ROADMAP.md",
    "CHANGELOG.md"
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
  "context_persistence": true,
  "main_protection": "off"
}
```

### Field reference

- **`schema_version`**: integer, currently `2` (was `1` in v0.2.1; v0.2.4 adds `external_patterns`, `planning_patterns`, `main_protection`). On load, if the value does not match the current schema, ddaro runs a named migration before use.
- **`main_worktree`**: absolute path to the clean main-branch worktree. ddaro never mutates this.
- **`protected_worktrees`**: paths ddaro will refuse to create in or delete. Auto-populated during init setup plus sibling folders user flags. Defines **Tier 3**.
- **`external_patterns`** *(new in 0.2.4)*: glob patterns for worktrees owned by other tools (e.g. Claude Code agent worktrees). ddaro ignores these entirely. Defines **Tier 5**.
- **`planning_patterns`** *(new in 0.2.4)*: globs used by `/ddaro:start` Step 5 to classify dirty-main files as "planning/state" vs "code" and offer targeted options. Does not affect commit rules elsewhere.
- **`max_concurrent`**: hard ceiling. `/ddaro:start` rejects beyond this.
- **`warn_threshold`**: soft warning at this count.
- **`stale_days`**: `/ddaro:list` marks worktrees older than this as `STALE`.
- **`naming_strategy`** + **`name_pool`**: control auto-generated names.
- **`language`**: `english` (default) or `korean`. Affects all subcommand output.
- **`context_persistence`**: `true` (default) writes `.ddaro/context/*.md` per commit.
- **`main_protection`** *(new in 0.2.4)*: `off` (default), `warn`, or `strict`. Controls whether hooks block direct mutation of the main worktree. See "Main protection hooks" below.

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
- **Removing a worktree while cwd is inside it** — `/ddaro:clear` / `:abandon` refuse unless cwd is main, and `/ddaro:merge` hands off cleanup to `/ddaro:clear` rather than deleting from inside the target

---

## Main protection hooks *(opt-in, new in 0.2.4)*

"ddaro never touches main" has historically been a **convention** enforced only by ddaro's own commands. A user (or a parallel Claude Code session) can still run plain `git commit` in the main worktree and break the invariant. `main_protection` promotes the convention to a tool-level guard using Claude Code hooks.

### Levels

| Level | SessionStart | PreToolUse (Edit/Write on main) | PreToolUse (Bash `git commit` on main) | Bypass |
|---|---|---|---|---|
| `off` (default) | silent | allow | allow | n/a |
| `warn` | show "you are in main" notice with tier summary | allow + log to stderr | allow + log to stderr | n/a |
| `strict` | show notice + hard reminder | **block** (except paths matching `planning_patterns`, `.claude/**`) | **block** (unless `ALLOW_MAIN_DIRECT=1`) | set env `ALLOW_MAIN_DIRECT=1` for one command |

Never blocks: `git merge`, `git pull`, `gh pr merge`, read-only tools, paths under `planning_patterns`.

### Hook scripts

Shipped inside the plugin at `${CLAUDE_PLUGIN_ROOT}/hooks/`:

- `session-start-notice.py` — SessionStart; prints the "you are in main" banner + tier summary if cwd matches `config.main_worktree` and level is `warn`/`strict`.
- `check-main-edit.py` — PreToolUse matching `Edit|Write|NotebookEdit`; blocks writes to files under `config.main_worktree` unless the relative path matches `planning_patterns` or level is `off`/`warn`.
- `check-main-bash.py` — PreToolUse matching `Bash`; blocks tool_input commands that look like `git commit` (including `git commit --amend`, `git commit --fixup`) targeting main, unless `ALLOW_MAIN_DIRECT=1` is set.

All three are Python scripts (stdlib only) for cross-platform portability. If Python is unavailable, the hooks fail open (log to stderr, allow action) - never fail closed.

### Enabling

```bash
cd <main_worktree>
/ddaro:config main_protection warn      # or strict
```

ddaro responds with a preview of the `.claude/settings.json` entries it will add and asks y/n:

```
/ddaro:config main_protection strict will add these entries to
  .claude/settings.json:

  {
    "hooks": {
      "SessionStart": [{
        "hooks": [{"type": "command",
                   "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/session-start-notice.py"}]
      }],
      "PreToolUse": [
        {
          "matcher": "Edit|Write|NotebookEdit",
          "hooks": [{"type": "command",
                     "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/check-main-edit.py"}]
        },
        {
          "matcher": "Bash",
          "hooks": [{"type": "command",
                     "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/check-main-bash.py"}]
        }
      ]
    }
  }

  Settings file: C:/.../.claude/settings.json
  Bypass:        ALLOW_MAIN_DIRECT=1 <command>

    y - merge entries into settings.json (preserves existing entries)
    n - print the JSON for manual paste
    x - cancel

  [y/n/x]:
```

Disabling: `/ddaro:config main_protection off` removes the ddaro-owned entries from `.claude/settings.json` (entries are tagged with a sentinel comment so ddaro can find them later). Other users' hook entries stay untouched.

### Helpful refusal

When a hook blocks an action, it prints the reason plus at least one way forward — never a terse "denied". Example for blocked `git commit` in main:

```
🛑 Blocked by ddaro main_protection=strict.
   You are in: C:/.../receipt_processor (main worktree).
   Direct commits on main are refused.

   Options:
     1) Commit in a ddaro worktree and merge:
          cd C:/.../receipt_processor-d-busan
          /ddaro:commit "<msg>"
          /ddaro:merge
     2) One-shot bypass (audit-visible):
          ALLOW_MAIN_DIRECT=1 git commit -m "<msg>"
     3) Disable strict protection:
          /ddaro:config main_protection off
```

---

## Lock File & Context Directory

### Lock (`<worktree>/.ddaro/LOCK`)

**ddaro-owned (Tier 1)** — default shape:

```json
{
  "branch": "d-fox",
  "topic": "user-supplied topic string or slug",
  "created_at": "2026-04-23T10:00:00",
  "main_worktree": "C:\\path\\to\\myapp",
  "language": "english"
}
```

**adopted (Tier 2)** — same fields plus three adoption markers:

```json
{
  "branch": "feat/phase-15-v28b-pending-ui",
  "topic": "user-supplied topic string or slug",
  "created_at": "2026-04-23T10:00:00",
  "main_worktree": "C:\\path\\to\\myapp",
  "language": "english",
  "adopted": true,
  "original_branch": "feat/phase-15-v28b-pending-ui",
  "adopted_at": "2026-04-23T10:00:00"
}
```

Backward compatibility: LOCK files written by v0.2.x without the `adopted` field are read as `adopted: false`. No migration required.

Every subcommand validates `current branch == lock.branch`. On mismatch, it prints the discrepancy, prompts y/n, and defaults to abort. This catches the user having manually switched branches inside a ddaro worktree.

### Context Directory (`<worktree>/.ddaro/`)

```
<worktree>/.ddaro/
├── OWNED                                      # empty flag - proves ddaro manages this worktree
├── LOCK                                       # JSON; adopted=true for Tier 2
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
2. **Existing-worktree scan**: list all worktrees grouped by tier so the user can pick an existing path instead of creating a new one:
   ```
   ⚠ Existing ddaro worktrees:
     1) new worktree (default)
     2) resume d-fox      (2h ago, 3 commits, uncommit)
     3) resume d-billing  (1d ago, pushed, ready to merge)
     4) cancel

   ⚠ Unmanaged worktrees detected (NOT carried over by /ddaro:start):
     • receipt_processor-ui  [feat/phase-15-pending]  (14 commits, 2 uncommit)
         a) Finish in place — cd there, commit/push/merge, remove manually
         b) Adopt into ddaro — /ddaro:adopt <path>
         c) Ignore and start fresh (default — these stay as-is)
   ```

   > Tip: if you already know you want to re-enter an existing worktree (e.g. after a crash or a days-later return), `/ddaro:resume` is the direct path - it generates a recap + cd + paste prompt in one step.
3. **Concurrency check**: reject at `max_concurrent`; warn at `warn_threshold` and list stale candidates.
4. **Name resolution**:
   - If user supplied `<name>` → slugify + collision check
   - Else → auto-generate per `naming_strategy` + `name_pool`
   - Collision → append `-2`, `-3`
5. **Main-worktree state check**: if main is dirty, classify uncommitted files into planning-like vs code and offer targeted options before proceeding. Planning-like = anything matching `config.planning_patterns` (default: `.planning/**`, `.gsd/**`, `STATE.md`, `ROADMAP.md`, `CHANGELOG.md`).
   ```
   ⚠ Main worktree is dirty. These will NOT carry into the new ddaro worktree:

     Planning / state (often important — GSD, docs):
       .planning/STATE.md        (15 lines)
       .planning/intel/runtime.md (new file)

     Code:
       src/app.py                (3 lines)

     Options:
       1) Commit all, then start ddaro            (recommended)
       2) Commit only planning/state files        (code stays uncommitted)
       3) Cherry-pick specific files after start  (manual cp)
       4) Start anyway — lose these in new worktree
       5) Cancel
   ```
   Only planning-like files carrying over is the typical desire (GSD state, refs). Code changes usually belong in the ddaro branch itself, so leaving them in main is rarely what the user wants — option 1 is default.
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

## /ddaro:adopt <path>

Bring an existing non-ddaro worktree under ddaro management. Use this when you already have a worktree (made by `git worktree add`, inherited from a teammate, created by another tool) and you want ddaro's commit/merge/context flow to apply to it - **without moving any code, without renaming the branch, without recreating anything**.

### What adopt does and does not do

| Does | Does not |
|---|---|
| Plant `<path>/.ddaro/OWNED`, `LOCK`, `context/`, `CURRENT.md` | Rename the branch |
| Mark `LOCK.adopted = true` + record `original_branch` | Change file contents |
| Record the existing branch as the adopted branch | Move the worktree path |
| Prompt for a topic | Create a new worktree or branch |
| Add `.ddaro/` to `.gitignore` if missing | Run any git operation |

### Refusal conditions

ddaro refuses adoption if the target path is:
- **main worktree** (`config.main_worktree`)
- In `config.protected_worktrees`
- Matched by any glob in `config.external_patterns` (e.g. `.claude/worktrees/agent-*` - owned by other tools)
- Already has `<path>/.ddaro/OWNED` (already ddaro or adopted)

The refusal prints why plus what the user can do instead (unprotect, or just keep using it outside ddaro).

### Flow

1. **Path validation**: must be a real `git worktree list` entry. If not, stop with an error.
2. **Tier check**: classify and refuse per the list above. Print the tier and remediation.
3. **State snapshot**: inspect the target and show a summary:
   ```
   Target:        C:/.../receipt_processor-ui
   Branch:        feat/phase-15-v28b-pending-ui   (kept as-is)
   Commits ahead of main: 14
   Uncommitted:   2 files
   Pushed:        origin/feat/phase-15-v28b-pending-ui up to date
   ```
4. **Topic prompt**: short description for `LOCK.topic` and `CURRENT.md`. User-typed, not auto-generated.
5. **Plant ddaro files**:
   - `mkdir <path>/.ddaro/context/`
   - `touch <path>/.ddaro/OWNED`
   - Write `<path>/.ddaro/LOCK`:
     ```json
     {
       "branch": "feat/phase-15-v28b-pending-ui",
       "topic": "<user-supplied>",
       "created_at": "<now>",
       "main_worktree": "C:/.../receipt_processor",
       "language": "english",
       "adopted": true,
       "original_branch": "feat/phase-15-v28b-pending-ui",
       "adopted_at": "<now>"
     }
     ```
   - Append `.ddaro/` to `<main_worktree>/.gitignore` if absent (same one-time rule as `/ddaro:start`).
   - Write initial `<path>/.ddaro/CURRENT.md` noting "adopted from external worktree".
6. **Output summary**:
   ```
   ✓ Adopted: C:/.../receipt_processor-ui
     Branch:     feat/phase-15-v28b-pending-ui   (kept as-is)
     Status:     14 commits ahead of main, 2 uncommit
     Topic:      <topic>

   From now on you can use: /ddaro:commit, /ddaro:merge, /ddaro:resume, /ddaro:clear

   Note: /ddaro:abandon is refused for adopted worktrees. To force-discard,
   use plain git from main:
     cd <main_worktree>
     git worktree remove --force <path>
     git branch -D <branch>
   ```

### End-of-life — adopted converges on `/ddaro:clear`

An adopted worktree finishes the same way a ddaro-owned one does:

```
adopt → commit (repeat) → merge → clear
```

`/ddaro:merge` and `/ddaro:clear` treat owned and adopted identically. The single difference is `/ddaro:abandon` - adopted is refused there, because ddaro never force-destroys something it did not create.

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
10. **Post-merge cleanup hand-off** (the merge never deletes its own worktree - see "cwd rules"):
    ```
    ✓ Merge complete: d-<name> → main (K commits, +X -Y)
    ✓ Pushed to remote

    Cleanup must run from the main worktree (this worktree is about to be removed).
      y (default) - print the copy-paste block to finish in main
      n           - keep everything for now; run /ddaro:clear later

    y/n [y]:
    ```
11. **`y` path — hand-off block** (no delete is executed here):
    ```
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
      Run this in your shell:

        cd <main_worktree>
        /ddaro:clear <branch-or-name>
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ```
    Why hand-off instead of direct delete: on Windows, `git worktree remove` fails when cwd is inside the target. On Linux/macOS it succeeds but leaves the shell pointing at a vanished path. Removing the worktree only from main (via `/ddaro:clear`) avoids both problems and means there is exactly one code path that deletes worktrees.

> **Archive option**: you may copy `.ddaro/context/` into `<main>/.ddaro/archive/d-<name>/` before removal. Default behavior skips archiving - commit log is the canonical history.

---

## /ddaro:clear [name]

Clean up ddaro-owned or adopted worktrees whose branches are already merged to main. This is the **single code path** that actually removes a worktree - `/ddaro:merge` only hands off to it. (Renamed from `/ddaro:clean` in v0.1.2; the deprecated alias was removed in v0.2.0.)

**Precondition — must run from main**:

```
if cwd != config.main_worktree:
    print helpful refusal:
      ✗ /ddaro:clear must run from the main worktree.
        Current cwd: <cwd>
        Main:        <main_worktree>

        Run this first:
          cd <main_worktree>

        Then re-run:
          /ddaro:clear <name>
    exit
```

This rule makes "where does the shell end up after the target vanishes?" a non-issue: the user is already in main when the delete happens.

### Flow

1. **cwd check** (above). Refuse with cd instructions if not in main.
2. **Target resolution**:
   - No name → list all merged ddaro-owned + adopted worktrees as candidates, let the user pick.
   - Name given → resolve to a single worktree (match against `LOCK.branch` or worktree folder name).
3. **Merge confirmation**: `git branch --merged main` must list the target's branch. If not:
   - Unmerged → refuse; suggest `/ddaro:merge` first, or `/ddaro:abandon` (owned only) / plain `git worktree remove --force` (adopted) to force-discard.
4. **Execute**:
   - `git branch -d <branch>` (safe - refuses if unmerged; catches the branch-in-another-worktree case).
   - `git push origin --delete <branch>` (prompt y/n if the remote branch still exists; skip if no remote).
   - `git worktree remove <path>` (context dir inside `.ddaro/` disappears with it).
5. **Post-clear**: confirm to user; cwd remains at main so the next action proceeds naturally.

`/ddaro:clear` applies identically to Tier 1 (owned) and Tier 2 (adopted). The only tier-specific logic lives in `/ddaro:abandon`.

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

Walk all worktrees in `git worktree list --porcelain`, classify each one by tier (see "Worktree tiers"), and print them grouped.

```
ddaro worktrees (4 / 10):

Summary:
  Owned:     2 active, 1 ready
  Adopted:   1
  Unmanaged: 1 (candidates for /ddaro:adopt)

Owned:
  d-fox        active    1 uncommit, 2 commits        2h ago
  d-billing    active    3 uncommit                   30m ago
  d-statement  ready     4 commits, pushed            1d ago  → /ddaro:merge

Adopted:
  receipt_processor-ui   [feat/phase-15-v28b-pending]   14 commits, pushed   adopted 1h ago
    ℹ /ddaro:abandon refused — use `git worktree remove --force` from main

Unmanaged (not under ddaro):
  receipt_processor-experiment   [feat/xyz]   3 commits   2d ago
    → /ddaro:adopt C:/.../receipt_processor-experiment
    → or /ddaro:config protect <path> to mark it hands-off

Protected (ddaro never touches):
  receipt_processor                 [main]
  receipt_processor-archive         [archive]

External (owned by other tools):
  .claude/worktrees/agent-a51235cb  [agent-a51235cb]
```

Warnings:
- At/over `warn_threshold` owned+adopted worktrees: "⚠ N+ worktrees active - consider cleaning stale ones"
- Stale entries (past `stale_days`): flagged inline with `⚠ STALE`
- Owned worktrees whose branch is fully merged to main: suggest `/ddaro:clear`

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

Destructive. Force-discards a ddaro-owned worktree even if its commits are unmerged. Reserved for "this work went wrong - drop everything" situations.

### Preconditions

1. **cwd must equal `config.main_worktree`** (same rule as `/ddaro:clear` - see the cwd rules section). On mismatch, refuse with cd instructions.
2. **Target tier must be `ddaro-owned`** (Tier 1).
   - Tier 2 (**adopted**) is **refused**: ddaro does not force-destroy worktrees it did not create. Print:
     ```
     ✗ /ddaro:abandon refuses adopted worktrees.

       Adopted means ddaro is managing, not owning. To force-discard
       unmerged work on an adopted worktree, use plain git from main:

         cd <main_worktree>
         git worktree remove --force <path>
         git branch -D <branch>
         # optional: git push origin --delete <branch>
     ```
   - Tier 0 (main), Tier 3 (protected), Tier 4 (unmanaged), Tier 5 (external): also refused, each with its own remediation message.

### Flow (after preconditions pass)

3-layer protection enforced in order:

1. **Layer 1 (`protected_worktrees` re-check)** — belt-and-braces; the tier check above already covers this.
2. **Layer 2 (OWNED + not adopted)** — verified via the tier gate.
3. **Layer 3 (typed confirmation)**:
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
- Optional: `git push origin --delete d-<name>` (if user answered y above)

After success, cwd is still main - no stranded shell.

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
| `/ddaro:config unprotect <path>` | Remove from protected list |
| `/ddaro:config external <pattern>` | Add a glob to `external_patterns` |
| `/ddaro:config naming <key>` | Change naming strategy |
| `/ddaro:config pool <key>` | Change name pool |
| `/ddaro:config language <en\|ko>` | Change language |
| `/ddaro:config context <true\|false>` | Toggle context MD writes |
| `/ddaro:config max <N>` | Change max concurrent |
| `/ddaro:config main_protection <off\|warn\|strict>` | Toggle the hook-based main-worktree guard (installs/uninstalls `.claude/settings.json` entries with y/n confirm) |

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
