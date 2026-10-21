# Changelog

All notable changes to this plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.10.0] - 2026-10-20

Merge gate (design track G, `docs/design/merge-gate.md` v3.3, slice S2). Opt-in: `merge_gate` is `off` by default and nothing changes until a project turns it on. Needs prism 0.6.0 (`report-contract.json`, `--run-tag` gate runs).

### Added
- `hooks/gate.py`: the single writer of `<main>/.ddaro/gates/`. `check-begin` (readiness, cycle cleanup, run number and scope: full / recheck / rejudge / tests-only, the project's `verify.json` tests before any review), `check-record` (judges prism's contract-2 report: meta and lens completeness, record format, new blockers at `gate_block_severity` and above, grounding failures, blocker closing only on a REJECTED record whose quote sits on a changed code line, carry of late-recorded runs), `status` (mergeable / reason / next with the spec's priority order, PASS carry-over for document-only commits), `close --merged --pr N` (a cycle closes only through a MERGED PR whose head descends from this cycle), `retire`, and the person-only `approve`, `close`, `reset`. Every verdict is JSON on stdout with exit 0; `summary` lines are what the command files print.
- `hooks/check-merge-gate.py` (PreToolUse `Bash|Edit|Write|NotebookEdit`, timeout 30 s): with `merge_gate` strict it blocks `gh pr merge` without `--match-head-commit <PR head>` or without a PASS for that head (docs-only PRs and approved commits pass), `--auto`, a merge chained after a branch-changing git command, write `gh api`, pushes to the base branch (explicit refspec, `--all`, `--mirror`, `--delete`, implied targets via `push.default` / `@{push}`, `-c push.*`), pushes into an auto-merge PR without a PASS, gh and git aliases, the person-only gate commands, weakening config changes (`config_tool.py set`, Edit/Write of `.ddaro/config.json`), and shell or tool writes to `.ddaro/gates/**`, `.ddaro/verify.json`, a run folder's `prism-report.json` / `prism-run.json`, `.ddaro` itself, or a `.ddaro/config.json` outside `<main>`. `warn` runs the same checks as `additionalContext`. Stdlib-only fast path; once a gate target is identified any failure blocks; before that the raw-text regexes decide.
- `config_tool.py`: schema 4 (`merge_gate`, `gate_block_severity`, `gate_verify` with value checks), `init <main> [key=value ...]`, `is_weakening` / `weakening_changes` (imported by the hook), the `<git-common-dir>/ddaro-gate` marker, `.ddaro/config.lock`.
- `_shared.py`: new helpers only (`segments_with_cwd`, `scan_git_global_opts` with accumulating `-C`, `main_root_of`, `load_main_config_status`, `gate_mode`, `file_lock`, `branch_enc`, prism install lookup through `installed_plugins.json`); every existing function keeps its contract.
- Tests: `tests/test_gate.py` (81), `tests/test_merge_gate_hook.py` (111), `tests/test_gate_prism_real.py` (2, end to end against the installed prism 0.6.0 scripts, skipped when absent), run-folder cases in `test_main_edit.py`, lint rules in `test_command_files.py`.
- Reviewed with `/prism --diff` before merge: 47 candidates, 41 supported and fixed (fail-closed resolution of `<main>`, filesystem-only pre-check so repositories without a gate pay no subprocess, wildcard refspecs, alias expansion, `gh api` file bodies, glob and case-insensitive protected paths, the gate marker and `git stash --all`, a snapshot of the gate files around the project tests, bounded git timeouts in the hook), 6 rejected as design decisions.

### Changed
- `/ddaro:check` with the gate on: `gate.py check-begin` -> the Skill tool runs `prism:prism` with the script's exact arguments -> `gate.py check-record`; the script's summary is printed verbatim. With the gate off the 0.9.2 flow is unchanged. `allowed-tools` of `ddaro-check.md` and `ddaro.md` gain `Skill`.
- `/ddaro:merge` with the gate on: a gate status step before step 1, no commits on the user's behalf, PR bodies through `--body-file`, a stop after any CI fix commit ("재확인 필요"), unanswered SUSPECTED questions shown before the merge confirmation (D11), `--match-head-commit` on the merge command, `gate.py close --merged` after the sync.
- `/ddaro:clear` and `/ddaro:abandon` call `gate.py retire` after deleting the branch. `/ddaro:config` documents the gate keys and the person-only changes. `reference/config.md` (verify.json, documents, state, `init`) and `reference/hooks.md` (the new row) updated.
- `check-main-edit.py` allows writes under `<main>/.ddaro/runs/**` while `merge_gate` is warn or strict (prism writes its run files there); with the gate off it behaves exactly as before.
- First-time setup creates the config with `config_tool.py init` and offers `merge_gate` as item 10.

### Known gaps (by design, see the design document's threat model)
- Commands inside scripts, `bash -c`, `eval` or command substitution; the user's own terminal and `!` commands; a GitHub web merge on a repository without required checks; hooks that cannot run (no Python, timeout).

## [0.9.2] - 2026-10-14

Follow prism 0.5.0 (Improvement lens retired, idea pass).

### Changed
- `/ddaro:review <doc>` fans out 7 agents, not 8: prism's design lens set is now 4 angles (conflict & reuse, claim accuracy, devil's advocate, robustness 4-axis) + triad's 3 lenses. prism's Improvement lens is retired.
- `/ddaro:review` notes that prism (>= 0.5.0) runs its idea pass after its Evidence pass: grounded alternatives (class / route / subtract) checked by an independent checker, listed separately from findings and never a review blocker. The inline fallback for a prism that refuses docs now runs 4 angles.
- `/ddaro:review --diff` notes the same idea pass after prism's 5 defect lenses and Evidence pass, listed separately and never a blocker.
- `/ddaro:go` cost note before `review`: 7 discovery agents + prism's idea pass (1 proposer + checker calls).
- `/ddaro:check` runs prism-all with `--no-ideas`: the gate judges defects only, so it skips prism's idea pass.

