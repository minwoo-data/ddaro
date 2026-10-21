---
name: ddaro
description: "Worktree-per-session git workflow for parallel Claude sessions. /ddaro <start|commit|merge|resume|status|list|clear|adopt|abandon|config|go|spec|review|check> [args]. Triggers: 따로, 병렬로, 분리해서, main 건드리지 마."
argument-hint: "<subcommand> [args]"
allowed-tools: [Agent, Bash, Read, Write, Edit, Glob, Grep, Skill]
---

# /ddaro

- `$ARGUMENTS` starts with `start`, `adopt`, `resume`, `commit`, `merge`, `clear`, `status`, `list`, `abandon`, `config`, `go`, `spec`, `review`, or `check`: read `${CLAUDE_PLUGIN_ROOT}/commands/ddaro-<subcommand>.md` and follow it exactly with the remaining arguments. Read no other ddaro file unless that file points to one.
- Legacy aliases: `summary` -> `resume --recap-only`, `setting` -> `config`; print "note: renamed - use /ddaro:<new>" first.
- Empty: one line per subcommand (start: new worktree / adopt: take over an existing one / commit / merge / resume / status / list / clear: remove merged / abandon: discard / config / go: next lifecycle stage / spec / review / check), and recommend `/ddaro:start` (or `/ddaro:adopt <path>` for an existing worktree).
- Anything else: "unknown subcommand" + the list.
