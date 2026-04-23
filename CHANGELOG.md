# Changelog

All notable changes to this plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] — 2026-04-23

### Fixed
- **OWNED / LOCK path**: moved from `<worktree>/.git/ddaro-owned` / `-lock` to `<worktree>/.ddaro/OWNED` / `LOCK`. In a `git worktree` setup `<worktree>/.git` is a file pointer, not a directory, so third-party files placed there could fail or be pruned by `git worktree remove` / `git gc`.
- **`.gitignore` scope**: `.ddaro/` exclusion is now appended once to `<main_worktree>/.gitignore` instead of `<worktree>/.ddaro/.gitignore` with pattern `*` (which ignored children but not the dir entry).
- **Section headings**: all 10 subcommand section headings now use colon form (`## /ddaro:start` rather than `## /ddaro start`) to match the Commands table and eliminate LLM ambiguity about the required invocation form.
- **`mangchi` merge override**: removed from `--review` accepted values; only `skip | triad | prism` are supported.
- **Size-band boundaries**: rewritten as a single consistent scheme — `small = lines≤50 AND files≤2`; `medium = not small AND lines≤300 AND files≤10`; `large = lines>300 OR files>10`.
- **Auto commit message**: em-dash replaced with ASCII hyphen so pre-commit hooks rejecting non-ASCII do not choke. Documented `--no-verify` is never used as a retry.
- **Local-merge path**: now emits an explicit copy-paste block (`cd <main_worktree> && git merge d-<name> && git push`) instead of vague wording. Dropped the false "Claude cannot cd" claim.
- **Worktree creation path**: `git worktree add` is now anchored to `main_worktree` (always a sibling), not cwd-relative, so the result is stable regardless of where the user invokes `/ddaro:start`.
- **Lock-mismatch behavior**: specification tightened to "print discrepancy, prompt y/n, default abort" (previously just "warn").

### Added
- **`schema_version` config field**: required for future migrations; on load, if the value does not match the current schema, ddaro runs a named migration before use.
- **"Why this exists" intro**: motivation for parallel-session users and crash-recovery, plus a sentence defining `git worktree` for readers who haven't used it.
- **"Quick start" walkthrough**: 6-line fenced block showing the minimum `/ddaro:start` → edit → `/ddaro:commit` → `/ddaro:merge` flow, before the Commands table.
- **3-Layer Protection rationale**: one-sentence explanation of why three layers exist (abandon/clean destroy real work; each layer catches a different mistake).

## [0.1.0] — 2026-04-23

### Added
- Initial plugin release.
- 10 subcommands: `start`, `commit`, `merge`, `clean`, `status`, `list`, `summary`, `abandon`, `setting`, `config`.
- Each subcommand exposed as namespaced slash (`/ddaro:start`, etc.) plus single-entry `/ddaro <sub>`.
- Worktree-based isolation model — one worktree, one branch, one Claude session.
- 3-layer protection:
  - `protected_worktrees` config list
  - `.git/ddaro-owned` ownership flag
  - typed `yes, I'm sure` confirmation for `/ddaro:abandon`
- Deletion classifier for commits: replacement / format / pure / function-level / 100-line-plus — flag only when destructive.
- Size-based merge review: small → deletion re-check; medium → `triad`; large → `prism`.
- Context MD persistence per commit: `.ddaro/context/<timestamp>-<sha7>.md` + running `.ddaro/CURRENT.md`.
- `/ddaro:summary` reconstructs work context from commits + context MDs for crash recovery.
- Bilingual output via `config.language` (english default, korean available).
- Naming strategies: `d-number` (default), `d-pool`, `ddaro-number`, `ddaro-pool`.
- Name pools: `animal`, `korea_city` (default), `us_state`, `fruit`, `greek`.
- Existing-worktree detection on `/ddaro:start` — offers resume instead of create.
- Initial 5-step setup wizard (language, main worktree, protected list, naming, pool).
- Interactive settings menu via `/ddaro:setting`.
- Self-hosted marketplace (install via `/plugin marketplace add github.com/minwoo-data/ddaro.git`).

### Known limitations
- Single merge at a time (parallel merges from multiple worktrees into main are not serialized).
- Context dir (`.ddaro/`) lives inside the worktree — lost if user manually deletes it.
- Auto-review invokes `triad`/`prism` as external skills; those must be installed for medium/large merges to get reviewed.