## [0.9.1] - 2026-10-14

### Fixed
- Every shell command that runs a plugin file now quotes `${CLAUDE_PLUGIN_ROOT}/<path>`: the 8 hook commands in `hooks/hooks.json` (the 8 `claude plugin validate` warnings) and the 19 `python ${CLAUDE_PLUGIN_ROOT}/...` lines in `commands/*.md` and `reference/config.md`. Unquoted, a plugin path with a space split into several words, and under bash a Windows path lost its backslashes.
- `tests/test_plugin_root_quoted.py` fails on any unquoted `${CLAUDE_PLUGIN_ROOT}` after `python`/`bash`/`sh`/`node` in hooks.json, commands or reference files.
- The Step 0 checks in `test_command_files.py` and `test_no_hardcoded_base_ref.py` now expect the quoted form (`config_tool.py" ensure-schema`).


## [0.9.0] - 2026-10-13

Token diet. ddaro was the most expensive plugin in the family: every session paid for 15 long command descriptions, and every command told the model to read the 92k-character `skills/ddaro/SKILL.md` (about 25-30k tokens) that then stayed in context for the rest of the session.

### Changed

- **One instruction file per command.** Each `commands/ddaro-<sub>.md` now holds that command's full procedure (identical Step 0 in every file, enforced by a test). Material several commands share lives in small on-demand files under `reference/` (`tiers.md`, `config.md` incl. first-time setup, `hooks.md`, `context-files.md`), read only when a command needs it.
- **`skills/ddaro/` removed** (SKILL.md and the stale `references/usage.md`). The skill was shadowed by the `/ddaro` command of the same name, so it added nothing to the listing; its only cost was being read in full by every command.
- **Subcommands are user-invoked only** (`disable-model-invocation: true`). You still type `/ddaro:commit` etc.; the model sees a single `/ddaro <sub>` entry and routes through it.
- Command descriptions shortened to one line; manifest descriptions condensed.

### Measured (headless Claude Code, same sandbox, before -> after)

- Always-on cost per session: 2,015 -> 112 tokens.
- `/ddaro:list`: peak context 57,883 -> 29,816; tokens processed 248,459 -> 86,126; cost -64%.
- Context a command adds when invoked: up to ~29k (SKILL.md) -> 1.1-1.5k (its own file).

## [0.8.0] - 2026-10-13

Two fixes to the things dogfooding showed were not actually working: the merge target was hardcoded as `main`, and the "crash-recoverable context" snapshots only existed when `/ddaro:commit` was used (which in practice it was not).

### Added

