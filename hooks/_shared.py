"""Shared helpers for ddaro main_protection hooks.

Philosophy: fail open on any exception. Blocking a user because our hook
misread a file is worse than missing an unwanted commit. strict mode is
opt-in, so users who want the guarantee accept the cost of occasional
misses when Python / config / environment goes sideways.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional


def read_payload() -> Optional[dict]:
    """Read a JSON payload from stdin. Return None on any error."""
    try:
        raw = sys.stdin.read()
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


def find_ddaro_config(cwd: Path) -> Optional[dict]:
    """Walk up from cwd looking for `.ddaro/config.json`. Return parsed
    dict on success, None otherwise. Never raises."""
    try:
        p = cwd.resolve()
    except Exception:
        return None

    for candidate in [p, *p.parents]:
        cfg_path = candidate / ".ddaro" / "config.json"
        try:
            if cfg_path.is_file():
                return json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return None


def cwd_from_payload(payload: dict) -> Path:
    """Best-effort cwd extraction. Falls back to os.getcwd()."""
    cwd_str = payload.get("cwd") or os.getcwd()
    try:
        return Path(cwd_str).resolve()
    except Exception:
        return Path(os.getcwd()).resolve()


def is_inside(child: Path, parent: Path) -> bool:
    """True if `child` is `parent` itself or any descendant. False on error."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def main_protection_level(cfg: dict) -> str:
    """Normalize the main_protection config value to one of off|warn|strict."""
    v = str(cfg.get("main_protection") or "off").strip().lower()
    if v in ("off", "warn", "strict"):
        return v
    return "off"


def bypass_active() -> bool:
    """True if the user has set ALLOW_MAIN_DIRECT=1 (or any truthy value)."""
    v = os.environ.get("ALLOW_MAIN_DIRECT", "")
    return v.strip() not in ("", "0", "false", "False")
