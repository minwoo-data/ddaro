# Changelog

All notable changes to this plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
