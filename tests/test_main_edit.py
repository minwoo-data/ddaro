"""Integration tests for check-main-edit.py (main_protection edit guard).

Covers Edit / Write / NotebookEdit, the planning_patterns allowlist, and the
0.5.1 NotebookEdit (`notebook_path`) fix.
"""

from __future__ import annotations

from conftest import run_hook

HOOK = "check-main-edit.py"
ALLOW = 0
BLOCK = 2


def _in_main(main_wt, rel: str) -> str:
    return (main_wt.root / rel).as_posix()


def test_off_allows_edit(main_wt):
    main_wt.write_config(main_protection="off")
    p = main_wt.payload("Edit", file_path=_in_main(main_wt, "src/app.py"))
    assert run_hook(HOOK, p).returncode == ALLOW


def test_warn_allows_edit(main_wt):
    main_wt.write_config(main_protection="warn")
    p = main_wt.payload("Write", file_path=_in_main(main_wt, "src/app.py"))
    assert run_hook(HOOK, p).returncode == ALLOW


def test_no_config_allows(main_wt):
    p = main_wt.payload("Edit", file_path=_in_main(main_wt, "src/app.py"))
    assert run_hook(HOOK, p).returncode == ALLOW


def test_strict_blocks_edit_in_main(main_wt):
    main_wt.write_config(main_protection="strict")
    p = main_wt.payload("Edit", file_path=_in_main(main_wt, "src/app.py"))
    r = run_hook(HOOK, p)
    assert r.returncode == BLOCK
    assert "main_protection" in r.stderr


def test_strict_blocks_write_in_main(main_wt):
    main_wt.write_config(main_protection="strict")
    p = main_wt.payload("Write", file_path=_in_main(main_wt, "README.txt"))
    assert run_hook(HOOK, p).returncode == BLOCK


def test_strict_blocks_notebook_in_main(main_wt):
    """0.5.1 fix: NotebookEdit carries notebook_path, not file_path."""
    main_wt.write_config(main_protection="strict")
    p = main_wt.payload("NotebookEdit", notebook_path=_in_main(main_wt, "analysis.ipynb"))
    assert run_hook(HOOK, p).returncode == BLOCK


def test_strict_allows_planning_path(main_wt):
    main_wt.write_config(main_protection="strict")
    p = main_wt.payload("Edit", file_path=_in_main(main_wt, ".planning/notes.md"))
    assert run_hook(HOOK, p).returncode == ALLOW


def test_strict_allows_notebook_in_planning(main_wt):
    main_wt.write_config(main_protection="strict")
    p = main_wt.payload("NotebookEdit", notebook_path=_in_main(main_wt, ".planning/x.ipynb"))
    assert run_hook(HOOK, p).returncode == ALLOW


def test_strict_allows_claude_dir(main_wt):
    main_wt.write_config(main_protection="strict")
    p = main_wt.payload("Edit", file_path=_in_main(main_wt, ".claude/settings.json"))
    assert run_hook(HOOK, p).returncode == ALLOW


def test_strict_allows_changelog(main_wt):
    main_wt.write_config(main_protection="strict")
    p = main_wt.payload("Write", file_path=_in_main(main_wt, "CHANGELOG.md"))
    assert run_hook(HOOK, p).returncode == ALLOW


def test_strict_allows_edit_outside_main(main_wt, tmp_path):
    main_wt.write_config(main_protection="strict")
    outside = (tmp_path.parent / "other-wt" / "app.py").as_posix()
    p = main_wt.payload("Edit", file_path=outside)
    assert run_hook(HOOK, p).returncode == ALLOW


def test_bypass_env_allows(main_wt):
    main_wt.write_config(main_protection="strict")
    p = main_wt.payload("Edit", file_path=_in_main(main_wt, "src/app.py"))
    assert run_hook(HOOK, p, env={"ALLOW_MAIN_DIRECT": "1"}).returncode == ALLOW


# --- 0.10.0 merge gate: run-folder allowance (merge-gate.md L5) ---

def _runs_file(main_wt) -> str:
    return _in_main(main_wt, ".ddaro/runs/d-busan.f486a3be/3-abc123/pass1.claude.security.txt")


def test_run_folder_write_allowed_when_gate_on(main_wt):
    for mode in ("warn", "strict"):
        main_wt.write_config(main_protection="strict", merge_gate=mode)
        assert run_hook(HOOK, main_wt.payload("Write", file_path=_runs_file(main_wt))).returncode == ALLOW
        # everything else on main stays blocked
        assert run_hook(HOOK, main_wt.payload("Write", file_path=_in_main(main_wt, "src/a.js"))).returncode == BLOCK
        assert run_hook(HOOK, main_wt.payload("Write", file_path=_in_main(main_wt, ".ddaro/gates/x.json"))).returncode == BLOCK


def test_run_folder_write_blocked_when_gate_off(main_wt):
    main_wt.write_config(main_protection="strict", merge_gate="off")
    assert run_hook(HOOK, main_wt.payload("Write", file_path=_runs_file(main_wt))).returncode == BLOCK
    main_wt.write_config(main_protection="strict")          # key absent == off
    assert run_hook(HOOK, main_wt.payload("Write", file_path=_runs_file(main_wt))).returncode == BLOCK
