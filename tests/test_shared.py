"""Unit tests for the shared git-commit detection helpers in _shared.py.

These guard the robust tokenizer that replaced a `git\\s+commit` regex which
missed `git -C <path> commit` (a real main_protection bypass) and wrongly
matched `git commit-graph`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import _shared  # noqa: E402

import pytest  # noqa: E402


# --- detection (target-agnostic bool) ---

@pytest.mark.parametrize(
    "command, expected",
    [
        ("git commit -m x", True),
        ("git commit", True),
        ("git commit --amend --no-edit", True),
        ("git -C /some/path commit", True),          # global -C before subcommand
        ("git -c user.name=x commit", True),         # -c k=v consumes its arg
        ("git --work-tree=/w commit", True),         # inline --opt=value
        ("git --git-dir=/g/.git commit -m y", True),
        ("git status && git commit -m y", True),     # chained
        ("ls; git commit", True),                    # after ';'
        ("/usr/bin/git commit", True),               # absolute git path
        # must NOT match:
        ("git commit-graph write", False),           # different subcommand
        ("git merge feature", False),                # merge is allowed on main
        ("git log --grep=commit", False),            # 'commit' only as an arg
        ("git rebase --continue", False),
        ("echo please git commit later", True),      # 'git commit' as words -> conservative match
        ("echo hello world", False),
        ("", False),
    ],
)
def test_command_has_git_commit(command, expected):
    assert _shared.command_has_git_commit(command) is expected


# --- target resolution (where the commit lands) ---

def test_target_defaults_to_cwd(tmp_path):
    assert _shared.command_git_commit_targets("git commit -m x", tmp_path) == [tmp_path]


def test_target_dash_C_absolute(tmp_path):
    other = tmp_path / "other"
    cmd = f"git -C {other.as_posix()} commit"
    assert _shared.command_git_commit_targets(cmd, tmp_path) == [other]


def test_target_dash_C_relative(tmp_path):
    # -C is resolved relative to cwd
    assert _shared.command_git_commit_targets("git -C sub commit", tmp_path) == [
        tmp_path / "sub"
    ]


def test_target_work_tree_inline(tmp_path):
    wt = tmp_path / "wt"
    cmd = f"git --work-tree={wt.as_posix()} commit"
    assert _shared.command_git_commit_targets(cmd, tmp_path) == [wt]


def test_git_dir_does_not_move_worktree(tmp_path):
    # --git-dir points at the .git, not the worktree -> target stays cwd
    cmd = "git --git-dir=/elsewhere/.git commit"
    assert _shared.command_git_commit_targets(cmd, tmp_path) == [tmp_path]


def test_two_commits_two_targets(tmp_path):
    other = tmp_path / "o"
    cmd = f"git commit -m a; git -C {other.as_posix()} commit -m b"
    assert _shared.command_git_commit_targets(cmd, tmp_path) == [tmp_path, other]


def test_non_commit_yields_no_targets(tmp_path):
    assert _shared.command_git_commit_targets("git commit-graph write", tmp_path) == []
    assert _shared.command_git_commit_targets("git merge x", tmp_path) == []
