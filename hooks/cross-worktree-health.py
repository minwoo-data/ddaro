#!/usr/bin/env python3
"""ddaro SessionStart hook: scan all ddaro-managed worktrees and report drift.

Reads `.ddaro/config.json` to find the main worktree + protected worktrees,
then enumerates `git worktree list` to cover any ddaro-owned siblings.
For each worktree, checks:
  - tracked files missing from disk (`git ls-files -d`)
  - branch behind cached origin (`rev-list HEAD..origin/<branch>`)
  - uncommitted changes (`git status --porcelain`)
  - stale (no commit in `stale_days`)

Silent on clean state (zero token cost). One short line per problem
worktree otherwise.

Triggered by SessionStart matcher. Installation managed by
`/ddaro:config cross_worktree_check on`. Fails open on any error.

Created by: Minwoo Park
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _shared import find_ddaro_config, read_payload  # noqa: E402


def _enabled(cfg: dict) -> bool:
    v = str(cfg.get("cross_worktree_check") or "off").strip().lower()
    return v in ("on", "true", "1", "yes")


def _git(args: list[str], cwd: Path) -> str:
    """Run git in cwd, return stdout (trimmed). Empty string on any error."""
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0:
            return ""
        return r.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _enumerate_worktrees(cfg: dict, main: Path) -> list[Path]:
    """Combine config.protected_worktrees + git worktree list. Dedup."""
    seen: dict[str, Path] = {}
    for raw in cfg.get("protected_worktrees") or []:
        try:
            p = Path(raw).resolve()
            if p.exists():
                seen[str(p)] = p
        except Exception:
            continue
    out = _git(["worktree", "list", "--porcelain"], main)
    for line in out.splitlines():
        if line.startswith("worktree "):
            try:
                p = Path(line[len("worktree "):]).resolve()
                if p.exists():
                    seen[str(p)] = p
            except Exception:
                continue
    return list(seen.values())


def _check_one(wt: Path, stale_days: int) -> list[str]:
    """Return zero or more issue strings for this worktree (advisory only)."""
    if not (wt / ".git").exists() and not (wt / ".git").is_file():
        return []

    issues: list[str] = []
    label = wt.name

    # Tracked-deleted
    missing = _git(["ls-files", "-d"], wt)
    if missing:
        first = missing.split("\n", 1)[0]
        more = missing.count("\n")
        suffix = f" (+{more} more)" if more > 0 else ""
        issues.append(f"tracked-deleted: {first}{suffix}")

    # Behind origin (cached)
    branch = _git(["symbolic-ref", "--short", "HEAD"], wt)
    if branch:
        if _git(["rev-parse", f"origin/{branch}"], wt):
            behind = _git(["rev-list", "--count", f"HEAD..origin/{branch}"], wt)
            if behind and behind != "0":
                issues.append(f"{behind} behind origin/{branch}")

    # Uncommitted
    porcelain = _git(["status", "--porcelain"], wt)
    if porcelain:
        n = len(porcelain.splitlines())
        issues.append(f"{n} uncommit")

    # Stale (only when stale_days > 0)
    if stale_days > 0:
        last_iso = _git(["log", "-1", "--format=%ct"], wt)
        if last_iso:
            try:
                last_ts = int(last_iso)
                age_days = int((time.time() - last_ts) / 86400)
                if age_days >= stale_days:
                    issues.append(f"stale {age_days}d")
            except (ValueError, OSError):
                pass

    return [f"[ddaro] {label}: {i}" for i in issues]


def main() -> int:
    payload = read_payload()  # SessionStart payload may be empty {} -- still fine
    if payload is None:
        payload = {}

    cwd = Path(os.getcwd()).resolve()
    cfg = find_ddaro_config(cwd)
    if not cfg:
        return 0

    if not _enabled(cfg):
        return 0

    main_str = cfg.get("main_worktree") or ""
    if not main_str:
        return 0
    main_path = Path(main_str)
    if not main_path.exists():
        return 0

    stale_days = int(cfg.get("stale_days") or 0)
    worktrees = _enumerate_worktrees(cfg, main_path)

    lines: list[str] = []
    for wt in worktrees:
        try:
            lines.extend(_check_one(wt, stale_days))
        except Exception:
            continue

    if lines:
        for ln in lines:
            print(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
