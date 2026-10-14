# ddaro worktree tiers

Every entry of `git worktree list --porcelain` is classified, first match wins:

1. path == `config.main_worktree` -> **main** (receives merges; ddaro never mutates it)
2. path matches a glob in `config.external_patterns` (e.g. `.claude/worktrees/agent-*`) -> **external** (other tools; ignore entirely)
3. path is in `config.protected_worktrees` -> **protected** (user said "do not touch"; read-only display)
4. `<path>/.ddaro/OWNED` exists -> **adopted** if `.ddaro/LOCK` has `"adopted": true`, else **owned**
5. otherwise -> **unmanaged** (shown, never acted on until adopted)

Order matters: a stray `OWNED` in the main worktree does not make it ddaro's, and any worktree can be shielded by adding it to `protected_worktrees`.

| Command | main | owned | adopted | protected | unmanaged | external |
|---|---|---|---|---|---|---|
| start (create) | - | - | - | refuse | - | refuse |
| adopt | refuse | refuse | refuse | refuse | **yes** | refuse |
| commit / merge / clear / resume | refuse | yes | yes | refuse | refuse | refuse |
| abandon | refuse | yes | only with `--force` | refuse | refuse | refuse |
| list | show | show | show | show | show | show |
| status | show list | yes | yes | show | show | - |

Owned and adopted behave the same everywhere except `abandon` (ddaro does not force-discard what it did not create unless told `--force`).