- **`config.base_branch` replaces the hardcoded `main`.** `/ddaro:clear` (`--merged`), `/ddaro:merge` (conflict dry-run, size, `gh pr create --base`, post-merge reset), `/ddaro:go` inference, `/ddaro:check` and every ahead count now use `<base>`. Detection lives in one place, `hooks/config_tool.py` (`origin/HEAD` -> local `main` -> local `master` -> `main`), and the value is stored in config so hooks never shell out. A repo on `master` finally works.
- **Automatic context snapshots on every `git commit`.** New PostToolUse hook `hooks/context_md.py hook` writes `.ddaro/context/<ts>-<sha7>.md` and refreshes `CURRENT.md` after any commit made through Claude Code's Bash tool inside a ddaro-managed worktree (owned or adopted). Idempotent per commit, `--amend` marks the superseded snapshot, 15-minute staleness window (`DDARO_SNAPSHOT_WINDOW_SEC`), one `additionalContext` line so Claude knows the file exists. Gate: `auto_snapshot` (default `on`); `context_persistence: false` still disables everything. Follows `cd <dir> && git commit` (the harness does not reflect an in-command `cd` in the payload `cwd` - verified by capturing a real payload) and Git Bash `/c/...` paths. A non-commit Bash call exits before any heavy import, so the hook costs about a bare interpreter start (Windows: 106ms -> 48ms).
- **`hooks/context_md.py` is the only writer of context MDs.** `init` (start/adopt), `write` (manual), `enrich` (stdin JSON; `/ddaro:commit` step 8 adds the Claude-written sections) - prompts no longer hand-write these files. Files start with `<!-- ddaro-context v1 -->`; headings are exact constants; the Journey block survives rewrites (including 0.7.0 files without a marker).
- **`config_tool.py ensure-schema`** - idempotent schema 2 -> 3 migration (fills `base_branch`, `auto_snapshot`), atomic write, run by every subcommand's Step 0. That is the entire upgrade path: update, restart, run any ddaro subcommand once.
- `/ddaro:config base_branch <name>`, `/ddaro:config auto_snapshot <on|off>`, `/ddaro:config show`.
- Doc lint `tests/test_no_hardcoded_base_ref.py` so `origin/main`-style literals cannot creep back into SKILL.md / commands, and every subcommand section keeps its ensure-schema call. 60 new tests (`test_config_tool.py`, `test_context_md.py`, shared helpers; 188 total); the context_md fixture uses a real linked worktree, and the Korean / `cd` regressions send raw UTF-8 payloads the way Claude Code does.

### Fixed

- **Non-ASCII stdin and git output on Windows.** Hooks and CLIs read stdin as bytes and decode UTF-8 (`_shared.read_stdin_text`, BOM-tolerant), and decode git output as UTF-8 with `core.quotepath=off`. Before this, a cp1252 locale turned Korean commit messages into mojibake, silently dropped the snapshot for messages containing bytes undefined in cp1252 (e.g. "에"), and crashed `enrich` on Korean summaries. Protective hooks were not affected in practice (surrogateescape kept the ASCII `git commit` tokens intact) but now parse the same bytes explicitly.

### Verified

- Before merge, on a real master-based project (config restored afterwards), a clone of it, and a real headless Claude Code session loading this plugin via `--plugin-dir`: snapshots written for Korean commits, the `additionalContext` line reached the model, `ensure-schema` was idempotent and preserved every existing key. Details in the 0.8.0 pull request.

### Changed

- `branch_naming` also accepts `config.base_branch` as a system branch.
- `/ddaro:merge --review=prism` (0.7.1) now runs `/prism --diff <base>...HEAD` instead of `main...HEAD`.
- `## Files changed` in snapshots no longer carries the stat in the heading (it is the first body line) so headings are exact.
- `/ddaro:summary` and `/ddaro:setting` sections removed from SKILL.md (they had been replaced by `/ddaro:resume --recap-only` and `/ddaro:config` in 0.3.0; the aliases in `/ddaro <sub>` still route).
- `skills/ddaro/templates/` removed - the format truth is the `HEADINGS` constant in `context_md.py`, and a test keeps the SKILL.md examples in sync.
- SKILL.md frontmatter version was stale at 0.4.0; now tracks the release.

### Design

- Design doc reviewed by triad (5 rounds, all PASS) before implementation; per the v0.2.5 policy the doc and review record are not shipped in the plugin tree. Summary in the 0.8.0 pull request.

## [0.7.1] - 2026-10-13

### Fixed
- **`/ddaro:review` routing after the prism 0.3 / triad 0.2 split.** triad 0.2.0 became
  documents-only and prism 0.3.0 briefly refused documents, so the 8-agent gate could fail on
  both sides. Routing is now by target: a **design doc** gets prism's 5 design angles (conflict &
  reuse / claim accuracy / devil's advocate / robustness 4-axis / improvement - "is it sound?")
  plus triad's 3 lenses ("is it well written?"); a **`--diff`** gets prism's defect lenses with
  its Evidence pass (`/prism --diff` scoping) plus triad only on the markdown files the diff
  touches. Needs prism >=0.3.1 to invoke the skill on docs; with prism 0.3.0 the design angles run
  inline.
- **`/ddaro:merge --review=<prism|triad>`**: `prism` runs `/prism --diff main...HEAD`; `triad` is
  limited to changed markdown files and suggests `--review=prism` for code-only diffs. Size-band
  hints say "consider --review=prism" instead of "triad review".
- READMEs: prism/triad one-liners no longer describe prism 0.1 ("singleton verification").

## [0.7.0] - 2026-06-22

### Fixed

