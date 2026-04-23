#!/usr/bin/env python3
"""ddaro SessionStart hook: print a one-shot notice when a Claude Code
session starts inside the main worktree with main_protection != off.
Silent in off mode and silent outside main.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _shared import (  # noqa: E402
    cwd_from_payload,
    find_ddaro_config,
    is_inside,
    main_protection_level,
    read_payload,
)


def main() -> int:
    payload = read_payload()
    if payload is None:
        return 0

    cwd = cwd_from_payload(payload)
    cfg = find_ddaro_config(cwd)
    if not cfg:
        return 0

    level = main_protection_level(cfg)
    if level == "off":
        return 0

    main_str = cfg.get("main_worktree") or ""
    if not main_str:
        return 0
    main_path = Path(main_str)
    if not main_path.exists():
        return 0

    if cwd.resolve() != main_path.resolve():
        return 0

    notice = _build_notice(main_path, level)
    # SessionStart hooks write context via stdout.
    sys.stdout.write(notice)
    return 0


def _build_notice(main_path: Path, level: str) -> str:
    lines = [
        "",
        "ddaro notice — you are in the main worktree:",
        f"  {main_path}",
        "",
    ]

    worktrees = _list_worktrees(main_path)
    if worktrees:
        lines.append("Worktrees known to ddaro:")
        for wt in worktrees:
            lines.append(f"  • {wt}")
        lines.append("")

    lines.append("For isolated work:")
    lines.append("  /ddaro:resume      — pick an existing ddaro worktree")
    lines.append("  /ddaro:start       — create a new one")
    lines.append("  /ddaro:adopt <p>   — bring an existing non-ddaro worktree under ddaro")
    lines.append("")

    if level == "strict":
        lines.append("main_protection=strict — direct git commit / Edit on main is blocked.")
        lines.append("Bypass: ALLOW_MAIN_DIRECT=1 <command>")
    else:  # warn
        lines.append("main_protection=warn — direct actions are allowed but logged.")
    lines.append("")
    return "\n".join(lines)


def _list_worktrees(main_path: Path) -> list[str]:
    """Best-effort `git worktree list --porcelain` walk. Returns one-line
    summaries. Silent on any failure."""
    try:
        out = subprocess.run(
            ["git", "-C", str(main_path), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return []
    if out.returncode != 0 or not out.stdout:
        return []

    items: list[str] = []
    current: dict[str, str] = {}
    for line in out.stdout.splitlines():
        if not line.strip():
            if current:
                items.append(_summarize(current, main_path))
                current = {}
            continue
        if " " in line:
            key, _, val = line.partition(" ")
            current[key] = val
        else:
            current[line] = ""
    if current:
        items.append(_summarize(current, main_path))

    # Drop the main entry from the list (user is already there).
    try:
        main_resolved = main_path.resolve()
        items = [it for it in items if not it.startswith(str(main_resolved))]
    except Exception:
        pass
    return items[:20]


def _summarize(entry: dict, main_path: Path) -> str:
    path = entry.get("worktree", "")
    branch = entry.get("branch", "").replace("refs/heads/", "")
    tier = _classify(Path(path), main_path)
    branch_str = f"[{branch}]" if branch else "(detached)"
    return f"{path}  {branch_str}  {tier}"


def _classify(path: Path, main_path: Path) -> str:
    try:
        owned = (path / ".ddaro" / "OWNED").is_file()
    except Exception:
        owned = False
    if not owned:
        return "(unmanaged — /ddaro:adopt candidate)"
    try:
        lock_raw = (path / ".ddaro" / "LOCK").read_text(encoding="utf-8")
        lock = json.loads(lock_raw)
        if lock.get("adopted"):
            return "(adopted)"
    except Exception:
        pass
    return "(owned)"


if __name__ == "__main__":
    sys.exit(main())
