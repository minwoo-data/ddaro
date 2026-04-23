#!/usr/bin/env python3
"""ddaro PreToolUse hook: block Edit/Write/NotebookEdit on files inside
the main worktree when main_protection=strict. Files matching any glob
in `planning_patterns` (planning/state/docs) pass through.

Fails open on any error. strict mode is opt-in.
"""

from __future__ import annotations

import fnmatch
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


DEFAULT_PLANNING_PATTERNS = [
    ".planning/**",
    ".gsd/**",
    "STATE.md",
    "ROADMAP.md",
    "CHANGELOG.md",
    ".claude/**",
]


def main() -> int:
    payload = read_payload()
    if payload is None:
        return 0

    tool = payload.get("tool_name") or ""
    if tool not in ("Edit", "Write", "NotebookEdit"):
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

    target_str = (payload.get("tool_input") or {}).get("file_path") or ""
    if not target_str:
        return 0
    target = Path(target_str)

    if not is_inside(target, main_path):
        return 0

    # Files on the planning whitelist are always allowed.
    patterns = cfg.get("planning_patterns") or DEFAULT_PLANNING_PATTERNS
    try:
        rel = target.resolve().relative_to(main_path.resolve())
    except Exception:
        return 0
    rel_posix = rel.as_posix()
    for pat in patterns:
        if _glob_match(rel_posix, pat):
            return 0

    if bypass_active():
        return 0

    print(_refusal(main_path, target), file=sys.stderr)
    return 2


def _glob_match(path: str, pattern: str) -> bool:
    """fnmatch.fnmatch handles `*` but not `**`. Rewrite `**` → match-any."""
    # Cheap `**` handling: replace `**/` with empty or any prefix path.
    # fnmatch.fnmatchcase on posix paths is good enough here.
    if "**" in pattern:
        # Transform a/**/b.py to a/.../b.py (fnmatch doesn't grok **).
        # Simple approach: if prefix matches up to **, allow any suffix.
        parts = pattern.split("**", 1)
        prefix = parts[0].rstrip("/")
        suffix = parts[1].lstrip("/") if len(parts) > 1 else ""
        if prefix and not path.startswith(prefix):
            return False
        if suffix:
            return fnmatch.fnmatch(path, f"*{suffix}") or path.endswith(suffix)
        return True
    return fnmatch.fnmatch(path, pattern)


def _refusal(main_path: Path, target: Path) -> str:
    return (
        "\n"
        "Blocked by ddaro main_protection=strict.\n"
        f"  cwd:    {main_path} (main worktree)\n"
        f"  target: {target}\n"
        "  Direct edits on main (outside planning_patterns) are refused.\n"
        "\n"
        "  Options:\n"
        "    1) Edit in a ddaro worktree:\n"
        "         cd <your-ddaro-worktree>\n"
        "         (edit + /ddaro:commit + /ddaro:merge)\n"
        "    2) One-shot bypass:\n"
        "         ALLOW_MAIN_DIRECT=1 <your command>\n"
        "    3) Add this path pattern to planning_patterns in .ddaro/config.json.\n"
        "    4) Disable strict protection:\n"
        "         /ddaro:config main_protection off\n"
    )


if __name__ == "__main__":
    sys.exit(main())
