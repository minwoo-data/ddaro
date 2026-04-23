#!/usr/bin/env python3
"""ddaro PreToolUse hook: block `git commit` in the main worktree when
main_protection=strict. Fails open on any error.

Installation is managed by `/ddaro:config main_protection strict`. Don't
invoke this script directly — it reads a PreToolUse JSON payload on stdin.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _shared import (  # noqa: E402
    bypass_active,
    cwd_from_payload,
    find_ddaro_config,
    is_inside,
    main_protection_level,
    read_payload,
)


# `git commit`, `git commit --amend`, `git commit --fixup=...`, etc.
# Intentionally does NOT match `git merge` (main's valid role is to receive merges).
GIT_COMMIT_RE = re.compile(r"(?:^|[;&|`\s])git\s+commit\b")


def main() -> int:
    payload = read_payload()
    if payload is None:
        return 0

    if (payload.get("tool_name") or "") != "Bash":
        return 0

    cwd = cwd_from_payload(payload)
    cfg = find_ddaro_config(cwd)
    if not cfg:
        return 0

    level = main_protection_level(cfg)
    if level != "strict":
        return 0

    main_str = cfg.get("main_worktree") or ""
    if not main_str:
        return 0
    main_path = Path(main_str)
    if not main_path.exists():
        return 0

    if not is_inside(cwd, main_path):
        return 0

    cmd = str((payload.get("tool_input") or {}).get("command") or "")
    if not GIT_COMMIT_RE.search(cmd):
        return 0

    if bypass_active():
        return 0

    print(_refusal(main_path, cmd), file=sys.stderr)
    return 2


def _refusal(main_path: Path, cmd: str) -> str:
    return (
        "\n"
        f"Blocked by ddaro main_protection=strict.\n"
        f"  cwd: {main_path} (main worktree — direct commits are refused)\n"
        "\n"
        "  Options:\n"
        "    1) Commit in a ddaro worktree and merge:\n"
        "         cd <your-ddaro-worktree>\n"
        "         /ddaro:commit \"<msg>\"\n"
        "         /ddaro:merge\n"
        "    2) One-shot bypass (audit-visible):\n"
        f"         ALLOW_MAIN_DIRECT=1 {cmd.strip()}\n"
        "    3) Disable strict protection:\n"
        "         /ddaro:config main_protection off\n"
    )


if __name__ == "__main__":
    sys.exit(main())