- **Sibling-worktree config discovery.** `find_ddaro_config` (the gate every
  protective hook calls) walked only the parent chain. Because `.ddaro/` is
  gitignored, a linked worktree created by `/ddaro:start` (or adopted) usually
  has no config of its own and none up its parents, so every hook silently
  no-opped there - the user lost `branch_naming` / `main_protection` /
  `branch_worktree_match` / `evidence_check` enforcement in all worktrees except
  the main one, with no warning. The lookup now falls back to the MAIN
  worktree's config by following the linked worktree's `.git` file ->
  `gitdir` -> `commondir` chain (filesystem-only, no subprocess; a non-ddaro
  repo still resolves to None at the cost of a couple of file reads). Protection
  is now uniform across every worktree of a ddaro repo.

### Added

- **`fetch_before_check` config key (opt-in, default off).** `cross_worktree_check`
  reads CACHED origin refs, so its "N behind" can be stale. Setting
  `fetch_before_check` to `on` runs a best-effort `git fetch origin` per worktree
  before the drift report. Bounded by `fetch_budget_seconds` (default 10) so a
  down network cannot stack per-worktree timeouts into a long SessionStart stall
  - which is why it defaults off.

## [0.6.2] - 2026-06-05

### Fixed

- **`/ddaro:go` stage inference (fallback path) hardened.** When `.ddaro/lifecycle.json` is
  absent (adopted or pre-0.6.1 worktrees), `/ddaro:go` infers the stage - and two heuristics
  were too literal, surfaced by dogfooding on a real worktree:
  - **Review-findings detection** matched only a literal `## Review findings` heading, so a
    hand-written doc using a numbered heading (`## 14. Review findings (...)`) read as "not
    reviewed" and would re-fire the 8-agent review on an already-reviewed doc. Now any h2
    whose text contains "Review findings" (with or without a section number/date) counts as
    reviewed.
  - **Implementation detection** used a two-dot `git diff origin/main` (tip vs tip), so a
    branch merely *behind* origin/main showed origin's newer files as "changes" and falsely
    inferred `check` on a stale branch with no real work. Now it uses the merge-base diff
    `git diff --name-only origin/main...HEAD` (three dots) plus working-tree edits, excluding
    doc/planning paths (`docs/**`, `*.md`, `.planning/**`, `.ddaro/**`).
  - The conductor now also flags a LOCK-vs-checked-out branch mismatch or a far-behind branch
    and prefers asking the operator over guessing. Both heuristics only affect the inference
    fallback; the normal `/ddaro:go`-driven flow records the stage in `lifecycle.json` and
    never relies on them, and the cost-confirm gate already prevented a silent re-review.

## [0.6.1] - 2026-06-05

### Added

- **Conductor entry point (`/ddaro:go`).** One command that reads the worktree's lifecycle
  stage and runs the next step, so you no longer have to remember which of
  spec/review/check to call. It detects the stage from `.ddaro/lifecycle.json` (or infers
  it: design doc present? has a `## Review findings` section? are there code changes beyond
  the doc?), shows the detected stage + its evidence, confirms before the heavy stages
  (review = 8 agents, check = prism-all), then delegates to the existing `/ddaro:spec` /
  `/ddaro:review` / `/ddaro:check` section - it adds no review logic of its own. After a
  stage it advances `.ddaro/lifecycle.json` and points at the next step; at the
  review -> implement boundary it stops (the human writes the feature, then re-runs
  `/ddaro:go`). The three named subcommands remain as the manual gears - pass
  `/ddaro:go spec|review|check` to force/re-run a specific stage. Pure orchestration over
  the 0.6.0 trio; touches no git history. New conductor state file
  `<worktree>/.ddaro/lifecycle.json` lives in the git-ignored `.ddaro/` dir.

## [0.6.0] - 2026-06-05

### Added

- **Lifecycle conductor (`/ddaro:spec`, `/ddaro:review`, `/ddaro:check`).** Three
  orchestration subcommands that fill the design->review FRONT half of the dev cycle
  before ddaro's existing commit->CI-merge back half:
  `start -> spec -> review -> [implement] -> check -> commit -> merge`.
  - `/ddaro:spec <name>` scaffolds a design/PRD doc with a fixed skeleton, enforces
    Search-Before-Building (greps existing code into a Reuse inventory), and captures
    Locked decisions (asks rather than silently defaulting a user-owned choice).
  - `/ddaro:review <file>` fans out 8 agents in parallel (prism 5 angles + triad 3 lenses),
    requires every agent to verify the doc's code claims against the real source, triages
    by severity + cross-angle agreement, and collates a `## Review findings` section back
    into the target. `--codex` adds the cross-engine pass (deferred by default for no-code
    docs).
  - `/ddaro:check [branch]` is a pre-merge gate: prism-all on the diff (adversarially
    verified) + a project ship checklist discovered from CLAUDE.md/rules (tests, route-map
    drift, CHANGELOG sync, schema-additive, no synthetic accounts/secrets/em-dash) ->
    BLOCK/PASS, handing off to `/ddaro:commit` + `/ddaro:merge` on PASS.
  - Pure orchestration: sequences the `doc-template` / `prism-all` / `triad` skills and
    degrades to inline steps if absent; only commit/merge touch git. Deliberately NOT a
    GSD-style project/milestone/phase framework - it encodes the lightweight
    one-doc->review->implement->review cadence that maps to a single ddaro session.

