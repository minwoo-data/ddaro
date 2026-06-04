"""Integration tests for check-worktree-branch-match.py.

Blocks `git commit` when the worktree's city marker (from cwd basename) does
not match the current branch's city marker. Uses a real throwaway git repo so
the hook's `git symbolic-ref` call resolves a branch.
"""

from __future__ import annotations

import json
import subprocess
import sys

from conftest import HOOKS_DIR

HOOK = "check-worktree-branch-match.py"
ALLOW = 0
BLOCK = 2
CITIES = ["busan", "seoul", "daejeon"]


def _make_repo(tmp_path, dirname, branch, level="strict"):
    root = tmp_path / dirname
    (root / ".ddaro").mkdir(parents=True)
    cfg = {
        "schema_version": 2,
        "main_worktree": root.as_posix(),
        "branch_worktree_match": level,
        "name_pool": "korea_city",
        "name_pools": {"korea_city": CITIES},
    }
    (root / ".ddaro" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", branch], cwd=root, check=True)
    return root


def _run(root, command="git commit -m x", env=None):
    payload = {
        "tool_name": "Bash",
        "cwd": root.as_posix(),
        "tool_input": {"command": command},
    }
    import os

    child_env = {k: v for k, v in os.environ.items() if not k.startswith("ALLOW_")}
    if env:
        child_env.update(env)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=child_env,
    )


def test_mismatch_blocks(tmp_path):
    root = _make_repo(tmp_path, "proj-d-busan", "d-seoul")
    r = _run(root)
    assert r.returncode == BLOCK
    assert "branch_worktree_match" in r.stderr


def test_match_allows(tmp_path):
    root = _make_repo(tmp_path, "proj-d-busan", "d-busan")
    assert _run(root).returncode == ALLOW


def test_off_allows_mismatch(tmp_path):
    root = _make_repo(tmp_path, "proj-d-busan", "d-seoul", level="off")
    assert _run(root).returncode == ALLOW


def test_non_city_worktree_allows(tmp_path):
    # cwd basename has no -d-<city> marker -> hook skips (main itself, etc.)
    root = _make_repo(tmp_path, "plainproject", "d-seoul")
    assert _run(root).returncode == ALLOW


def test_non_city_branch_allows(tmp_path):
    # branch has no city marker -> check-branch-naming owns that, this skips
    root = _make_repo(tmp_path, "proj-d-busan", "feature-x")
    assert _run(root).returncode == ALLOW


def test_commit_graph_not_treated_as_commit(tmp_path):
    # mismatch dir+branch, but `git commit-graph` is not a commit -> allow
    root = _make_repo(tmp_path, "proj-d-busan", "d-seoul")
    assert _run(root, command="git commit-graph write").returncode == ALLOW


def test_bypass_env_allows(tmp_path):
    root = _make_repo(tmp_path, "proj-d-busan", "d-seoul")
    assert _run(root, env={"ALLOW_WORKTREE_BRANCH_MISMATCH": "1"}).returncode == ALLOW
