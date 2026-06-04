"""Integration tests for check-branch-naming.py (branch_naming guard)."""

from __future__ import annotations

import pytest

from conftest import run_hook

HOOK = "check-branch-naming.py"
ALLOW = 0
BLOCK = 2

POOL = {"name_pool": "korea_city", "name_pools": {"korea_city": ["busan", "seoul", "daejeon"]}}


def _cfg(main_wt, **extra):
    main_wt.write_config(branch_naming="strict", **POOL, **extra)


def _bash(main_wt, command, env=None):
    return run_hook(HOOK, main_wt.payload("Bash", command=command), env=env)


def test_off_allows_any_branch(main_wt):
    main_wt.write_config(branch_naming="off", **POOL)
    assert _bash(main_wt, "git checkout -b whatever").returncode == ALLOW


def test_no_pool_allows(main_wt):
    main_wt.write_config(branch_naming="strict")  # no name_pools -> nothing to enforce
    assert _bash(main_wt, "git checkout -b whatever").returncode == ALLOW


@pytest.mark.parametrize(
    "command",
    [
        "git checkout -b d-busan",
        "git switch -c d-seoul/refactor",
        "git checkout -b feat/cleanup-busan",
        "git checkout -b backup/d-busan-premerge",
        "git checkout -b main",
        "git switch -c release/1.2",
        "git checkout -b ddaro/tmp",
        "git checkout -b dependabot/pip/x",
        "git status",                 # not a branch creation
    ],
)
def test_strict_allows_valid(main_wt, command):
    _cfg(main_wt)
    assert _bash(main_wt, command).returncode == ALLOW


@pytest.mark.parametrize(
    "command",
    [
        "git checkout -b random-topic",
        "git switch -c hotfixx",
        "git checkout -b feat/cleanup-tokyo",   # tokyo not in pool
        "git branch some-feature",
    ],
)
def test_strict_blocks_invalid(main_wt, command):
    _cfg(main_wt)
    r = _bash(main_wt, command)
    assert r.returncode == BLOCK
    assert "branch_naming" in r.stderr


def test_bypass_env_allows(main_wt):
    _cfg(main_wt)
    assert _bash(main_wt, "git checkout -b bad", env={"ALLOW_NON_DDARO_BRANCH": "1"}).returncode == ALLOW


def test_segment_bypass_allows(main_wt):
    _cfg(main_wt)
    cmd = "ALLOW_NON_DDARO_BRANCH=1 git checkout -b bad"
    assert _bash(main_wt, cmd).returncode == ALLOW
