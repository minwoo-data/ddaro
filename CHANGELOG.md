# Changelog

All notable changes to this plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.5] - 2026-04-23

Metadata hygiene release. No behaviour changes — just brings shipped metadata in sync with the actual 0.2.x feature set and drops internal artifacts that shouldn't have been in the published tree.

### Fixed

- **`.claude-plugin/marketplace.json` stale** — the plugin's self-hosted marketplace metadata was still describing the 0.1.x feature set (`"version": "0.1.2"`, "deletion-aware commits, size-based merge review, crash-recoverable context logs"). Now matches `plugin.json` 0.2.5: mentions 6-tier worktree model, `/ddaro:adopt`, cwd-safe destructive commands, main-protection hooks, Korean triggers.
- **Version drift inside the plugin** — `plugin.json` was 0.2.4 while self-hosted `marketplace.json` was 0.1.2; both now 0.2.5.

### Removed

- **`docs/discussion/ddaro-skill/`** — internal design-discussion artifacts (`source.md`, `round-1.md`, `state.json`) that were getting shipped to users. The authoritative user-facing spec is `skills/ddaro/SKILL.md`; design history belongs in git, not the plugin payload.

## [0.2.4] - 2026-04-23

This is a large feature release that rounds out ddaro's coverage from "helper for new isolated work" to "first-class worktree manager that coexists with everything already in the repo." Three concept shifts, all backward-compat: existing 0.2.x users see no behaviour change until they opt in.

### Added

- **6-tier worktree model** (documented in `SKILL.md` → "Worktree tiers"). Every worktree ddaro sees is classified into one of: `main`, `ddaro-owned` (Tier 1), `adopted` (Tier 2, new), `protected` (Tier 3), `unmanaged` (Tier 4, new), `external` (Tier 5, new - for `.claude/worktrees/agent-*` and similar). The classification algorithm enforces priority (main > external > protected > owned/adopted > unmanaged) so stray flag files can't override user-declared protection. A per-command permission matrix makes it clear what each tier allows.
- **`/ddaro:adopt <path>`** — new command. Bring an existing non-ddaro worktree under ddaro management without renaming the branch, moving files, or recreating anything. Only plants `<path>/.ddaro/OWNED`, `LOCK` (with `adopted: true`), `context/`, and `CURRENT.md`. Refuses main, protected, external, and already-ddaro targets. Adopted worktrees use `/ddaro:commit`, `/ddaro:merge`, `/ddaro:resume`, `/ddaro:clear` identically to owned; only `/ddaro:abandon` is refused (force-discard stays a plain-git operation).
- **cwd rules for destructive commands** (SKILL.md → "cwd rules (destructive commands)"). `/ddaro:clear` and `/ddaro:abandon` now refuse unless cwd is `config.main_worktree`, printing a helpful `cd <main>` + re-run block. Structurally eliminates the "worktree deleted from inside — where does my shell go?" problem.
- **`/ddaro:merge` cleanup hand-off**. The `y` branch of the post-merge cleanup prompt no longer executes deletion from inside the target worktree. Instead it prints the exact `cd <main>` + `/ddaro:clear <name>` block for the user to paste. One removal code path instead of two; works identically on Windows (where delete-while-inside fails) and Linux/macOS (where it succeeds but leaves a stale cwd).
- **Unmanaged-worktree surfacing**. `/ddaro:start` Step 2 and `/ddaro:list` now detect and print worktrees that exist in git but are outside ddaro's management, offering three options: finish-in-place, `/ddaro:adopt`, or ignore. Never auto-adopts.
- **Dirty-main classification**. `/ddaro:start` Step 5 classifies uncommitted main changes into "planning-like" vs "code" using the new `config.planning_patterns` (default: `.planning/**`, `.gsd/**`, `STATE.md`, `ROADMAP.md`, `CHANGELOG.md`). Offers targeted options (commit all / commit planning only / cherry-pick later / start anyway / cancel) instead of a blanket warning.
- **Main protection hooks (opt-in)**. New `config.main_protection` key with three levels: `off` (default, no change from 0.2.1), `warn` (SessionStart notice + logged but allowed), `strict` (blocks `git commit` and Edit/Write inside main). Hooks ship inside the plugin (`./hooks/*.py`, stdlib-only, fail-open). Enable via `/ddaro:config main_protection warn|strict` — presents the `.claude/settings.json` entries for y/n/x confirm rather than silently mutating the user's settings. Bypass with `ALLOW_MAIN_DIRECT=1 <command>`.
- **LOCK schema v2**. Adds `adopted: bool`, `original_branch: str`, `adopted_at: iso8601` fields. Absent fields default to `false` / null for 0.2.1 worktrees; no migration required.
- **Config schema v2**. New keys: `external_patterns`, `planning_patterns`, `main_protection`. The `schema_version` field bumps from `1` to `2`. Older configs load unchanged with defaults filled in.
- **`/ddaro:config` new actions**: `unprotect <path>`, `external <pattern>`, `main_protection <off|warn|strict>`.