## [0.5.2] - 2026-06-04

### Added

- **Hook test suite (`tests/`).** 82 pytest cases exercise the seven hooks through real subprocess invocation: config-gating (off / warn / strict / no-config), block-allow matrices, the `planning_patterns` allowlist, NotebookEdit `notebook_path` handling, evidence-token freshness/staleness, branch-name validation, worktree-branch match against a throwaway git repo, bypass env vars, and fail-open on malformed stdin. Run with `pytest tests/`; a GitHub Actions workflow to run them on every push/PR (Python 3.9 / 3.11 / 3.13 + a JSON-manifest check) follows separately. The plugin previously shipped protective hooks with no automated coverage; this round alone surfaced three latent bugs - the 0.5.0 SessionStart matcher, the 0.5.1 NotebookEdit field, and the `git -C` bypass below.

### Fixed

- **`main_protection` no longer bypassed by `git -C <main> commit`.** `check-main-bash.py` detected commits with a `git\s+commit` regex, so any git global option between `git` and `commit` (`-C <path>`, `-c k=v`, `--git-dir=`, `--work-tree=`) let a commit land on main under `main_protection=strict`. The same `commit\b` regex also wrongly matched `git commit-graph`. Detection now lives in a shared tokenizer in `_shared.py` (`command_git_commit_targets` / `command_has_git_commit`) that skips global options, matches the `commit` subcommand exactly (so `commit-graph` / `git merge` / `git log --grep=commit` are ignored), and resolves the commit's effective target worktree from `-C` / `--work-tree`. main_protection now reasons about WHERE a commit lands, which also fixes the inverse false-positive (a `git -C <other> commit` launched from main was being blocked). `check-worktree-branch-match.py` shares the same detector. Pre-existing since 0.2.4; still fails open on any error.

## [0.5.1] - 2026-06-04

### Fixed

- **`main_protection` now actually blocks `NotebookEdit` on main.** `hooks/check-main-edit.py` is registered on the `Edit|Write|NotebookEdit` matcher but only read `tool_input.file_path` - which `NotebookEdit` payloads do not carry (they use `notebook_path`). NotebookEdit edits to files inside the main worktree therefore slipped through (empty target -> early return) under `main_protection=strict`, contradicting the hook's stated scope. The hook now falls back to `notebook_path`, so notebook edits on main are guarded like ordinary Edit/Write. Pre-existing since 0.2.4; fails open as before.

## [0.5.0] - 2026-06-03

Plugin-native hooks release. All seven protective hooks are now registered by the plugin itself via `hooks/hooks.json` at the plugin root, instead of being installed into each project's `.claude/settings.json`. They activate automatically whenever the ddaro plugin is enabled and appear under the `Plugin` source in `/hooks`. Behavior is unchanged: every hook stays config-gated (reads `.ddaro/config.json`) and fail-open, so a project that has not opted in - or has the relevant mode `off` - sees zero noise and zero blocking. This removes the `.claude/settings.json` write that previously polluted projects (and that interfered with clean main-worktree syncs).

### Added

- **Plugin-native hook registration (`hooks/hooks.json`).** Registers all seven hooks at the plugin root: PreToolUse `Edit|Write|NotebookEdit` -> `check-main-edit.py`; PreToolUse `Edit|Write` -> `check-evidence.py`; PreToolUse `Bash` -> `check-main-bash.py` + `check-branch-naming.py` + `check-worktree-branch-match.py`; SessionStart -> `session-start-notice.py` + `cross-worktree-health.py`. No `hooks` field in `plugin.json` (auto-discovered from the root `hooks/` directory). Commands use `${CLAUDE_PLUGIN_ROOT}` so paths resolve on every platform.
- **`/ddaro:config migrate` action.** One-time upgrade helper. Scans `.claude/settings.json` and removes only the hook entries whose command references `${CLAUDE_PLUGIN_ROOT}/hooks/<ddaro script>` (the seven scripts above), dropping now-empty `hooks` arrays / matcher blocks and leaving every other hook untouched. Idempotent (no-op + "already clean" report when there is nothing to remove). `/ddaro:config` (no args) and `/ddaro:start` also detect leftover entries and offer to run it.

### Changed

