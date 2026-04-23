# Round 1 — ddaro/skills/ddaro/SKILL.md

**Target**: `C:\00_AI_SANDBOX\minwoo-plugins\ddaro\skills\ddaro\SKILL.md` (661 lines)
**Mode**: read-only (no `--apply`)
**Started**: 2026-04-23T03:15:00
**Result**: all 3 perspectives returned `REVISE` → continue to R2 if fixes are not applied first

---

## LLM Perspective

```yaml
verdict: REVISE
top_issues:
  - severity: high
    locus: "SKILL.md:225, 269, 318, 368, 379, 404, 429, 491, 512, 549"
    problem: "Section headings use `/ddaro start` / `/ddaro commit` (space form), but the Commands table (lines 24-33) uses `/ddaro:start` / `/ddaro:commit` (colon form). LLM cannot determine whether `:` is required or optional."
    proposed_fix: "Rename every section heading to colon form (10 headings). Keep line 35 as the sole note that space form is also accepted."
  - severity: high
    locus: "SKILL.md:339-341 (merge step 6)"
    problem: "`mangchi` is listed as a valid `--review` override but never defined, described, or linked anywhere in the file."
    proposed_fix: "Either remove `mangchi` from line 341 or add a line defining each override value."
  - severity: high
    locus: "SKILL.md:121-122 (Layer 2) vs. 246-247 (step 7) vs. 657"
    problem: "`<worktree>/.git/` is a FILE pointing to `<main>/.git/worktrees/<name>/`, not a directory. `touch <worktree>/.git/ddaro-owned` will fail or write to the wrong place."
    proposed_fix: "Either resolve via `git rev-parse --git-path ddaro-owned` (per-worktree gitdir) or move the flag out of `.git/` entirely (e.g. `<worktree>/.ddaro/OWNED`). Lines 121, 139, 247-248, 383, 657-658."
  - severity: med
    locus: "SKILL.md:250"
    problem: "`echo \"*\" > <worktree>/.ddaro/.gitignore` ignores children of `.ddaro/`, not `.ddaro/` itself. The directory entry itself is still tracked."
    proposed_fix: "Append `.ddaro/` to `<main_worktree>/.gitignore` if not present, instead of per-dir `.gitignore`."
  - severity: med
    locus: "SKILL.md:347 (Local path)"
    problem: "'Claude cannot cd to main worktree' is false for Claude Code. Also, the copy-paste text is not specified, unlike /ddaro:start step 8."
    proposed_fix: "Replace with a concrete block like `cd <main_worktree> && git merge d-<name> && git push`. Drop the 'Claude cannot cd' claim."
  - severity: med
    locus: "SKILL.md:296"
    problem: "Auto message uses em-dash (—); pre-commit hooks may reject non-ASCII. Line 131 forbids --no-verify, so there is no escape."
    proposed_fix: "Use ASCII `-`. Add fallback: 'If hook rejects, stop and ask user; do not retry with --no-verify.'"
  - severity: med
    locus: "SKILL.md:244 (start step 6)"
    problem: "`git worktree add <project>-d-<name>` is a relative path; result depends on cwd, but cwd at invocation time is unspecified."
    proposed_fix: "Use `git -C <main_worktree> worktree add <main_worktree>/../<project>-d-<name> ...` and state 'always sibling of main_worktree'."
  - severity: low
    locus: "SKILL.md:339"
    problem: "Size bands: `<50, ≤2` (strict+non) / `50–300, 3–10` / `>300 OR >10`. Boundary at 50 lines is ambiguous."
    proposed_fix: "Single consistent scheme: small = `lines≤50 AND files≤2`; medium = otherwise AND `lines≤300 AND files≤10`; large = `lines>300 OR files>10`."
  - severity: low
    locus: "SKILL.md:152"
    problem: "'warns on mismatch' without specifying whether subcommand aborts, confirms, or proceeds."
    proposed_fix: "Add: 'Print mismatch; prompt y/n; default abort.'"
open_questions:
  - "Is `mangchi` a supported merge-review override (line 341), and if so what does it do?"
  - "Where should the ownership flag actually live — per-worktree gitdir or a plain file outside `.git/`?"
  - "At `/ddaro:start` invocation, what is assumed cwd — main worktree, project root, arbitrary?"
