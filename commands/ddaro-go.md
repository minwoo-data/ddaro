---
name: ddaro:go
description: "Conductor entry point - read the worktree's lifecycle stage and run the next step (spec -> review -> implement -> check) automatically, instead of remembering which subcommand to call. Detects state, confirms before heavy stages (review/check), executes the matching spec/review/check section, advances the stage, and points at the next step. The manual /ddaro:spec | review | check stay available for forcing a specific stage."
argument-hint: "[spec|review|check] - no arg = auto-detect + run the next stage; an arg forces that stage"
allowed-tools: [Agent, Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## /ddaro:go [stage]" and execute with `$ARGUMENTS`.

- Precondition: must be inside a ddaro worktree (reuse the `/ddaro status` cwd detection). In main -> tell the user which worktree to `cd` into; not under ddaro -> suggest `/ddaro:start` or `/ddaro:adopt`.
- Determine the current stage from `.ddaro/lifecycle.json` if present, else infer it (design doc exists? has a `## Review findings` section? are there code changes beyond the doc?).
- If `$1` is `spec` / `review` / `check`, force that stage (manual override / re-run); otherwise run the auto-detected next stage.
- Before a heavy stage (review = 8 agents, check = prism-all), state what it will fire and confirm. The spec stage's `[DECIDE]` items are still asked interactively.
- Execute the corresponding `## /ddaro:spec` / `## /ddaro:review` / `## /ddaro:check` section - do NOT reimplement them. The conductor only sequences them.
- After the stage completes, advance `.ddaro/lifecycle.json` and tell the user the next step (re-run `/ddaro:go`). At the review -> implement boundary, STOP - the human implements, then runs `/ddaro:go` again to reach check.

This is the auto-transmission over the manual spec/review/check gears. It never touches git history; only `/ddaro:commit` / `/ddaro:merge` do.
