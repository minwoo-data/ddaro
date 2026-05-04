#!/usr/bin/env python3
"""ddaro PreToolUse hook: block git branch creation that doesn't follow the
ddaro naming convention when branch_naming=strict. Fails open on any error.

Triggers on `git checkout -b <name>`, `git switch -c <name>`,
`git branch <name>`, and `git worktree add <path> -b <name>`. Validates
<name> against the project's `.ddaro/config.json` `name_pool` plus a
fixed allowlist for system / CI branches.

Allowed patterns:
  - d-<city>                                     (e.g. d-busan)
  - d-<city>/<topic>                             (e.g. d-busan/refactor)
  - feat|fix|chore|docs|refactor|test|style|build|ci|perf/<topic>-<city>
                                                 (e.g. chore/cleanup-busan)
  - backup/d-<city>-<...>                        (e.g. backup/d-busan-pre-merge)
  - main / master / develop / release/* / hotfix/* / ddaro/* / dependabot/*

Bypass: prefix the bash command with ALLOW_NON_DDARO_BRANCH=1.

Installation is managed by `/ddaro:config branch_naming strict`. Don't
invoke this script directly -- it reads a PreToolUse JSON payload on stdin.

Created by: Minwoo Park
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _shared import (  # noqa: E402
    cwd_from_payload,
    find_ddaro_config,
    read_payload,
)


# Branch-creating git invocations. We extract the proposed name in main().
_BRANCH_CREATE_PATTERNS = [
    re.compile(r"git\s+checkout\s+-b\s+(\S+)"),
    re.compile(r"git\s+switch\s+-c\s+(\S+)"),
    re.compile(r"git\s+branch\s+(?!--?)([^-\s][^\s]*)"),
    re.compile(r"git\s+worktree\s+add\s+\S+\s+-b\s+(\S+)"),
]

_SYSTEM_BRANCHES = {"main", "master", "develop"}
_SYSTEM_PREFIXES = ("release/", "hotfix/", "ddaro/", "dependabot/")
_CONVENTIONAL_PREFIXES = (
    "feat", "fix", "chore", "docs", "refactor", "test", "style",
    "build", "ci", "perf",
)


def _branch_naming_level(cfg: dict) -> str:
    v = str(cfg.get("branch_naming") or "off").strip().lower()
    if v in ("off", "warn", "strict"):
        return v
    return "off"


def _bypass_active() -> bool:
    v = os.environ.get("ALLOW_NON_DDARO_BRANCH", "")
    return v.strip() not in ("", "0", "false", "False")


def _extract_new_branch(cmd: str) -> str | None:
    for pat in _BRANCH_CREATE_PATTERNS:
        m = pat.search(cmd)
        if m:
            return m.group(1).strip()
    return None


def _city_pool(cfg: dict) -> set[str]:
    active = cfg.get("name_pool", "korea_city")
    pools = cfg.get("name_pools") or {}
    items = pools.get(active) or []
    return set(items)


def _is_allowed(name: str, cities: set[str]) -> tuple[bool, str]:
    """Return (allowed, reason)."""
    if name in _SYSTEM_BRANCHES:
        return True, "system branch"
    if name.startswith(_SYSTEM_PREFIXES):
        return True, "system/auto prefix"

    m = re.match(r"^d-([a-z0-9-]+?)(?:/.+)?$", name)
    if m and m.group(1) in cities:
        return True, "d-<city> pattern"

    m = re.match(r"^backup/d-([a-z0-9-]+?)[-/].*$", name)
    if m and m.group(1) in cities:
        return True, "backup/d-<city> pattern"

    pat = r"^(" + "|".join(_CONVENTIONAL_PREFIXES) + r")/.+-([a-z0-9]+)$"
    m = re.match(pat, name)
    if m and m.group(2) in cities:
        return True, "conventional/<topic>-<city> pattern"

    return False, "missing city marker (.ddaro/config.json name_pool)"


def _refusal(name: str, reason: str, cmd: str, pool_name: str) -> str:
    return (
        "\n"
        f"Blocked by ddaro branch_naming=strict.\n"
        f"  Branch '{name}' doesn't follow the convention.\n"
        f"  Reason: {reason}\n"
        "\n"
        f"  Allowed patterns (cities from name_pool='{pool_name}'):\n"
        "    - d-<city>                       e.g. d-busan\n"
        "    - d-<city>/<topic>               e.g. d-busan/refactor\n"
        "    - feat|fix|chore|docs|refactor|test|style|build|ci|perf/<topic>-<city>\n"
        "                                     e.g. chore/cleanup-busan\n"
        "    - backup/d-<city>-<...>          e.g. backup/d-busan-pre-merge\n"
        "\n"
        "  Options:\n"
        "    1) /ddaro:start [name]           create a new worktree+branch from the pool\n"
        "    2) Rename to include a city marker, then re-run.\n"
        f"    3) One-shot bypass (audit-visible):\n"
        f"         ALLOW_NON_DDARO_BRANCH=1 {cmd.strip()}\n"
        "    4) Disable strict enforcement:\n"
        "         /ddaro:config branch_naming off\n"
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
        return 0  # not a ddaro project

    if _branch_naming_level(cfg) != "strict":
        return 0

    cmd = str((payload.get("tool_input") or {}).get("command") or "")
    if not cmd:
        return 0

    if _bypass_active():
        return 0

    name = _extract_new_branch(cmd)
    if name is None:
        return 0

    cities = _city_pool(cfg)
    if not cities:
        return 0  # no pool configured -> nothing to enforce

    ok, reason = _is_allowed(name, cities)
    if ok:
        return 0

    pool_name = str(cfg.get("name_pool") or "korea_city")
    print(_refusal(name, reason, cmd, pool_name), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
