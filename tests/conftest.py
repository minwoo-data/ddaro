"""Shared pytest fixtures + helpers for the ddaro hook test suite.

Hooks are stdlib Python scripts that read a PreToolUse / SessionStart JSON
payload on stdin and signal via exit code (0 = allow, 2 = block). We invoke
them as real subprocesses through ``sys.executable`` (so the suite runs on
whatever interpreter ran pytest, sidestepping the ``python`` vs ``python3``
PATH question) and assert on the exit code + stderr.

Paths embedded in payloads use POSIX separators (``Path.as_posix()``) so the
hooks' ``shlex.split`` does not eat Windows backslashes and JSON stays clean.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"

# Bypass env vars are cleared from the child env by default so a developer
# who has one exported locally cannot turn the whole suite green by accident.
_BYPASS_VARS = (
    "ALLOW_MAIN_DIRECT",
    "ALLOW_NO_EVIDENCE",
    "ALLOW_NON_DDARO_BRANCH",
    "ALLOW_WORKTREE_BRANCH_MISMATCH",
)


def run_hook(script: str, payload: dict, env: dict | None = None):
    """Run hooks/<script> with `payload` as JSON on stdin.

    Returns the CompletedProcess (assert on .returncode: 0 allow / 2 block).
    """
    child_env = {k: v for k, v in os.environ.items() if k not in _BYPASS_VARS}
    if env:
        child_env.update(env)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=child_env,
    )


class MainWorktree:
    """A tmp directory standing in for a ddaro main worktree."""

    def __init__(self, root: Path):
        self.root = root
        (root / ".ddaro").mkdir(parents=True, exist_ok=True)

    def write_config(self, **overrides) -> dict:
        cfg = {"schema_version": 2, "main_worktree": self.root.as_posix()}
        cfg.update(overrides)
        (self.root / ".ddaro" / "config.json").write_text(
            json.dumps(cfg), encoding="utf-8"
        )
        return cfg

    def payload(
        self,
        tool_name: str,
        *,
        command: str | None = None,
        file_path: str | None = None,
        notebook_path: str | None = None,
        cwd: Path | str | None = None,
    ) -> dict:
        tool_input: dict = {}
        if command is not None:
            tool_input["command"] = command
        if file_path is not None:
            tool_input["file_path"] = file_path
        if notebook_path is not None:
            tool_input["notebook_path"] = notebook_path
        cwd_val = cwd if cwd is not None else self.root
        cwd_str = cwd_val.as_posix() if isinstance(cwd_val, Path) else str(cwd_val)
        return {"tool_name": tool_name, "cwd": cwd_str, "tool_input": tool_input}


@pytest.fixture
def main_wt(tmp_path) -> MainWorktree:
    """A tmp main worktree with a `.ddaro/` dir and a config writer."""
    return MainWorktree(tmp_path)