```

---

## Architect Perspective

```yaml
verdict: REVISE
top_issues:
  - severity: high
    locus: "SKILL.md:138-165, 169-222"
    problem: "Context MD system duplicates git log/diff/status. Every commit writes two MD files that must be regenerated + kept consistent + parsed by /ddaro:summary. Five touchpoints (writer, overwriter, reader, archive, templates) shift together. Schema will drift within a year."
    proposed_fix: "Drop CURRENT.md (derivable from git + lock + latest snapshot on demand). Keep per-commit snapshots only if the Claude-generated 'What was done' line earns its cost. Trade-off: lose pre-rendered resume hint, gain one source of truth."
  - severity: high
    locus: "SKILL.md:114-134 + 491-509"
    problem: "3-layer protection spread across 3 disjoint stores (config list + flag file + runtime typed confirm). Invariants are implicit — no single function owns the check. Adding a 4th protection need touches every destructive subcommand."
    proposed_fix: "Define a single `can_destroy(worktree)` predicate as the sole gate for every destructive op. All three layers live inside it. Trade-off: one abstraction, future protections become one-line additions."
  - severity: high
    locus: "SKILL.md:243-250, 353-362"
    problem: "Lock/owned files under `.git/` couple to git internals. Files placed there are not stable across `git worktree remove/repair`, `gc --aggressive`, or future git versions. Irreplaceable assumption."
    proposed_fix: "Move `ddaro-owned` and `ddaro-lock` into `<worktree>/.ddaro/`. Single location, no git coupling."
  - severity: med
    locus: "SKILL.md:337-341"
    problem: "`triad` / `prism` skill names are hardcoded cross-plugin dependencies with no fallback documented. Rename/remove breaks /ddaro:merge silently."
    proposed_fix: "Document the contract: 'merge expects a skill accepting a unified diff and returning verdict'. Add `review_skill_{small,medium,large}` config with null=skip fallback."
  - severity: med
    locus: "SKILL.md:70-97, 556"
    problem: "No `schema_version` in config. Adding/renaming keys will silently mis-load old configs. `/ddaro:config init` is not a migration."
    proposed_fix: "Add `schema_version: 1`. On load, if mismatch, run named migration before use."
  - severity: med
    locus: "SKILL.md:276"
    problem: "`git add -A` + no `--no-verify` (line 132) means any artifacts outside .gitignore (monorepo side-effects) get silently staged with no opt-out."
    proposed_fix: "Add `stage_strategy` config: `all` / `tracked` / `interactive`. Default `all`."
  - severity: low
    locus: "SKILL.md:41-66"
    problem: "Five built-in name_pools (animal/korea_city/us_state/fruit/greek) are YAGNI. A single `string[]` would do."
    proposed_fix: "Reduce to `name_pool: string[]` with documented default. Drop named presets."
open_questions:
  - "Is crash recovery genuinely needed beyond `git log main..HEAD --stat` + `git status`?"
  - "Will ddaro ever support non-git VCS (jj, sapling)? That would invalidate `.git/` placements."
  - "Who reconciles `protected_worktrees` when user manually deletes a sibling folder?"
  - "Any lockfile on main for concurrent `/ddaro:merge`? §649 says 'merge one at a time' but doesn't enforce."
```

---

## EndUser Perspective

```yaml
verdict: REVISE
top_issues:
  - severity: high
    locus: "SKILL.md:1-17 (frontmatter + intro)"
    problem: "First 30 lines answer 'what' but not WHY. Terms 'worktree', 'lock files', 'deletion-aware', 'context snapshots' drop without explaining the underlying pain. Beginner asks: 'do I even have this problem?'"
    proposed_fix: "After line 14 insert 'Why this exists' block. Draft: 'Running two Claude Code sessions at once? They overwrite each other. Close VS Code mid-task? The plan Claude had is gone. ddaro: one isolated folder per session + every commit writes a plain-text recap to disk.'"
  - severity: high
    locus: "SKILL.md:10-20"
    problem: "5-min test #3 (how do I start?) fails. Reader scrolls through 10 tables before seeing any usage. First walkthrough is at line 578."
    proposed_fix: "Add a 'Quick start (30 seconds)' section right after 'Why' and before Commands table. Draft: `/ddaro:start` → `cd <project>-d-1` → edit → `/ddaro:commit \"msg\"` → `/ddaro:merge`."
  - severity: high
    locus: "SKILL.md:41-46, 114-134"
    problem: "Mechanism without motive. Reader is told 'worktree folder: <project>-d-<name>', '1=1=1', '3 layers of protection' without WHY worktrees (vs. branches) or WHY three layers."
    proposed_fix: "Above line 39 add: 'A git worktree is a second working folder that shares the repo but checks out a different branch — two Claude sessions can edit independently.' Above line 114 add: 'Why three layers? Because abandon deletes real work. Each layer catches a different mistake.'"
open_questions:
  - "Target reader: developer opening on GitHub + Claude at runtime. Should human-friendly 'why + quickstart' live at top of SKILL.md, or only in README.md?"
  - "Is there a concrete before/after screenshot / transcript to replace the abstract 'main is never touched'?"
