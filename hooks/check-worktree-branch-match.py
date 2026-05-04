#!/usr/bin/env python3
"""ddaro PreToolUse hook: block `git commit` when the worktree's city marker
doesn't match the branch's city marker. Fails open on any error.

Catches the foot-gun where a user is in worktree
`/...-d-busan` but accidentally has branch `d-namyangju` checked out (e.g.
they ran `git switch` to jump branches and forgot which physical worktree
they were in). Without this guard, the commit lands on the wrong branch
and trace-back is hard.

Logic:
  - extract worktree city from cwd basename pattern: `*-d-<city>`
  - extract branch city from current branch via the same patterns
    `check-branch-naming.py` recognizes
  - if both have markers AND they differ -> block
  - if either has no marker -> skip (let check-branch-naming handle it)

Bypass: prefix the bash command with ALLOW_WORKTREE_BRANCH_MISMATCH=1.

Installation managed by `/ddaro:config branch_worktree_match strict`.

Created by: Minwoo Park
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _shared import (  # noqa: E402
    cwd_from_payload,
    find_ddaro_config,
    read_payload,
)


_GIT_COMMIT_RE = re.compile(r"(?:^|[;&|`\s])git\s+commit\b")


def _level(cfg: dict) -> str:
    v = str(cfg.get("branch_worktree_match") or "off").strip().lower()
    if v in ("off", "warn", "strict"):
        return v
    return "off"


# Bypass scope: must be at the START of the same command segment as the
# `git commit`. A bypass attached to an unrelated earlier segment
# (e.g. `ALLOW_...=1 git status && git commit -m bad`) does NOT waive the
# protected commit -- only the segment that contains the commit counts.
_BYPASS_SEGMENT_PREFIX_RE = re.compile(
    r"^\s*ALLOW_WORKTREE_BRANCH_MISMATCH=(?!0\b|false\b|False\b|\"\"|''|\s)\S*\s+"
)
_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||;|&|\|")


def _segments(cmd: str) -> list[str]:
    return [s for s in _SEGMENT_SPLIT_RE.split(cmd) if s.strip()]


def _bypass_for_commit(cmd: str) -> bool:
    """Bypass applies only if the SEGMENT containing `git commit` also starts
    with ALLOW_WORKTREE_BRANCH_MISMATCH=<truthy>."""
    env_v = os.environ.get("ALLOW_WORKTREE_BRANCH_MISMATCH", "").strip()
    if env_v not in ("", "0", "false", "False"):
        return True
    for seg in _segments(cmd):
        if _GIT_COMMIT_RE.search(seg):
            return bool(_BYPASS_SEGMENT_PREFIX_RE.match(seg))
    return False


def _city_pool(cfg: dict) -> set[str]:
    active = cfg.get("name_pool", "korea_city")
    pools = cfg.get("name_pools") or {}
    items = pools.get(active) or []
    return set(items)


def _worktree_city(cwd: Path, cities: set[str]) -> str | None:
    """Match cwd basename like `<project>-d-<city>` and return <city> if in pool."""
    name = cwd.name
    m = re.match(r"^.+-d-([a-z0-9-]+)$", name)
    if not m:
        return None
    candidate = m.group(1)
    return candidate if candidate in cities else None


def _branch_city(branch: str, cities: set[str]) -> str | None:
    """Extract city from branch name using the same patterns as check-branch-naming.py."""
    if not branch:
        return None
    # d-<city> or d-<city>/<topic>
    m = re.match(r"^d-([a-z0-9-]+?)(?:/.+)?$", branch)
    if m and m.group(1) in cities:
        return m.group(1)
    # backup/d-<city>-...
    m = re.match(r"^backup/d-([a-z0-9-]+?)[-/].*$", branch)
    if m and m.group(1) in cities:
        return m.group(1)
    # conventional/<topic>-<city>
    prefixes = "feat|fix|chore|docs|refactor|test|style|build|ci|perf"
    m = re.match(rf"^({prefixes})/.+-([a-z0-9]+)$", branch)
    if m and m.group(2) in cities:
        return m.group(2)
    return None


def _current_branch(cwd: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=3,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return ""


def _refusal(cwd_city: str, branch: str, branch_city: str, cmd: str) -> str:
    return (
        "\n"
        f"Blocked by ddaro branch_worktree_match=strict.\n"
        f"  Worktree city marker: '{cwd_city}'\n"
        f"  Branch city marker:   '{branch_city}' (branch: {branch})\n"
        f"  These don't match — you might be committing on the wrong branch.\n"
        "\n"
        "  Options:\n"
        f"    1) Switch to the matching branch (anything with '{cwd_city}'):\n"
        f"         git checkout d-{cwd_city}    # or any city-matching branch\n"
        "    2) Move to the right worktree:\n"
        f"         cd $(/ddaro:list)            # find the worktree for '{branch_city}'\n"
        f"    3) One-shot bypass (audit-visible):\n"
        f"         ALLOW_WORKTREE_BRANCH_MISMATCH=1 {cmd.strip()}\n"
        "    4) Disable strict enforcement:\n"
        "         /ddaro:config branch_worktree_match off\n"
    )


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

    if _level(cfg) != "strict":
        return 0

    cmd = str((payload.get("tool_input") or {}).get("command") or "")
    if not cmd or not _GIT_COMMIT_RE.search(cmd):
        return 0

    if _bypass_for_commit(cmd):
        return 0

    cities = _city_pool(cfg)
    if not cities:
        return 0

    cwd_city = _worktree_city(cwd, cities)
    if cwd_city is None:
        return 0  # not a city-marked worktree (e.g. main itself)

    branch = _current_branch(cwd)
    branch_city = _branch_city(branch, cities)
    if branch_city is None:
        return 0  # branch isn't city-marked -- check-branch-naming.py owns this

    if cwd_city == branch_city:
        return 0

    print(_refusal(cwd_city, branch, branch_city, cmd), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