- **`/ddaro:config <hook> <mode>` no longer edits `.claude/settings.json`.** The `main_protection` / `branch_naming` / `cross_worktree_check` / `branch_worktree_match` / `evidence_check` toggles now only write the chosen mode into `<main>/.ddaro/config.json`. The hook is already registered plugin-natively; the mode value alone decides whether it acts. The old y/n/x settings.json preview / merge / sentinel-removal flow is gone (from `/ddaro:config` and from the `/ddaro:start` Steps 6-9 setup prompts). The mode prompts themselves are unchanged.
- **SessionStart matcher.** The plugin-native SessionStart entry uses `"matcher": "startup|resume|clear|compact"` to fire on every session-start source, matching the prior no-matcher behavior under the current Claude Code schema (which requires an explicit matcher for plugin hooks).

### Migration

- Upgraders: run `/ddaro:config migrate` once per project to delete the now-redundant ddaro hook entries from `.claude/settings.json`. Not strictly required (Claude Code de-duplicates identical hook commands, so there is no double-fire), but it removes leftover cruft - including the legacy `main_protection` SessionStart entry that was written without a `matcher`.
- No `.ddaro/config.json` schema change (`schema_version` stays `2`). Existing mode values keep working as-is.

## [0.4.0] - 2026-05-28

Dev-cycle orchestration release. /ddaro:commit gains an opt-in `--verify` flag that runs the project's verify command(s) before committing, and /ddaro:merge grows a full CI orchestration phase (state machine, hard-capped fix loop, idempotency, confirm gate, sync-main diff preview) so the PR-path can be driven from branch-ready all the way to local-branch-synced. Three pre-existing hooks (branch_naming, cross_worktree_check, branch_worktree_match) that were queued in `[Unreleased]` ship in this release too.

### Added

- **`/ddaro:commit --verify` flag.** Opt-in. Runs the project's verify command(s) on the staged changes before committing. Discovery order: (1) `.ddaro/verify.json` primary (canonical machine contract with `commands: [{pattern, run}]` shape), (2) `.claude/CLAUDE.md` "Commands" section fallback (best-effort parse), (3) skip with warning. Routes by touched-file type from `git diff --cached --name-only`; each rule's command runs once with live-streamed output. On non-zero exit, the user gets a three-way choice: keep changes staged (default `k`), drop changes (`d`, runs `git restore`), or commit anyway (`c`, logged in the context MD for audit). Default behavior of /ddaro:commit (no flag) is byte-identical to 0.3.x.