### Changed

- **Commands table** (SKILL.md) now includes `/ddaro:adopt` and notes the main-cwd requirement on `/ddaro:clear` / `:abandon`.
- **`/ddaro:list`** output restructured by tier: Owned / Adopted / Unmanaged / Protected / External. Surface adopt suggestions inline for unmanaged.
- **Hard prohibitions** list in SKILL.md extends to explicitly ban "removing a worktree while cwd is inside it".

### Internal

- Plugin now declares `hooks: ./hooks/` in `plugin.json` alongside `commands` and `skills`.
- Hooks reuse a shared `_shared.py` helper module (config lookup, cwd resolution, bypass check) so behaviour stays consistent across the three hook entry points.

### Compatibility

- 0.2.1 users see no behaviour change on upgrade. `main_protection` defaults to `off`, `external_patterns` / `planning_patterns` defaults match prior hardcoded behaviour, adopt is opt-in, tier reclassification is internal only.
- Worktrees created under 0.2.1 keep working. Their LOCK files lack the `adopted` field and are read as `adopted: false` (i.e. Tier 1).

## [0.2.1] - 2026-04-23

### Fixed
- **`/ddaro:merge` no longer auto-invokes other plugins**. Previously medium diffs would auto-call `triad` and large diffs would auto-call `prism`, creating a hidden runtime dependency on sibling haroom plugins. ddaro is now truly standalone: size bands only control deletion-scan strictness and print a size warning. Cross-plugin review is now **opt-in only** via `--review=<triad|prism>`, and if the named plugin is not installed the command stops with an install hint instead of silently failing.

### Changed
- **`--review=<triad|prism>` semantics**: flag is now explicit opt-in. Previously the flag overrode the auto-invoke default; now the flag is the only way cross-plugin review runs.

## [0.2.0] - 2026-04-23

### Removed
- **`/ddaro:clean` deprecated alias**. The v0.1.2 rename (`/ddaro:clean` -> `/ddaro:clear`) shipped with a one-version grace alias. That alias is now gone. Typing `/ddaro:clean` will report "unknown command". Users still on muscle memory should switch to `/ddaro:clear`.

### Added
- **`/ddaro:merge` optional `/prism` hint**. When the `prism` plugin is detected (file stat on the plugin cache path), the merge confirmation appends one informational line: "Tip: for a deeper multi-angle review of this diff, run /prism after merging." Purely advisory - ddaro never calls prism at runtime and does not require it installed.

### Fixed
- **`commands/ddaro.md` dispatcher description**: subcommand list was stale (listed `/ddaro:clean`, missing `/ddaro:resume`). Now lists the current v0.2.0 surface: `start | resume | commit | merge | status | list | summary | clear | abandon | setting | config`.

## [0.1.2] - 2026-04-23

### Added
- **`/ddaro:clear`**: new command for post-merge cleanup of merged ddaro worktrees. Renamed from `/ddaro:clean` to avoid confusion with git clean semantics. Safe (refuses unmerged); delegates force-discard to `/ddaro:abandon`.
- **`/ddaro:resume`**: new command for re-entering a ddaro worktree after a crash or days-later return. Combines the existing-worktree scan from `/ddaro:start`, the recap from `/ddaro:summary`, and an auto-generated cd + paste-ready prompt in one step.

### Fixed
- **Missing command files**: v0.1.2 SKILL.md documented `/ddaro:clear` and `/ddaro:resume` but the `commands/` folder was never updated, so Claude Code never registered those slash commands. This release adds the command files that should have shipped in v0.1.2.
- **`commands/ddaro-clean.md`** kept temporarily as a deprecated alias that prints a one-line warning and forwards to `/ddaro:clear`. (Removed in v0.2.0.)

