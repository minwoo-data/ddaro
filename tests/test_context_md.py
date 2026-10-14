"""Integration tests for hooks/context_md.py (hook / init / write / enrich).

Fixture mirrors real ddaro usage: a MAIN repo on `master` carries
`.ddaro/config.json`; a LINKED worktree (`git worktree add`) carries only
`.ddaro/OWNED` + LOCK. That exercises `find_ddaro_config`'s commondir
fallback and `worktree_root`'s `.git`-file handling, not just the happy
path where config sits next to the commit.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import context_md  # noqa: E402

from conftest import HOOKS_DIR  # noqa: E402

SCRIPT = HOOKS_DIR / "context_md.py"
GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@t"]


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *GIT_ID, *args], cwd=cwd, check=True, capture_output=True, text=True)
    return r.stdout.strip()


def _run(args, stdin: str = "", env: dict | None = None) -> subprocess.CompletedProcess:
    child = {k: v for k, v in os.environ.items() if not k.startswith("DDARO_")}
    if env:
        child.update(env)
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin,
                          capture_output=True, text=True, env=child)


def _hook(cwd: Path, command: str, env: dict | None = None) -> subprocess.CompletedProcess:
    payload = {"tool_name": "Bash", "cwd": cwd.as_posix(), "tool_input": {"command": command},
               "tool_response": {}}
    return _run(["hook"], stdin=json.dumps(payload), env=env)


class Proj:
    def __init__(self, tmp_path: Path, base: str = "master", cfg_base: str | None = None, **cfg_extra):
        self.main = tmp_path / "proj"
        self.main.mkdir()
        _git(self.main, "init", "-q", "-b", base)
        base = cfg_base or base
        (self.main / ".gitignore").write_text(".ddaro/\n", encoding="utf-8")
        _git(self.main, "add", ".gitignore")
        _git(self.main, "commit", "-q", "-m", "init")
        (self.main / ".ddaro").mkdir()
        cfg = {"schema_version": 3, "main_worktree": self.main.as_posix(), "base_branch": base}
        cfg.update(cfg_extra)
        (self.main / ".ddaro" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        self.wt = tmp_path / "proj-d-busan"
        _git(self.main, "worktree", "add", "-q", self.wt.as_posix(), "-b", "d-busan")
        (self.wt / ".ddaro" / "context").mkdir(parents=True)
        (self.wt / ".ddaro" / "OWNED").touch()
        (self.wt / ".ddaro" / "LOCK").write_text(
            json.dumps({"branch": "d-busan", "topic": "restore last view", "main_worktree": self.main.as_posix()}),
            encoding="utf-8")

    def commit(self, name: str, msg: str, cwd: Path | None = None) -> str:
        cwd = cwd or self.wt
        (self.wt / name).write_text(f"{name}\n{msg}\n", encoding="utf-8")
        _git(self.wt, "add", name)
        _git(self.wt, "commit", "-q", "-m", msg)
        return _git(self.wt, "rev-parse", "--short=7", "HEAD")

    def snapshots(self):
        return sorted((self.wt / ".ddaro" / "context").glob("*.md"))

    def current(self) -> str:
        return (self.wt / ".ddaro" / "CURRENT.md").read_text(encoding="utf-8")


@pytest.fixture
def proj(tmp_path):
    return Proj(tmp_path)


# --- hook mode -----------------------------------------------------------

def test_hook_writes_snapshot_and_current(proj):
    sha = proj.commit("a.txt", "add a")
    r = _hook(proj.wt, "git commit -m 'add a'")
    assert r.returncode == 0
    snaps = proj.snapshots()
    assert len(snaps) == 1 and snaps[0].name.endswith(f"-{sha}.md")
    text = snaps[0].read_text(encoding="utf-8")
    assert text.splitlines()[0] == context_md.FORMAT_MARKER
    assert "## Files changed\n1 files, +2 -0\n- a.txt (+2 -0)" in text
    assert "**Ahead of base (master)**: 1 commit(s)" in text
    out = json.loads(r.stdout)
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert f"-{sha}.md (ahead 1)" in out["hookSpecificOutput"]["additionalContext"]
    cur = proj.current()
    assert cur.splitlines()[0] == context_md.FORMAT_MARKER
    assert f"1. [" in cur and f"Commit {sha} - add a" in cur
    assert "- Last goal: restore last view" in cur
    assert "**Uncommit**: none" in cur


def test_hook_is_idempotent(proj):
    proj.commit("a.txt", "add a")
    _hook(proj.wt, "git commit -m x")
    r = _hook(proj.wt, "git commit -m x")
    assert r.returncode == 0 and r.stdout == ""
    assert len(proj.snapshots()) == 1


def test_journey_accumulates_after_init(proj):
    assert _run(["init", proj.wt.as_posix(), "--topic", "restore last view"]).returncode == 0
    cur = proj.current()
    assert "1. [" in cur and "Worktree created, branch d-busan from master@" in cur
    proj.commit("a.txt", "first")
    _hook(proj.wt, "git commit -m first")
    proj.commit("b.txt", "second")
    _hook(proj.wt, "git commit -m second")
    journey = [ln for ln in proj.current().splitlines() if ln[:2] in ("1.", "2.", "3.")]
    assert len(journey) == 3
    assert journey[0].startswith("1. ") and "Worktree created" in journey[0]
    assert journey[1].startswith("2. ") and "first" in journey[1]
    assert journey[2].startswith("3. ") and "second" in journey[2]


def test_journey_preserved_from_markerless_legacy_current(proj):
    """0.7.0 wrote CURRENT.md by prompt (no marker); upgrading must not lose its Journey."""
    legacy = "\n".join([
        "# d-busan - Current State", "", "**Branch**: d-busan", "",
        "## Journey so far",
        "1. [09:00] Worktree created, branch d-busan from main@abc1234",
        "2. [09:30] Commit 1111111 - legacy", "",
        "## Currently", "Idle", "",
    ])
    (proj.wt / ".ddaro" / "CURRENT.md").write_text(legacy, encoding="utf-8")
    proj.commit("a.txt", "add a")
    r = _hook(proj.wt, "git commit -m 'add a'")
    assert "journey reset" not in r.stderr
    journey = [ln for ln in proj.current().splitlines() if ln[:2] in ("1.", "2.", "3.")]
    assert len(journey) == 3 and "legacy" in journey[1] and journey[2].startswith("3. ")


def test_hook_from_subdirectory_writes_at_root(proj):
    sub = proj.wt / "src" / "deep"
    sub.mkdir(parents=True)
    sha = proj.commit("a.txt", "add a")
    r = _hook(sub, "git commit -m 'add a'")
    assert r.returncode == 0
    assert proj.snapshots()[0].name.endswith(f"-{sha}.md")


def test_hook_dash_C_targets_other_worktree(proj, tmp_path):
    sha = proj.commit("a.txt", "add a")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    r = _hook(elsewhere, f"git -C {proj.wt.as_posix()} commit -m 'add a'")
    assert r.returncode == 0
    assert proj.snapshots()[0].name.endswith(f"-{sha}.md")
    assert not (elsewhere / ".ddaro").exists()


def test_hook_ignores_main_worktree_commit(proj):
    (proj.main / "m.txt").write_text("m\n", encoding="utf-8")
    _git(proj.main, "add", "m.txt")
    _git(proj.main, "commit", "-q", "-m", "on main")
    r = _hook(proj.main, "git commit -m 'on main'")
    assert r.returncode == 0 and r.stdout == ""
    assert not (proj.main / ".ddaro" / "context").exists()


def test_hook_ignores_non_commit_commands(proj):
    proj.commit("a.txt", "add a")
    r = _hook(proj.wt, "git status && git log --grep=commit")
    assert r.returncode == 0 and r.stdout == ""
    assert proj.snapshots() == []


@pytest.mark.parametrize("extra", [{"auto_snapshot": "off"}, {"context_persistence": False}])
def test_hook_respects_config_gates(tmp_path, extra):
    p = Proj(tmp_path, **extra)
    p.commit("a.txt", "add a")
    r = _hook(p.wt, "git commit -m x")
    assert r.returncode == 0 and r.stdout == ""
    assert p.snapshots() == []


def test_hook_skips_stale_head_outside_window(proj):
    proj.commit("a.txt", "add a")
    r = _hook(proj.wt, "git commit -m x", env={"DDARO_SNAPSHOT_WINDOW_SEC": "-1"})
    assert r.returncode == 0 and r.stdout == ""
    assert proj.snapshots() == []


def test_hook_ahead_falls_back_to_origin_then_question_mark(tmp_path):
    p = Proj(tmp_path, cfg_base="nope")   # config.base_branch points at a missing ref
    p.commit("a.txt", "add a")
    _hook(p.wt, "git commit -m x")
    text = p.snapshots()[0].read_text(encoding="utf-8")
    assert "**Ahead of base (nope)**: ? commit(s)" in text


def test_hook_amend_marks_previous_superseded(proj):
    sha1 = proj.commit("a.txt", "add a")
    _hook(proj.wt, "git commit -m 'add a'")
    _git(proj.wt, "commit", "-q", "--amend", "-m", "add a (amended)")
    sha2 = _git(proj.wt, "rev-parse", "--short=7", "HEAD")
    assert sha1 != sha2
    _hook(proj.wt, "git commit --amend -m 'add a (amended)'")
    snaps = proj.snapshots()
    assert len(snaps) == 2
    old = next(s for s in snaps if s.name.endswith(f"-{sha1}.md")).read_text(encoding="utf-8")
    assert f"**Superseded by**: {sha2}" in old


def test_hook_fail_open_on_garbage_stdin():
    r = subprocess.run([sys.executable, str(SCRIPT), "hook"], input="not json",
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == ""


# --- write / enrich ---------------------------------------------------------

def test_write_creates_once_even_when_auto_snapshot_off(tmp_path):
    p = Proj(tmp_path, auto_snapshot="off")
    sha = p.commit("a.txt", "add a")
    r = _run(["write", p.wt.as_posix()])
    assert r.returncode == 0 and r.stdout.strip().endswith(f"-{sha}.md")
    r2 = _run(["write", (p.wt / "src").as_posix()]) if (p.wt / "src").mkdir() is None else None
    assert r2.returncode == 0 and r2.stdout == ""
    assert len(p.snapshots()) == 1


def test_enrich_overwrites_sections_keeps_journey_rerenders_header(proj):
    sha = proj.commit("a.txt", "add a")
    _hook(proj.wt, "git commit -m 'add a'")
    before_journey = [ln for ln in proj.current().splitlines() if ln.startswith("1. ")]
    payload = {"what_was_done": "분리한 복원 로직\n두 줄째", "next_planned": "테스트 추가",
               "review_flags": "None", "currently": "Idle (just committed)",
               "resume_hint": {"last_goal": "복원", "next_expected": "merge"}, "bogus": 1}
    r = _run(["enrich", proj.wt.as_posix(), sha], stdin=json.dumps(payload))
    assert r.returncode == 0 and r.stdout.strip() == f"enriched {sha}"
    assert "unknown key 'bogus'" in r.stderr
    text = proj.snapshots()[0].read_text(encoding="utf-8")
    assert "## What was done\n분리한 복원 로직\n두 줄째\n\n## Next planned (inferred)\n테스트 추가\n\n## Review flags raised\nNone\n" in text
    assert "## Commit message\nadd a\n" in text  # untouched
    cur = proj.current()
    assert [ln for ln in cur.splitlines() if ln.startswith("1. ")] == before_journey
    assert "## Currently\nIdle (just committed)" in cur
    assert "- Last goal: 복원" in cur and "- Next expected: merge" in cur
    assert f"- cwd: {proj.wt.resolve().as_posix()}" in cur


def test_enrich_creates_when_missing(proj):
    sha = proj.commit("a.txt", "add a")
    r = _run(["enrich", proj.wt.as_posix(), sha], stdin=json.dumps({"what_was_done": "x"}))
    assert r.returncode == 0 and r.stdout.strip() == f"created+enriched {sha}"
    assert len(proj.snapshots()) == 1
    assert "## What was done\nx\n" in proj.snapshots()[0].read_text(encoding="utf-8")


def test_enrich_refuses_file_without_marker(proj):
    sha = proj.commit("a.txt", "add a")
    (proj.wt / ".ddaro" / "context" / f"2026-01-01T00-00-00-{sha}.md").write_text(
        "# old format\n## What was done\nlegacy\n", encoding="utf-8")
    r = _run(["enrich", proj.wt.as_posix(), sha], stdin="{}")
    assert r.returncode == 1 and "marker" in r.stderr


def test_enrich_bad_json_exit_1(proj):
    sha = proj.commit("a.txt", "add a")
    assert _run(["enrich", proj.wt.as_posix(), sha], stdin="{not json").returncode == 1


def test_enrich_persistence_off_is_noop(tmp_path):
    p = Proj(tmp_path, context_persistence=False)
    sha = p.commit("a.txt", "add a")
    r = _run(["enrich", p.wt.as_posix(), sha], stdin="{}")
    assert r.returncode == 0 and "context_persistence" in r.stderr
    assert p.snapshots() == []


def test_init_adopted_and_no_overwrite(proj):
    r = _run(["init", proj.wt.as_posix(), "--topic", "t", "--adopted"])
    assert r.returncode == 0
    cur = proj.current()
    assert "1. [" in cur and "Adopted from external worktree, branch d-busan" in cur
    r2 = _run(["init", proj.wt.as_posix(), "--topic", "other"])
    assert r2.returncode == 0 and proj.current() == cur


def test_cli_refuses_unmanaged_path(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert _run(["write", plain.as_posix()]).returncode == 1
    assert _run(["init", plain.as_posix(), "--topic", "t"]).returncode == 1


def test_headings_match_reference_doc():
    """reference/context-files.md examples must use exactly the HEADINGS."""
    text = (HOOKS_DIR.parent / "reference" / "context-files.md").read_text(encoding="utf-8")
    found, in_fence = set(), False
    for ln in text.splitlines():
        s_ = ln.strip()
        if s_.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence and s_.startswith("## "):
            found.add(s_)
    assert found == set(context_md.HEADINGS.values())
