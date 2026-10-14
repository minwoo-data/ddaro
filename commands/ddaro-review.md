---
name: ddaro:review
description: "Multi-angle review of a design doc or diff: a doc gets prism's 5 design lenses (is it sound?) + triad's 3 lenses (is it well written?) in parallel; a diff gets prism --diff (defect lenses + Evidence pass) + triad on any changed docs. Cross-check every code claim against real files, triage by severity + cross-model agreement, and collate findings back INTO the target as a '## Review findings' section with a fix list. Automates the design-review gate."
argument-hint: "<file> [--codex] [--diff] - e.g. docs/design/canonical-merge.md"
allowed-tools: [Agent, Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## /ddaro:review <file>" and execute with `$ARGUMENTS` as `<file> [flags]`.

- Read the target. If `--diff`, review the working/branch diff instead of a file (mirror `/ddaro:check` scoping).
- **Doc target** - fire 8 agents IN PARALLEL (one message): prism's 5 design angles (conflict & reuse / claim accuracy / devil's-advocate / robustness-4axis / improvement) + triad 3 lenses (LLM-implementability / architecture-longevity / decision-maker-comprehension). Every agent MUST verify the doc's file:line / behavior claims against the ACTUAL code, not take them on faith.
- **`--diff` target** - prism's 5 defect lenses on the diff (`/prism --diff` scoping: hunks + pre-change code + direct callers/callees + touched tests) with its Evidence pass, plus triad's 3 lenses on each markdown file the diff touches. triad >=0.2.0 refuses code, so never hand it source files; a code-only diff gets prism alone (say so in the section).
- Triage: severity CRIT/HIGH/MED/LOW; promote findings flagged by 2+ angles/lenses (agreement tier). Separate genuine contradictions for adjudication.
- Collate into the target: append a `## Review findings (<date> - prism + triad)` section + an ordered fix list. If reviewing a doc, also APPLY the fixes (or list them if the user prefers review-only).
- `--codex`: also run the real dual-engine versions (Claude + Codex): doc -> prism-all + triad-all; diff -> prism-all on the diff context + triad-all on changed docs. Default DEFERS Codex to the implementation-PR review for no-code docs (note this in the section, per the project's established cadence).
- If the skills are installed, invoke them: `/prism <doc>` (prism >=0.3.1 auto-selects its design lens set for markdown) or `/prism --diff`, and `/triad <doc>`. If `/prism` answers a doc with a refusal (prism 0.3.0 only), run the 5 design angles inline and note the version in the findings section. Without the skills, run the agents directly per the angle/lens prompts in SKILL.md.
- Output: the findings summary (top CRIT/HIGH) + confirm the section was written. Recommend implementing, then `/ddaro:check`.
