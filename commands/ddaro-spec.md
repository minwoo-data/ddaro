---
name: ddaro:spec
description: "Scaffold a design/PRD doc + capture locked decisions before building. Enforces Search-Before-Building (greps existing code into a Reuse inventory), fixed section skeleton, and a [DECIDE] checklist. Front half of the dev cycle - run inside a ddaro worktree before implementing."
argument-hint: "<name> [target-path] - e.g. canonical-merge docs/design/canonical-merge.md"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## /ddaro:spec <name>" and execute with `$ARGUMENTS` as `<name> [target-path]`.

- Resolve target path: `$2` if given, else `docs/design/<name>.md`. Refuse to overwrite an existing doc without confirm.
- **Search-Before-Building (mandatory):** grep `src/services/`, `src/routes/`, and siblings for symbols related to `<name>`; record what already exists + the reuse/extend decision in a "Reuse inventory" table. A spec with an empty inventory for a non-greenfield feature is incomplete - say so.
- Scaffold the fixed skeleton: TL;DR (decision) / Problem / Evidence / Reuse inventory / Options table (verdict per row) / Locked decisions / Slices + per-slice gates / Schema (if any) / UI (if any) / Test plan / Rollback / Open questions / Out of scope.
- Fill what the conversation already settled; mark every unresolved gray area as `[DECIDE]` inline.
- Capture Locked decisions explicitly: for each gray area, either record the user's stated choice or ASK (do not silently default).
- If a `doc-template` skill is installed, use it for the skeleton instead of hand-rolling.
- Output: the doc path + a checklist of remaining `[DECIDE]` items, and recommend `/ddaro:review <path>` next.
