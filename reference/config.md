# ddaro config (`<main_worktree>/.ddaro/config.json`)

```json
{
  "schema_version": 3,
  "main_worktree": "C:/path/to/myapp",
  "project_name": "myapp",
  "base_branch": "main",
  "auto_snapshot": "on",
  "protected_worktrees": ["C:/path/to/myapp"],
  "external_patterns": [".claude/worktrees/agent-*", ".git/worktrees/*"],
  "planning_patterns": [".planning/**", ".gsd/**", "STATE.md", "ROADMAP.md", "CHANGELOG.md"],
  "max_concurrent": 10,
  "warn_threshold": 5,
  "stale_days": 7,
  "naming_strategy": "d-number",
  "name_pool": "korea_city",
  "name_pools": {
    "animal": ["otter","panda","fox","owl","seal","koala","squirrel","whale","hedgehog","penguin","sloth","beaver","rabbit","finch","bear","wolf","deer","mole"],
    "korea_city": ["seoul","busan","incheon","daegu","daejeon","gwangju","ulsan","suwon","jeju","pohang","gyeongju","jeonju","andong","chuncheon","gangneung","mokpo","sokcho","yeosu","tongyeong","jinju"],
    "us_state": ["ca","ny","tx","fl","wa","or","co","az","ma","il","pa","oh","mi","ga","nc","va","nj","tn","in","md"],
    "fruit": ["peach","kiwi","mango","plum","lime","berry","fig","guava","lychee","apricot"],
    "greek": ["alpha","beta","gamma","delta","epsilon","zeta","eta","theta","iota","kappa"]
  },
  "language": "english",
  "context_persistence": true,
  "main_protection": "off"
}
```

Fields:
- `schema_version` 3. `hooks/config_tool.py ensure-schema` migrates (fills `base_branch`, `auto_snapshot`), idempotent, atomic, keeps unknown keys.
- `base_branch`: branch merged into (`<base>`). Absent = `main`. Wrong value shows as clear seeing merged branches as unmerged, or a huge ahead count; fix with `/ddaro:config base_branch <name>`.
- `auto_snapshot` `on`|`off`: gates only the PostToolUse snapshot hook (`off` = snapshots only via /ddaro:commit). `context_persistence: false` disables every context write.
- `protected_worktrees` / `external_patterns`: tiers 3 / 5 (see `reference/tiers.md`). `planning_patterns`: files /ddaro:start treats as planning when main is dirty.
- `max_concurrent` (hard cap), `warn_threshold` (soft), `stale_days` (STALE marker).
- `naming_strategy`: `d-number` (d-1, d-2; numbers never reused), `d-pool` (d-<pool name>), `ddaro-number`, `ddaro-pool`. `name_pool`: key into `name_pools`.
- `language`: `english` | `korean` for all output.
- Hook modes (`main_protection`, `branch_naming`, `branch_worktree_match`, `evidence_check`, `cross_worktree_check`, ...): see `reference/hooks.md`.
- `ci_fix_cap` 1..10 (default 3): /ddaro:merge CI fix-loop cap. `evidence_token_ttl_seconds` 30..86400 (default 300).

## First-time setup (no config found)

1. Ask: "Is `<cwd>` your main worktree (the receiver folder ddaro never edits)? yes / no / other path". If another path: it must be a `git worktree list` entry; save the config there (step 2-3), then print `cd <main>` + `/ddaro:start` and stop without creating anything.
2. Ask in order (number menus, default in brackets) and write the answers with the JSON above as the template:
   1. language [english] / korean
   2. main worktree [cwd] (auto-detected candidates from `git worktree list`)
   3. sibling folders to protect: all / comma list / none [main only]
   4. naming strategy [d-number] / d-pool / ddaro-number / ddaro-pool
   5. name pool [korea_city] / animal / us_state / fruit / greek
   6. `main_protection` [strict] / warn / off - blocks direct `git commit` / Edit / Write on main (merges and `planning_patterns` still pass; bypass `ALLOW_MAIN_DIRECT=1 <cmd>`)
   7. `branch_naming` [strict] / off - branch names must carry a pool marker (bypass `ALLOW_NON_DDARO_BRANCH=1`)
   8. `cross_worktree_check` [on] / off - SessionStart drift report, silent when clean
   9. `branch_worktree_match` [strict] / off - blocks a commit when the folder's marker and the branch's differ (bypass `ALLOW_WORKTREE_BRANCH_MISMATCH=1`)
   Hooks are plugin-native: writing the mode is all that is needed; never edit `.claude/settings.json`.
3. Write `schema_version: 2` with the wizard keys only, then run `python "${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py" ensure-schema <main>` and show its line (it records `base_branch` and `auto_snapshot`), adding "if the base branch is wrong: /ddaro:config base_branch <name>".
4. If cwd is main, continue with /ddaro:start; otherwise stop after the cd instructions.
