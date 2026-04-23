---
name: ddaro
description: "ddaro - worktree-based parallel workflow. Use subcommands via /ddaro:start, /ddaro:resume, /ddaro:commit, /ddaro:merge, /ddaro:status, /ddaro:list, /ddaro:summary, /ddaro:clear, /ddaro:abandon, /ddaro:setting, /ddaro:config. Or /ddaro <subcommand> [args]. Korean triggers: 따로, 병렬로, 분리해서, main 건드리지 마."
argument-hint: "<subcommand> [args] - start | resume | commit | merge | status | list | summary | clear | abandon | setting | config"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` fully, then:

- If `$ARGUMENTS` is empty, show a brief overview of all subcommands and recommend `/ddaro:start` for first-time users.
- If `$ARGUMENTS[0]` matches one of: `start`, `resume`, `commit`, `merge`, `clear`, `status`, `list`, `summary`, `abandon`, `setting`, `config` - execute the matching section in the skill document using the remaining arguments.
- Otherwise, report "unknown subcommand" and list valid ones.

Follow the procedures in SKILL.md exactly. Do not skip config checks, worktree scans, deletion-flag prompts, or lock-file creation.