- **Cooperative invariants for /ddaro:commit sessions.** Documentation-only, surfaced as a preamble to the /ddaro:commit section: pre-edit `git log -- <file>` recheck (TOCTOU defense against parallel sessions), read-before-edit (relies on the harness's PreToolUse:Edit enforcer; surfaced via --verify's failure mode), prereq fixes split into their own atomic commits (don't smuggle unrelated bug fixes into the chunk commit).

- **`/ddaro:merge` CI orchestration (PR path).** Step 9.5 polls `gh pr view --json statusCheckRollup` every 20s with a 20-minute wall-clock cap and live progress prints. On CI_FAIL, three-way user choice: analyze+fix (Claude reads `gh run view --log-failed`, proposes a fix, commits via /ddaro:commit, pushes `--force-with-lease`, increments `fix_attempts`), skip (`--admin` override hint), escalate (abort with PR URL). Hard cap on `fix_attempts` defaults to 3 (configurable via `/ddaro:config ci_fix_cap <N>`, range 1..10, per-worktree). A distinct CI_STUCK state ("no checks reported in 60s") does NOT consume a fix-loop slot — it escalates with a wait / manual-dispatch / abort menu, because retrying a code fix on infra silence wastes the budget.

- **Explicit state machine for /ddaro:merge.** Documented at the top of the /ddaro:merge section: `IDLE → FETCHED → CHECKED → CI_PENDING → CI_PASS/FAIL/STUCK → MERGED → SYNCED`. Terminal states (MERGED, SYNCED, ABORTED, ESCALATED), forbidden transitions (no MERGED → CI_PENDING; no CHECKED → MERGED on PR path), and stuck-state semantics are enumerated so re-entry from a half-completed previous invocation is well-defined.

- **Idempotency guard before squash merge.** Re-query `gh pr view <N> --json state` immediately before the merge call. If `state == MERGED`, skip the merge step and jump to step 10 (sync-main). Catches the TOCTOU window between CI_PASS observation and merge attempt that could otherwise produce a duplicate squash on a stale base.

- **Confirm gate before `gh pr merge`.** Step 9.6c prints the exact command and waits on an explicit `y` (default `n`). Squash-merging is irreversible from the branch perspective; accidental Enter does not ship code.

- **Post-merge sync-main with content-diff preview.** Step 11a (default in 0.4.0, paired with `--delete-branch=false`) shows the difference between origin/main and the local branch BEFORE resetting. Non-empty "local has, main doesn't" bucket = visible abort signal that the squash didn't capture the work. Matches the project-side `git sync-main` alias guard (content-diff, not ancestry), so behavior is consistent whether the user runs the alias or lets /ddaro:merge drive it.

- **Push safety invariant.** All pushes initiated by /ddaro:merge (including fix-loop pushes) use `git push --force-with-lease` rather than bare `--force`. Parallel-session pushes are aborted instead of silently overwritten.

- **`evidence_check` hook (`hooks/check-evidence.py`).** Opt-in PreToolUse hook on Edit / Write / NotebookEdit. Levels: `off` (default, silent), `warn` (print reminder to stderr, allow), `strict` (require fresh `.ddaro/evidence-token` within `evidence_token_ttl_seconds` mtime OR `ALLOW_NO_EVIDENCE=1` env var, else block with exit 2). The hook is honest about what it can't do — PreToolUse hooks don't see chat history — so "evidence" is an external sentinel the session opts in to (`touch .ddaro/evidence-token`). Pure stdlib Python. Fails open on any error. Toggle: `/ddaro:config evidence_check <off|warn|strict>`. Bypass: `ALLOW_NO_EVIDENCE=1 <cmd>`.

- **Branch-naming enforcement hook.** *(was in [Unreleased] queue, shipping now)* New optional guard `branch_naming` (off / warn / strict) blocks `git checkout -b <name>` / `git switch -c <name>` / `git branch <name>` / `git worktree add -b <name>` when the proposed branch doesn't follow the project's `name_pool` convention. `hooks/check-branch-naming.py` (PreToolUse Bash) reads `.ddaro/config.json` and validates against:
  - `d-<city>` and `d-<city>/<topic>` (cities from active `name_pool`)
  - `feat|fix|chore|docs|refactor|test|style|build|ci|perf/<topic>-<city>`
  - `backup/d-<city>-<...>`
  - `main` / `master` / `develop` / `release/*` / `hotfix/*` / `ddaro/*` / `dependabot/*`
  Solves the "non-ddaro `git checkout -b <topic>` creates an orphan branch with no city marker, can't tell which worktree it came from later" problem. Set up via `/ddaro:start` Step 7 prompt (defaults to `strict`) or `/ddaro:config branch_naming <off|warn|strict>` after the fact. One-shot bypass: `ALLOW_NON_DDARO_BRANCH=1 <cmd>`. Fails open when `.ddaro/config.json` is missing or `branch_naming` is `off`.

- **Cross-worktree health check (SessionStart).** *(was in [Unreleased] queue, shipping now)* New optional guard `cross_worktree_check` (on / off). At every Claude Code session start, scans every ddaro-managed worktree (`protected_worktrees` + `git worktree list`) and reports per-worktree any of: tracked-deleted files, behind cached origin, uncommit count, stale (per `stale_days`). Silent when all clean (zero token cost). Catches the foot-gun where you forget you have uncommit work in another physical worktree. `hooks/cross-worktree-health.py`. Set up via `/ddaro:start` Step 8 prompt (defaults to `on`) or `/ddaro:config cross_worktree_check <on|off>`.

- **Worktree-branch match check.** *(was in [Unreleased] queue, shipping now)* New optional guard `branch_worktree_match` (off / warn / strict) blocks `git commit` when the worktree's city marker (extracted from cwd basename, e.g. `*-d-busan`) doesn't match the current branch's city marker (e.g. branch `d-namyangju`). Catches the foot-gun where `git switch` jumped branches but the user forgot which physical worktree they were in. `hooks/check-worktree-branch-match.py` (PreToolUse Bash). Set up via `/ddaro:start` Step 9 prompt (defaults to `strict`) or `/ddaro:config branch_worktree_match <off|warn|strict>`. One-shot bypass: `ALLOW_WORKTREE_BRANCH_MISMATCH=1 <cmd>`. Skips when either side has no city marker (e.g. main worktree, or a system branch like `main` -- those are handled by `main_protection` and `branch_naming` respectively).

### Changed

- **`/ddaro:merge` default merge cleanup is now reuse-branch.** The post-merge hand-off (steps 10/11) now defaults to the reuse-branch path (`--delete-branch=false` on the squash command, content-diff preview before `git reset --hard origin/main`), matching the project-side `git sync-main` pattern documented in the README. The legacy delete-branch path is preserved as an opt-in alternative for users who prefer the one-worktree-per-PR convention.

### Config

New keys (all per-worktree, all opt-in / safe defaults):

- `evidence_check` (off / warn / strict, default `off`)
- `evidence_token_ttl_seconds` (30..86400, default 300)
- `ci_fix_cap` (1..10, default 3)
- `cross_worktree_check` (on / off, default `on` per first-time setup, persisted user choice thereafter)
- `branch_naming` (off / warn / strict)
- `branch_worktree_match` (off / warn / strict)

## [0.3.1] - 2026-04-23

Install-blocking fix. 0.3.0 refused to install against recent Claude Code builds with "Validation errors: hooks: Invalid input". The plugin.json field `"hooks": "./hooks/"` (a directory path) does not match the hooks schema, which expects event/matcher/command entries. Our hook scripts are installed imperatively by `/ddaro:config main_protection strict` (merged into the user's `.claude/settings.json`), not auto-loaded by the plugin manifest, so the field was never doing anything useful. It has been removed.

### Fixed

- **`plugin.json` no longer declares `"hooks": "./hooks/"`.** Claude Code's updated plugin validator rejected this string-form hooks value. The Python hook scripts (`./hooks/check-main-bash.py`, `check-main-edit.py`, `session-start-notice.py`) still ship inside the plugin tree and are still installed into the user's `.claude/settings.json` by `/ddaro:config main_protection <warn|strict>` (and by Step 6 of `/ddaro:start` first-time setup). No behaviour change — just metadata that was blocking install.

### Known follow-ups (carried from 0.3.0)

- `skills/ddaro/SKILL.md` body sections for start / resume / abandon / config still need syncing to the new command-file spec.

## [0.3.0] - 2026-04-23

Surface-area pruning + opinionated first-time setup. This is a minor-breaking release: two subcommands are removed in favor of flags on existing ones, and the `/ddaro:start` first-run flow is opinionated enough to warrant a minor bump. Legacy aliases still route, so existing muscle memory prints a one-line deprecation and then works.

### Added

- **First-time `/ddaro:start` is now a 6-step setup.** Step 0 explicitly asks "is `<cwd>` your main worktree?" — if the user says no (or gives a different path), config is saved pointing at that path and the command refuses to create a worktree from the wrong cwd. This eliminates the "oops I ran start from the parent folder and now ddaro thinks /home is main" foot-gun. Step 6 prompts for `main_protection` with **strict as the default** — Enter installs the hooks immediately.
- **`main_protection` is opt-out instead of opt-in.** New users get the hook by default; the prompt is a one-line Enter to accept. Previous 0.2.x behaviour (off by default) survives via `off` choice.
- **`/ddaro:status` auto-delegates to `/ddaro:list` when cwd is main.** Previously it refused and suggested `/ddaro:list` as a separate command; now it just runs the inventory view inline. Worktree-local behaviour unchanged.
- **`/ddaro:abandon <name> --force` now accepts adopted (Tier 2) targets.** Previously refused with a raw-git recipe; now the same 3-layer confirmation flow handles adopted with an "ADOPTED target — original_branch: <...>" banner in the preview. `--force` is required (extra guard since the branch usually pre-exists the adopt). `--delete-remote` opts into remote branch deletion.
- **`/ddaro:resume [name] [--recap-only] [--all]`** now covers Tier 2 (adopted) worktrees too, supports positional `<name>` for direct resume, and folds in the former `/ddaro:summary` logic via `--recap-only`.
- **`/ddaro:config` with no args opens the interactive 9-item menu** (the behaviour previously split into `/ddaro:setting`). `/ddaro:config show` prints full config without the menu. `/ddaro:config <key> <value>` direct set is unchanged.
- **Hotfix example session** documented in README (EN + KO): feature worktree in flight → spawn isolated hotfix worktree → `merge --local` → `clear` → `/ddaro:resume` back into the feature with full context restored. No new command — just the normal pipeline applied in parallel.

### Changed

- **`/ddaro` dispatcher subcommand list** trimmed. `summary` and `setting` still route through as legacy aliases (`summary` → `resume --recap-only`, `setting` → `config`) with a one-line deprecation notice, then execute.

### Removed

- **`/ddaro:summary` command file** (`commands/ddaro-summary.md`). Its logic is inline in `/ddaro:resume` and callable via `--recap-only`. Legacy `/ddaro summary ...` still routes.
- **`/ddaro:setting` command file** (`commands/ddaro-setting.md`). The menu is now what `/ddaro:config` does with no args. Legacy `/ddaro setting` still routes.

### Migration notes

- Users upgrading from 0.2.x: no config migration. `main_protection` defaults to whatever was already in `config.json`; new installs get `strict`.
- Scripts or muscle memory using `/ddaro:summary` or `/ddaro:setting` directly (namespaced forms) will 404 — switch to `/ddaro:resume --recap-only` and `/ddaro:config` respectively. The `/ddaro <sub>` dispatcher form still accepts both as aliases for one more version.
- `/ddaro:abandon <name>` on an adopted worktree no longer prints a raw-git recipe — it asks for `--force`.

### Known follow-ups

- `skills/ddaro/SKILL.md` still needs the body sections for `## /ddaro:start`, `## /ddaro:resume`, `## /ddaro:abandon`, and `## /ddaro:config` synced to the new command-file spec. Command-file descriptions are authoritative for routing; SKILL.md is the behaviour contract and will be updated in a follow-up.

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
