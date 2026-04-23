---
name: ddaro:start
description: "Create a new isolated ddaro worktree + branch with lock. First run triggers initial config prompt. Scans existing worktrees and surfaces unmanaged ones (with /ddaro:adopt suggestion) and dirty-main state (classified into planning vs code)."
argument-hint: "[name]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## /ddaro:start [name]" and execute with `$ARGUMENTS` as the optional name.

### Phase A — First-time setup (no `.ddaro/config.json` anywhere the search finds)

The first run MUST pin down which folder is `main` before anything else happens. cwd is just a guess — confirm it.

1. Ask: "**Is `<cwd>` your main worktree?** (the canonical receiver folder that ddaro must never touch directly — yes / no / other-path)"
   - **yes** → treat cwd as main; continue to step 2.
   - **no** / **other-path** → ask for the intended main path. Validate: must be an existing git worktree (`git worktree list` entry). If path is valid BUT is not cwd:
     - Save the 5-step config scaffold **pointing at that path** (so the config file lands at `<main>/.ddaro/config.json`, not here).
     - **Refuse to create a worktree from the current cwd.** Print:
       ```
       ✓ Setup saved. Main is set to <main-path>.
       ✗ /ddaro:start must run from main. Copy-paste:

           cd <main-path>
           /ddaro:start
       ```
     - **Stop here.** Do not scan, do not create worktrees.
2. Run the 5-step setup (language / main / protected / naming / pool). Persist to `<main>/.ddaro/config.json`.
3. **Step 6 — main_protection prompt** (new; this is the "main is a receiver, not a workspace" guardrail):
   - Ask: "Install the main-protection hook? This blocks direct `git commit` / `Edit` / `Write` on `<main>` so you can only modify main by merging a ddaro branch. `git merge` and files under `planning_patterns` (`.planning/**`, `.gsd/**`, `CHANGELOG.md`, etc.) still pass. One-shot bypass: `ALLOW_MAIN_DIRECT=1 <cmd>`.  [**strict** (recommended) / warn / off]"
   - Default pick when user hits Enter: **strict**.
   - If `strict` or `warn`: internally invoke the same flow as `/ddaro:config main_protection <level>` — preview the `.claude/settings.json` hook entries (PreToolUse: Bash → check-main-bash.py, Edit/Write/NotebookEdit → check-main-edit.py) and merge them in. Preserve any existing hooks via sentinel markers. `off` → skip entirely and note "you can enable later with `/ddaro:config main_protection strict`".
   - Write the chosen level into `<main>/.ddaro/config.json`.
4. If cwd == main (step 1 = yes), print "Setup complete — continuing with worktree creation below" and fall through to Phase B. Otherwise Phase A already stopped above (config + hook are in place; user will cd to main and re-run start).

### Phase B — cwd-is-main precondition (every subsequent run)

- If `.ddaro/config.json` is resolvable but `cwd != config.main_worktree`, refuse:
  ```
  ✗ /ddaro:start must run from main (<config.main_worktree>).
    cd <config.main_worktree>
    /ddaro:start
  ```
  Do not create a worktree from the wrong cwd.

### Phase C — Pre-create scan (cwd == main)

- **Existing-worktree scan** — classify all worktrees via the tier algorithm in SKILL.md. Present in groups:
  - **Ddaro-owned / adopted active** → offer `/ddaro:resume` instead of creating new; if user picks resume, exit start.
  - **Unmanaged (not under ddaro)** → surface with three options per entry:
    1. `/ddaro:adopt <path>` — bring under ddaro management
    2. commit-and-clean in place (print the cd + `git status` hint; user finishes there first)
    3. ignore and keep going
    Default is **ignore** (never auto-adopt).
- **Main dirty check** — if uncommitted changes exist in cwd, classify files using `config.planning_patterns` (default: `.planning/**`, `.gsd/**`, `STATE.md`, `ROADMAP.md`, `CHANGELOG.md`). Offer targeted options:
  - commit all before start
  - commit planning-only, leave code uncommit
  - carry code changes into the new worktree (git stash → create worktree → stash pop inside)
  - start anyway (uncommit stays on main, user's problem)
  - cancel
- **Unpushed-commits check on main** — if main has unpushed commits, warn once but don't block.
- Respect `max_concurrent` and `warn_threshold` limits.
- Use `naming_strategy` + `name_pool` from config when user gives no name.

### Phase D — Create

- `git worktree add <path> -b d-<name> main`.
- Plant `<path>/.ddaro/OWNED`, `<path>/.ddaro/LOCK`, `<path>/.ddaro/context/`, initial `<path>/.ddaro/CURRENT.md`. Append `.ddaro/` to `<main_worktree>/.gitignore` if absent (once per project).
- Output cd + copy-paste prompt for the new terminal. Remind user: "next steps in the new worktree — edit → `/ddaro:commit` → `/ddaro:merge`. If you close the session, come back with `/ddaro:resume`."
