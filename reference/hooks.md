# ddaro hooks

All hooks are registered by the plugin (`hooks/hooks.json`) and active whenever ddaro is enabled. Each reads `.ddaro/config.json` and does nothing when the key is `off`/absent or no config exists (fail-open). `/ddaro:config <key> <mode>` only writes the mode; never touch `.claude/settings.json`.

| Config key | Modes | Event / script | Effect | One-shot bypass |
|---|---|---|---|---|
| `main_protection` | off / warn / strict | PreToolUse Bash `check-main-bash.py`, Edit/Write/NotebookEdit `check-main-edit.py`, SessionStart `session-start-notice.py` | strict blocks `git commit` and file edits in the main worktree (session cwd in main). Never blocks merges, pulls, read-only tools, or `planning_patterns` / `.claude/**` files. warn = notice only. | `ALLOW_MAIN_DIRECT=1 <cmd>` |
| `branch_naming` | off / warn / strict | PreToolUse Bash `check-branch-naming.py` | strict blocks creating a branch without a `name_pool` marker. Allowed: `d-<city>[/<topic>]`, `<feat|fix|chore|docs|refactor|test|style|build|ci|perf>/<topic>-<city>`, `backup/d-<city>-...`, `main`/`master`/`develop`/`base_branch`, `release/*`, `hotfix/*`, `ddaro/*`, `dependabot/*`. | `ALLOW_NON_DDARO_BRANCH=1 <cmd>` |
| `branch_worktree_match` | off / warn / strict | PreToolUse Bash `check-worktree-branch-match.py` | strict blocks `git commit` when the folder marker (`*-d-busan`) and branch marker (`d-seoul`) differ. | `ALLOW_WORKTREE_BRANCH_MISMATCH=1 <cmd>` |
| `evidence_check` | off / warn / strict | PreToolUse Edit/Write `check-evidence.py` | strict requires a fresh `.ddaro/evidence-token` (`touch` it after reading/grepping; ttl `evidence_token_ttl_seconds`, default 300). | `ALLOW_NO_EVIDENCE=1 <cmd>` |
| `cross_worktree_check` | on / off | SessionStart `cross-worktree-health.py` | one line per worktree with tracked-deleted files, behind origin, uncommit, stale. `fetch_before_check: on` fetches first (budget `fetch_budget_seconds`, default 10). | - |
| `auto_snapshot` | on / off | PostToolUse Bash `context_md.py hook` | writes `.ddaro/context/<ts>-<sha7>.md` + refreshes `CURRENT.md` after a `git commit` in an owned/adopted worktree. | - |

## `/ddaro:config migrate` (installs from <= 0.4.0)

Open the project's `.claude/settings.json` (main first, then cwd; absent = "nothing to migrate"). In `hooks.PreToolUse` and `hooks.SessionStart` remove only entries whose command contains `${CLAUDE_PLUGIN_ROOT}/hooks/` followed by one of `check-main-edit.py`, `check-main-bash.py`, `check-branch-naming.py`, `check-worktree-branch-match.py`, `check-evidence.py`, `session-start-notice.py`, `cross-worktree-health.py`; drop arrays/matcher blocks left empty; keep every other hook and key. Nothing to remove = report "already clean" and do not write.
