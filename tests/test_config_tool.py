"""Tests for hooks/config_tool.py (detect / verify / ensure-schema / set).

Uses throwaway git repos so each fallback stage of the detection order is
exercised for real: origin/HEAD -> local main -> local master -> "main".
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import config_tool  # noqa: E402

from conftest import HOOKS_DIR  # noqa: E402

SCRIPT = HOOKS_DIR / "config_tool.py"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(tmp_path: Path, name: str, initial_branch: str) -> Path:
    root = tmp_path / name
    root.mkdir()
    _git(root, "init", "-q", "-b", initial_branch)
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
         "--allow-empty", "-m", "init")
    return root


def _write_cfg(root: Path, **extra) -> Path:
    (root / ".ddaro").mkdir(exist_ok=True)
    cfg = {"schema_version": 2, "main_worktree": root.as_posix()}
    cfg.update(extra)
    p = root / ".ddaro" / "config.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return p


def _read_cfg(root: Path) -> dict:
    return json.loads((root / ".ddaro" / "config.json").read_text(encoding="utf-8"))


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


# --- detect_base_branch() fallback order ---

def test_origin_head_wins(tmp_path):
    remote = _repo(tmp_path, "remote", "trunk")
    local = tmp_path / "local"
    subprocess.run(["git", "clone", "-q", remote.as_posix(), local.as_posix()],
                   check=True, capture_output=True)
    assert config_tool.detect_base_branch(local) == "trunk"


def test_local_main_when_no_origin(tmp_path):
    assert config_tool.detect_base_branch(_repo(tmp_path, "r", "main")) == "main"


def test_local_master_when_no_main(tmp_path):
    assert config_tool.detect_base_branch(_repo(tmp_path, "r", "master")) == "master"


def test_fallback_main_when_nothing_matches(tmp_path):
    assert config_tool.detect_base_branch(_repo(tmp_path, "r", "develop")) == "main"


def test_non_git_dir_falls_back(tmp_path):
    assert config_tool.detect_base_branch(tmp_path) == "main"


# --- detect / verify CLI ---

def test_cli_detect_prints_branch(tmp_path):
    root = _repo(tmp_path, "r", "master")
    r = _cli("detect", root.as_posix())
    assert r.returncode == 0 and r.stdout.strip() == "master"


def test_cli_verify_exit_codes(tmp_path):
    root = _repo(tmp_path, "r", "master")
    assert _cli("verify", root.as_posix(), "master").returncode == 0
    assert _cli("verify", root.as_posix(), "main").returncode == 1


def test_cli_verify_accepts_remote_only_base(tmp_path):
    """A base that exists only as origin/<name> (never checked out) is valid."""
    remote = _repo(tmp_path, "remote", "trunk")
    local = tmp_path / "local"
    subprocess.run(["git", "clone", "-q", remote.as_posix(), local.as_posix()],
                   check=True, capture_output=True)
    _git(local, "checkout", "-q", "-b", "work")
    _git(local, "branch", "-q", "-D", "trunk")          # local trunk gone, origin/trunk stays
    assert _cli("verify", local.as_posix(), "trunk").returncode == 0
    assert _cli("verify", local.as_posix(), "nope").returncode == 1


def test_cli_usage_error():
    assert _cli("bogus").returncode == 2


# --- ensure-schema ---

def test_ensure_schema_fills_missing_keys_and_bumps(tmp_path):
    root = _repo(tmp_path, "r", "master")
    _write_cfg(root)
    r = _cli("ensure-schema", root.as_posix())
    assert r.returncode == 0
    assert "schema 3" in r.stdout
    cfg = _read_cfg(root)
    assert cfg["base_branch"] == "master"
    assert cfg["auto_snapshot"] == "on"
    assert cfg["schema_version"] == 3
    assert cfg["main_worktree"] == root.as_posix()  # untouched


def test_ensure_schema_is_idempotent(tmp_path):
    root = _repo(tmp_path, "r", "master")
    _write_cfg(root)
    _cli("ensure-schema", root.as_posix())
    before = (root / ".ddaro" / "config.json").read_text(encoding="utf-8")
    r = _cli("ensure-schema", root.as_posix())
    assert r.returncode == 0 and r.stdout == ""
    assert (root / ".ddaro" / "config.json").read_text(encoding="utf-8") == before


def test_ensure_schema_keeps_existing_base_branch(tmp_path):
    root = _repo(tmp_path, "r", "master")
    _write_cfg(root, base_branch="develop")  # user-set, does not resolve
    r = _cli("ensure-schema", root.as_posix())
    assert r.returncode == 0
    assert "not found" in r.stderr
    assert _read_cfg(root)["base_branch"] == "develop"


def test_ensure_schema_keeps_existing_auto_snapshot(tmp_path):
    root = _repo(tmp_path, "r", "main")
    _write_cfg(root, auto_snapshot="off")
    _cli("ensure-schema", root.as_posix())
    assert _read_cfg(root)["auto_snapshot"] == "off"


def test_ensure_schema_missing_config_is_noop(tmp_path):
    root = _repo(tmp_path, "r", "main")
    r = _cli("ensure-schema", root.as_posix())
    assert r.returncode == 0 and r.stdout == ""
    assert not (root / ".ddaro" / "config.json").exists()


def test_ensure_schema_preserves_unknown_keys(tmp_path):
    root = _repo(tmp_path, "r", "master")
    _write_cfg(root, some_future_key={"nested": [1, 2]}, language="korean")
    _cli("ensure-schema", root.as_posix())
    cfg = _read_cfg(root)
    assert cfg["some_future_key"] == {"nested": [1, 2]}
    assert cfg["language"] == "korean"
    assert not list((root / ".ddaro").glob(".config.*.tmp"))  # temp file cleaned up


def test_set_missing_config_exit_1(tmp_path):
    root = _repo(tmp_path, "r", "main")
    assert _cli("set", root.as_posix(), "auto_snapshot", "off").returncode == 1


# --- set ---

def test_set_writes_key(tmp_path):
    root = _repo(tmp_path, "r", "master")
    _write_cfg(root)
    assert _cli("set", root.as_posix(), "auto_snapshot", "off").returncode == 0
    assert _read_cfg(root)["auto_snapshot"] == "off"


def test_set_base_branch_warns_but_writes(tmp_path):
    root = _repo(tmp_path, "r", "master")
    _write_cfg(root)
    r = _cli("set", root.as_posix(), "base_branch", "nope")
    assert r.returncode == 0 and "not found" in r.stderr
    assert _read_cfg(root)["base_branch"] == "nope"