```

---

## Synthesis (main agent)

**Issue counts:** 9 high / 7 med / 3 low across 3 perspectives. No PASS — R2 warranted unless R1 fixes are applied first.

**Overlap detected:**
- LLM#3 (`.git/ddaro-owned` path) ≈ Architect#3 (git-internal coupling) — **converge on moving ownership flag to `<worktree>/.ddaro/OWNED`** (both agree; Architect's framing is more load-bearing).
- EndUser#3 (mechanism without motive for 3-layer) partially overlaps Architect#2 (single `can_destroy()` predicate) — different axis (doc vs. code structure) but same symptom.

### Priority ranking (accept / defer / reject)

| # | Issue | Perspective | Verdict | Rationale |
|---|---|---|---|---|
| 1 | Section heading colon form | LLM high | **ACCEPT (trivial fix)** | 10 heading renames; no design cost. |
| 2 | `mangchi` merge override undefined | LLM high | **ACCEPT** | Remove from line 341 (simpler), or define (more work). Default: remove. |
| 3 | `.git/ddaro-owned` path broken in worktree | LLM+Arch high | **ACCEPT** | Move to `<worktree>/.ddaro/OWNED` + `<worktree>/.ddaro/LOCK`. Closes both LLM#3 and Arch#3 at once. |
| 4 | "Why this exists" intro block | EndUser high | **ACCEPT** | 1 paragraph at line 14 — no design cost. |
| 5 | Quick Start walkthrough | EndUser high | **ACCEPT** | 1 fenced code block before Commands table. |
| 6 | Mechanism-without-motive on 3-layer | EndUser high | **ACCEPT** | 1 sentence above §114 + 1 sentence above §39. |
| 7 | `.gitignore` `*` scope wrong | LLM med | **ACCEPT** | Append `.ddaro/` to main .gitignore; or use `<worktree>/.ddaro/.gitignore` with pattern excluding `.ddaro/` at parent level. |
| 8 | False "Claude cannot cd" + missing copy-paste | LLM med | **ACCEPT** | Replace with explicit block. |
| 9 | em-dash in auto commit | LLM med | **ACCEPT** | ASCII only. |
| 10 | Relative worktree path | LLM med | **ACCEPT** | Anchor to `main_worktree`. |
| 11 | Size-band boundary ambiguity | LLM low | **ACCEPT** | 3-line rewrite. |
| 12 | Drop CURRENT.md | Arch high | **DEFER to R2** | Design-impact decision — needs user preference. CURRENT.md was specifically added for crash-recovery UX. |
| 13 | `can_destroy()` predicate | Arch high | **DEFER to R2** | Code-design change, not doc change. Affects implementation order, not v0.1.0 spec. |
| 14 | `review_skill_*` fallback config | Arch med | **DEFER to R2** | New config key — adds surface; weigh vs. YAGNI. |
| 15 | `schema_version` in config | Arch med | **ACCEPT** | 1-line addition; cheap insurance. |
| 16 | `stage_strategy` config | Arch med | **DEFER to R2** | YAGNI check — is `git add -A` actually biting users? No reports yet. |
| 17 | Drop 5 built-in name_pools | Arch low | **REJECT** | Presets are a UX feature, not bloat. Keep. |
| 18 | "warns on mismatch" spec gap | LLM low | **ACCEPT** | 1-line spec tightening. |

**Deferred = 3 HIGH/MED design questions for user** — not mechanical fixes.

---

## Applied changes this round

`--apply` not set. No `updated.md` generated. Recommendations only.

---

## Open issues for R2

1. **Drop CURRENT.md?** (Architect high) — design call.
2. **`can_destroy()` predicate** (Architect high) — defer unless v0.1.1 scope allows refactor.
3. **`review_skill_*` fallback** (Architect med) — does plugin need hard dependency on triad/prism, or soft fallback?
4. **`stage_strategy`** (Architect med) — add now or wait for first user bug report?
5. **SKILL.md role** (EndUser open_question) — dense runtime context vs. human-friendly first-read? If README covers beginner UX, SKILL.md can stay dense.
6. **cwd at `/ddaro:start`** (LLM open_question) — spec needs to state the invariant.

---

## Next step

**Option A (recommended)** — apply the 12 ACCEPT items as a v0.1.1 doc-fix commit, then run R2 focused only on the 6 open issues.

**Option B** — skip R1 fixes, run R2 now with the open_questions surfaced. Pro: parallel deliberation on design calls. Con: agents will re-surface accepted items.

**Option C** — stop here (`/triad --stop`), treat this as the review artifact, and address items in a later iteration.
