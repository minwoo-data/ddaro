# Usage Guide

Common scenarios with exact command sequences.

---

## Scenario 1 - First time setup

```
/ddaro:start
  → Claude detects no config, runs 5-step setup
  → Pick language, main worktree, protect list, naming, pool
  → Config saved, worktree created with auto name (d-1)
  → Copy-paste prompt shown - open new terminal, cd, paste
```

---

## Scenario 2 - Daily workflow

```
/ddaro:start feature-name        # creates myapp-d-feature-name worktree
# [in new terminal, cd, claude session]
# edit files...
/ddaro:commit "add foo"          # pushes automatically
# edit more...
/ddaro:commit "wire up bar"
/ddaro:merge                     # pre-flight check, auto review, y/n cleanup
```

---

## Scenario 3 - Crash recovery

After VS Code or Claude Code session dies:

```
# open new terminal
cd <worktree-path>
claude
# inside new session:
/ddaro:summary
  → Claude reads commits, diffs, .ddaro/context/*.md
  → Full recap of what was done + where it stopped
# continue where you left off
```

---

## Scenario 4 - Parallel work (2+ worktrees)

Session A:
```
/ddaro:start auth-fix    # creates d-auth-fix
```

Session B (separate Claude Code window):
```
/ddaro:start billing     # creates d-billing
```

Both run independently. Physical folder isolation prevents collisions. Each has its own branch, lock, context dir.

To see all at once:
```
/ddaro:list
```

---

## Scenario 5 - Abandoning bad work

```
/ddaro:abandon d-experiment
  → Shows destruction preview (commits lost, snapshots lost)
  → User must type 'yes, I'm sure'
  → Worktree + branch + remote branch all deleted
```

---

## Scenario 6 - Returning after days

```
/ddaro:summary                   # one-line per worktree
/ddaro:summary d-old-work        # detailed recap of that one
# Decide: continue / merge / clean / abandon
```

---

## Scenario 7 - Stale cleanup

After several worktrees accumulate:

```
/ddaro:list
  → Shows ⚠ STALE entries past stale_days
/ddaro:clean d-stale-1           # merged ones get cleaned
/ddaro:abandon d-never-used       # unmerged ones get abandoned (with typed confirm)
```

---

## Scenario 8 - Tuning

Try animal names instead of numbers:
```
/ddaro:setting
  → 2 (naming strategy)
  → 2 (d-pool)
  → back to main menu
  → 3 (name pool)
  → 1 (animal)
# Next /ddaro:start will auto-name d-otter, d-panda, ...
```

Or direct:
```
/ddaro:config naming d-pool
/ddaro:config pool animal
```

Change language mid-work:
```
/ddaro:config language korean
# All subsequent output in Korean
```

---

## Scenario 9 - Single-worktree mental model

Think of it this way:

```
main worktree       = the clean copy you ship from
ddaro worktrees     = disposable scratch copies for each task
context MDs         = written memory so your Claude session can't forget
lock file           = "this worktree is running branch X, don't mess with it"
3-layer protection  = "even if you mess with it, ddaro won't delete it"
```

The whole system is: work safely in isolation → review before merging → clean up on the way out.
