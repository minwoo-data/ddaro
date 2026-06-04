"""Integration tests for check-evidence.py (opt-in evidence-token gate)."""

from __future__ import annotations

import time

from conftest import run_hook

HOOK = "check-evidence.py"
ALLOW = 0
BLOCK = 2


def _edit(main_wt):
    return main_wt.payload("Edit", file_path=(main_wt.root / "app.py").as_posix())


def _token(main_wt):
    return main_wt.root / ".ddaro" / "evidence-token"


def test_off_allows(main_wt):
    main_wt.write_config(evidence_check="off")
    assert run_hook(HOOK, _edit(main_wt)).returncode == ALLOW


def test_warn_allows_with_reminder(main_wt):
    main_wt.write_config(evidence_check="warn")
    r = run_hook(HOOK, _edit(main_wt))
    assert r.returncode == ALLOW
    assert "evidence_check" in r.stderr


def test_strict_without_token_blocks(main_wt):
    main_wt.write_config(evidence_check="strict")
    r = run_hook(HOOK, _edit(main_wt))
    assert r.returncode == BLOCK
    assert "evidence-token" in r.stderr


def test_strict_with_fresh_token_allows(main_wt):
    main_wt.write_config(evidence_check="strict")
    _token(main_wt).write_text("", encoding="utf-8")  # mtime = now
    assert run_hook(HOOK, _edit(main_wt)).returncode == ALLOW


def test_strict_with_stale_token_blocks(main_wt):
    main_wt.write_config(evidence_check="strict", evidence_token_ttl_seconds=60)
    tok = _token(main_wt)
    tok.write_text("", encoding="utf-8")
    old = time.time() - 600  # well past the 60s ttl
    import os
    os.utime(tok, (old, old))
    assert run_hook(HOOK, _edit(main_wt)).returncode == BLOCK


def test_strict_bypass_env_allows(main_wt):
    main_wt.write_config(evidence_check="strict")
    assert run_hook(HOOK, _edit(main_wt), env={"ALLOW_NO_EVIDENCE": "1"}).returncode == ALLOW


def test_non_edit_tool_ignored(main_wt):
    main_wt.write_config(evidence_check="strict")
    # Bash is not in the evidence hook's scope (Edit/Write only)
    p = main_wt.payload("Bash", command="git status")
    assert run_hook(HOOK, p).returncode == ALLOW