## [0.1.1] - 2026-04-23

### Fixed
- **OWNED / LOCK path**: moved from `<worktree>/.git/ddaro-owned` / `-lock` to `<worktree>/.ddaro/OWNED` / `LOCK`. In a `git worktree` setup `<worktree>/.git` is a file pointer, not a directory, so third-party files placed there could fail or be pruned by `git worktree remove` / `git gc`.
- **`.gitignore` scope**: `.ddaro/` exclusion is now appended once to `<main_worktree>/.gitignore` instead of `<worktree>/.ddaro/.gitignore` with pattern `*` (which ignored children but not the dir entry).
- **Section headings**: all 10 subcommand section headings now use colon form (`## /ddaro:start` rather than `## /ddaro start`) to match the Commands table and eliminate LLM ambiguity about the required invocation form.
- **`mangchi` merge override**: removed from `--review` accepted values; only `skip | triad | prism` are supported.
- **Size-band boundaries**: rewritten as a single consistent scheme - `small = lines≤50 AND files≤2`; `medium = not small AND lines≤300 AND files≤10`; `large = lines>300 OR files>10`.
- **Auto commit message**: em-dash replaced with ASCII hyphen so pre-commit hooks rejecting non-ASCII do not choke. Documented `--no-verify` is never used as a retry.
- **Local-merge path**: now emits an explicit copy-paste block (`cd <main_worktree> && git merge d-<name> && git push`) instead of vague wording. Dropped the false "Claude cannot cd" claim.
- **Worktree creation path**: `git worktree add` is now anchored to `main_worktree` (always a sibling), not cwd-relative, so the result is stable regardless of where the user invokes `/ddaro:start`.
- **Lock-mismatch behavior**: specification tightened to "print discrepancy, prompt y/n, default abort" (previously just "warn").

### Added
- **`schema_version` config field**: required for future migrations; on load, if the value does not match the current schema, ddaro runs a named migration before use.
- **"Why this exists" intro**: motivation for parallel-session users and crash-recovery, plus a sentence defining `git worktree` for readers who haven't used it.
- **"Quick start" walkthrough**: 6-line fenced block showing the minimum `/ddaro:start` → edit → `/ddaro:commit` → `/ddaro:merge` flow, before the Commands table.
- **3-Layer Protection rationale**: one-sentence explanation of why three layers exist (abandon/clean destroy real work; each layer catches a different mistake).

## [0.1.0] - 2026-04-23

### Added
- Initial plugin release.
- 10 subcommands: `start`, `commit`, `merge`, `clean`, `status`, `list`, `summary`, `abandon`, `setting`, `config`.
- Each subcommand exposed as namespaced slash (`/ddaro:start`, etc.) plus single-entry `/ddaro <sub>`.
- Worktree-based isolation model - one worktree, one branch, one Claude session.
- 3-layer protection:
  - `protected_worktrees` config list
  - `.git/ddaro-owned` ownership flag
  - typed `yes, I'm sure` confirmation for `/ddaro:abandon`
- Deletion classifier for commits: replacement / format / pure / function-level / 100-line-plus - flag only when destructive.
- Size-based merge review: small → deletion re-check; medium → `triad`; large → `prism`.
- Context MD persistence per commit: `.ddaro/context/<timestamp>-<sha7>.md` + running `.ddaro/CURRENT.md`.
- `/ddaro:summary` reconstructs work context from commits + context MDs for crash recovery.
- Bilingual output via `config.language` (english default, korean available).
- Naming strategies: `d-number` (default), `d-pool`, `ddaro-number`, `ddaro-pool`.
- Name pools: `animal`, `korea_city` (default), `us_state`, `fruit`, `greek`.
- Existing-worktree detection on `/ddaro:start` - offers resume instead of create.
- Initial 5-step setup wizard (language, main worktree, protected list, naming, pool).
- Interactive settings menu via `/ddaro:setting`.
- Self-hosted marketplace (install via `/plugin marketplace add github.com/minwoo-data/ddaro.git`).

### Known limitations
- Single merge at a time (parallel merges from multiple worktrees into main are not serialized).
- Context dir (`.ddaro/`) lives inside the worktree - lost if user manually deletes it.
- Auto-review invokes `triad`/`prism` as external skills; those must be installed for medium/large merges to get reviewed.
