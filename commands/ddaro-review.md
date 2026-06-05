---
name: ddaro:review
description: "Dual-engine multi-angle review of a doc or diff: fire prism-all (5 angles) + triad (3 lenses) in parallel, cross-check every code claim against real files, triage by severity + cross-model agreement, and collate findings back INTO the target as a '## Review findings' section with a fix list. Automates the design-review gate."
argument-hint: "<file> [--codex] [--diff] - e.g. docs/design/canonical-merge.md"
allowed-tools: [Agent, Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## /ddaro:review <file>" and execute with `$ARGUMENTS` as `<file> [flags]`.

- Read the target. If `--diff`, review the working/branch diff instead of a file (mirror `/ddaro:check` scoping).
- Fire 8 agents IN PARALLEL (one message): prism 5 angles (conflict / devil's-advocate / improvement / code-review / robustness-4axis) + triad 3 lenses (LLM-implementability / architecture-longevity / decision-maker-comprehension). Every agent MUST verify the doc's file:line / behavior claims against the ACTUAL code, not take them on faith.
- Triage: severity CRIT/HIGH/MED/LOW; promote findings flagged by 2+ angles/lenses (agreement tier). Separate genuine contradictions for adjudication.
- Collate into the target: append a `## Review findings (<date> - prism + triad)` section + an ordered fix list. If reviewing a doc, also APPLY the fixes (or list them if the user prefers review-only).
- `--codex`: also run the real dual-engine prism-all + triad-all (Claude + Codex). Default DEFERS Codex to the implementation-PR review for no-code docs (note this in the section, per the project's established cadence).
- If `prism-all` / `triad` skills are installed, invoke them; else run the 8 agents directly per the angle/lens prompts in this section.
- Output: the findings summary (top CRIT/HIGH) + confirm the section was written. Recommend implementing, then `/ddaro:check`.
