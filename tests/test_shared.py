"""Unit tests for the shared git-commit detection helpers in _shared.py.

These guard the robust tokenizer that replaced a `git\\s+commit` regex which
missed `git -C <path> commit` (a real main_protection bypass) and wrongly
matched `git commit-graph`.
"""

from __future__ import annotations

import json
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


# --- find_ddaro_config: sibling (linked-worktree) fallback ---
#
# `.ddaro/config.json` is gitignored, so a linked worktree usually has no
# config of its own. find_ddaro_config must still resolve the MAIN worktree's
# config (via the `.git` file -> gitdir -> commondir chain) or every hook
# silently no-ops there. These guard that resolution.

def _make_linked_worktree(tmp_path, *, with_commondir=True, **cfg_overrides):
    """Build a minimal main + linked-worktree layout. Returns (main, linked).
    main carries .ddaro/config.json; linked has a `.git` FILE pointing into
    main's .git/worktrees/<name>."""
    main_root = tmp_path / "main"
    wt_gitdir = main_root / ".git" / "worktrees" / "wt1"
    wt_gitdir.mkdir(parents=True)
    if with_commondir:
        (wt_gitdir / "commondir").write_text("../..\n", encoding="utf-8")
    cfg = {"schema_version": 2, "main_worktree": main_root.as_posix()}
    cfg.update(cfg_overrides)
    (main_root / ".ddaro").mkdir(parents=True)
    (main_root / ".ddaro" / "config.json").write_text(
        json.dumps(cfg), encoding="utf-8"
    )
    linked = tmp_path / "wt1"
    linked.mkdir()
    (linked / ".git").write_text(
        f"gitdir: {wt_gitdir.as_posix()}\n", encoding="utf-8"
    )
    return main_root, linked


def test_find_config_sibling_fallback_via_commondir(tmp_path):
    main_root, linked = _make_linked_worktree(tmp_path, branch_naming="strict")
    cfg = _shared.find_ddaro_config(linked)
    assert cfg is not None
    assert cfg["branch_naming"] == "strict"
    assert cfg["main_worktree"] == main_root.as_posix()


def test_find_config_local_takes_priority_over_sibling(tmp_path):
    # A linked worktree with its OWN config -> parent walk wins; the sibling
    # fallback is never consulted.
    _main_root, linked = _make_linked_worktree(tmp_path, branch_naming="strict")
    (linked / ".ddaro").mkdir()
    (linked / ".ddaro" / "config.json").write_text(
        json.dumps({"schema_version": 2, "branch_naming": "warn"}),
        encoding="utf-8",
    )
    assert _shared.find_ddaro_config(linked)["branch_naming"] == "warn"


def test_find_config_fallback_layout_without_commondir(tmp_path):
    # No commondir file -> positional <gitdir>.parent.parent.parent fallback.
    main_root, linked = _make_linked_worktree(tmp_path, with_commondir=False)
    cfg = _shared.find_ddaro_config(linked)
    assert cfg is not None
    assert cfg["main_worktree"] == main_root.as_posix()


def test_find_config_none_when_main_has_no_config(tmp_path):
    # Linked worktree whose main carries no .ddaro/config.json -> None, no crash.
    main_root = tmp_path / "main"
    wt_gitdir = main_root / ".git" / "worktrees" / "wt1"
    wt_gitdir.mkdir(parents=True)
    (wt_gitdir / "commondir").write_text("../..\n", encoding="utf-8")
    linked = tmp_path / "wt1"
    linked.mkdir()
    (linked / ".git").write_text(
        f"gitdir: {wt_gitdir.as_posix()}\n", encoding="utf-8"
    )
    assert _shared.find_ddaro_config(linked) is None


def test_find_config_none_for_plain_dir(tmp_path):
    # Not a worktree, no config anywhere -> None (no subprocess, no crash).
    assert _shared.find_ddaro_config(tmp_path) is None
