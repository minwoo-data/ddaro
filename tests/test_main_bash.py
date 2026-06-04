"""Integration tests for check-main-bash.py (main_protection git-commit guard).

Exercises the real hook via subprocess against a tmp main worktree. The
target-aware detection (closing the `git -C <main> commit` bypass) is proven
here end-to-end.
"""

from __future__ import annotations

from conftest import run_hook

HOOK = "check-main-bash.py"
ALLOW = 0
BLOCK = 2


# --- config gating ---

def test_off_allows_commit(main_wt):
    main_wt.write_config(main_protection="off")
    p = main_wt.payload("Bash", command="git commit -m x")
    assert run_hook(HOOK, p).returncode == ALLOW


def test_warn_does_not_block(main_wt):
    main_wt.write_config(main_protection="warn")
    p = main_wt.payload("Bash", command="git commit -m x")
    assert run_hook(HOOK, p).returncode == ALLOW


def test_no_config_allows(main_wt):
    # main_wt created .ddaro/ but we never write config.json -> not a ddaro project
    p = main_wt.payload("Bash", command="git commit -m x")
    assert run_hook(HOOK, p).returncode == ALLOW


def test_non_bash_tool_ignored(main_wt):
    main_wt.write_config(main_protection="strict")
    p = main_wt.payload("Edit", command="git commit")  # tool_name Edit
    assert run_hook(HOOK, p).returncode == ALLOW


# --- strict: block / allow matrix ---

def test_strict_blocks_plain_commit(main_wt):
    main_wt.write_config(main_protection="strict")
    p = main_wt.payload("Bash", command="git commit -m x")
    r = run_hook(HOOK, p)
    assert r.returncode == BLOCK
    assert "main_protection" in r.stderr


def test_strict_blocks_dash_C_into_main(main_wt):
    """The headline bypass: `git -C <main> commit` used to slip through."""
    main_wt.write_config(main_protection="strict")
    cmd = f"git -C {main_wt.root.as_posix()} commit -m x"
    assert run_hook(HOOK, main_wt.payload("Bash", command=cmd)).returncode == BLOCK


def test_strict_blocks_work_tree_into_main(main_wt):
    main_wt.write_config(main_protection="strict")
    cmd = f"git --work-tree={main_wt.root.as_posix()} commit"
    assert run_hook(HOOK, main_wt.payload("Bash", command=cmd)).returncode == BLOCK


def test_strict_blocks_commit_with_global_config(main_wt):
    main_wt.write_config(main_protection="strict")
    cmd = "git -c user.name=x commit -m x"
    assert run_hook(HOOK, main_wt.payload("Bash", command=cmd)).returncode == BLOCK


def test_strict_blocks_chained_commit(main_wt):
    main_wt.write_config(main_protection="strict")
    cmd = "git status && git commit -m y"
    assert run_hook(HOOK, main_wt.payload("Bash", command=cmd)).returncode == BLOCK


def test_strict_allows_dash_C_other_dir(main_wt, tmp_path):
    """Commit explicitly targeting another worktree must NOT be blocked."""
    main_wt.write_config(main_protection="strict")
    other = tmp_path.parent / "elsewhere"
    cmd = f"git -C {other.as_posix()} commit -m x"
    assert run_hook(HOOK, main_wt.payload("Bash", command=cmd)).returncode == ALLOW


def test_strict_allows_commit_graph(main_wt):
    main_wt.write_config(main_protection="strict")
    cmd = "git commit-graph write"
    assert run_hook(HOOK, main_wt.payload("Bash", command=cmd)).returncode == ALLOW


def test_strict_allows_merge(main_wt):
    main_wt.write_config(main_protection="strict")
    cmd = "git merge feature"
    assert run_hook(HOOK, main_wt.payload("Bash", command=cmd)).returncode == ALLOW


def test_strict_allows_non_git(main_wt):
    main_wt.write_config(main_protection="strict")
    cmd = "python build.py && echo done"
    assert run_hook(HOOK, main_wt.payload("Bash", command=cmd)).returncode == ALLOW


# --- bypass ---

def test_bypass_env_allows(main_wt):
    main_wt.write_config(main_protection="strict")
    p = main_wt.payload("Bash", command="git commit -m x")
    r = run_hook(HOOK, p, env={"ALLOW_MAIN_DIRECT": "1"})
    assert r.returncode == ALLOW


def test_fail_open_on_garbage_payload():
    # malformed stdin -> hook must allow (fail open), never crash to block
    import subprocess
    import sys
    from conftest import HOOKS_DIR

    r = subprocess.run(
        [sys.executable, str(HOOKS_DIR / HOOK)],
        input="not json at all",
        capture_output=True,
        text=True,
    )
    assert r.returncode == ALLOW
