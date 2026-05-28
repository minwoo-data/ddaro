#!/usr/bin/env python3
"""ddaro PreToolUse hook: gentle reminder (or hard block) that an edit
should be backed by some evidence the file was read / understood first.
Triggers on `Edit` and `Write` tool calls. Fails open on any error.

The hook does NOT introspect conversation history (PreToolUse hooks
don't have that). What it CAN do:

  - off (default):  do nothing.
  - warn:           print a one-line reminder to stderr; allow the edit.
                    The reminder is informational only - no exit code 2.
  - strict:         require ALLOW_NO_EVIDENCE=1 (or =true / non-empty)
                    in the caller's environment, OR the presence of a
                    fresh `.ddaro/evidence-token` file (mtime within the
                    last `evidence_token_ttl_seconds` config, default
                    300). Otherwise exit 2 with an explanation.

Why "fresh token file" instead of trying to parse conversation history:

  PreToolUse hooks see the tool payload + cwd, not chat. The cleanest
  contract is for the calling session to write a sentinel file when it
  has established evidence (a grep pass, a git log read, a Read tool
  call against the file in question, etc.). The session can write it
  manually:

      touch .ddaro/evidence-token

  or via a project-side hook that does so on grep / Read invocations.
  The hook just checks "did SOMEONE recently confirm evidence?" without
  caring about the form of the evidence itself.

  In off mode the file is ignored. Most projects will run with off or
  warn; strict is for repos where every edit needs an audit trail
  (regulated industries, etc).

Bypass: prefix the command (or set the env globally) with
ALLOW_NO_EVIDENCE=1. The same convention as ALLOW_NON_DDARO_BRANCH /
ALLOW_MAIN_DIRECT in the sibling hooks.

Installation is managed by `/ddaro:config evidence_check <off|warn|strict>`.
Don't invoke this script directly -- it reads a PreToolUse JSON payload
on stdin.

Created by: Minwoo Park
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _shared import (  # noqa: E402
    cwd_from_payload,
    find_ddaro_config,
    read_payload,
)


def _evidence_level(cfg: dict) -> str:
    v = str(cfg.get("evidence_check") or "off").strip().lower()
    if v in ("off", "warn", "strict"):
        return v
    return "off"


def _token_ttl_seconds(cfg: dict) -> int:
    raw = cfg.get("evidence_token_ttl_seconds")
    try:
        n = int(raw)
        if 30 <= n <= 86400:  # 30s..1day sane band
            return n
    except (TypeError, ValueError):
        pass
    return 300  # 5 minutes default


def _bypass_active() -> bool:
    v = os.environ.get("ALLOW_NO_EVIDENCE", "")
    return v.strip() not in ("", "0", "false", "False")


def _token_is_fresh(worktree: Path, ttl: int) -> bool:
    """True if `.ddaro/evidence-token` exists and was modified within `ttl` seconds."""
    token = worktree / ".ddaro" / "evidence-token"
    try:
        mtime = token.stat().st_mtime
    except (FileNotFoundError, PermissionError, OSError):
        return False
    return (time.time() - mtime) <= ttl


def _tool_name(payload: dict) -> str:
    """Extract the tool name. PreToolUse payloads vary by harness version;
    try a few shapes."""
    return (
        payload.get("tool")
        or payload.get("tool_name")
        or payload.get("name")
        or ""
    )


def main() -> int:
    payload = read_payload()
    if payload is None:
        return 0  # fail open

    tool = _tool_name(payload)
    if tool not in ("Edit", "Write"):
        return 0

    cwd = cwd_from_payload(payload)
    cfg = find_ddaro_config(cwd) or {}
    level = _evidence_level(cfg)
    if level == "off":
        return 0

    if _bypass_active():
        return 0

    # Walk up to the worktree root that owns the .ddaro config so the
    # token file check uses the canonical location, not the nested cwd
    # the harness may have surfaced.
    worktree = cwd
    for candidate in [cwd, *cwd.parents]:
        if (candidate / ".ddaro").is_dir():
            worktree = candidate
            break

    ttl = _token_ttl_seconds(cfg)
    if _token_is_fresh(worktree, ttl):
        return 0

    msg = (
        f"[ddaro] evidence_check={level}: no fresh .ddaro/evidence-token "
        f"(ttl={ttl}s). Establish evidence before {tool}: read the file, "
        f"grep the relevant symbol, or scan recent git log. Then "
        f"`touch .ddaro/evidence-token` to record the evidence pass.\n"
        f"Bypass once: ALLOW_NO_EVIDENCE=1 <your-command>.\n"
        f"Disable entirely: /ddaro:config evidence_check off."
    )

    if level == "warn":
        print(msg, file=sys.stderr)
        return 0

    # strict
    print(msg, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
