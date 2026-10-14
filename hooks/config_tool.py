#!/usr/bin/env python3
"""ddaro config CLI (0.8.0): base-branch detection + schema migration.

The merge target used to be hardcoded as `main` throughout the ddaro skill.
`config.base_branch` replaces that literal; this script is the ONLY place the
detection logic and the schema-3 migration live, so the slash commands shell
out to it instead of re-implementing the git probing / JSON editing in prose.

Usage (called by the slash commands, never by hooks):

    python config_tool.py detect <main_worktree>            # prints branch name, exit 0
    python config_tool.py verify <main_worktree> <name>     # exit 0 if refs/heads/<name> OR refs/remotes/origin/<name> exists, else 1
    python config_tool.py ensure-schema <main_worktree>     # idempotent; prints 1 line only when it changed something; no config -> exit 0, creates nothing
    python config_tool.py set <main_worktree> <key> <value> # write one key (base_branch warns on verify failure); no config -> exit 1

Writes are atomic (temp file + os.replace) and preserve unknown keys.

Detection order (`detect_base_branch`):
  1. origin/HEAD  (`git symbolic-ref --short refs/remotes/origin/HEAD`)
  2. local `main` exists
  3. local `master` exists
  4. fallback `main` (identical to the pre-0.8.0 behaviour)

`ensure-schema` (idempotent) fills `base_branch` (detected) and `auto_snapshot`
("on") when absent and bumps `schema_version` to 3. It never overwrites an
existing `base_branch`; if that value no longer resolves it only warns on
stderr. Every subcommand that reads config runs this once, which is the
whole 0.7 -> 0.8 upgrade path.

Hooks never call this; they read `cfg.get("base_branch") or "main"` via
`_shared.base_branch(cfg)` so the blocking (PreToolUse) path stays
subprocess-free.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

FALLBACK = "main"
SCHEMA_VERSION = 3
_CANDIDATES = ("main", "master")
_KEYS_WITH_DEFAULTS = {"auto_snapshot": "on"}


def _git(args: list, cwd: Path, timeout: int = 5) -> str:
    """Run git in cwd; return stripped stdout, or "" on any failure.
    Bytes + explicit UTF-8 decode (text=True would use the Windows ANSI code
    page and can raise inside subprocess's reader thread)."""
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""
    if r.returncode != 0:
        return ""
    return r.stdout.decode("utf-8", errors="replace").strip()


def local_ref_exists(main_path: Path, name: str) -> bool:
    """True if `name` resolves to a local branch (refs/heads/<name>)."""
    if not name:
        return False
    return bool(_git(["rev-parse", "--verify", "--quiet", f"refs/heads/{name}"], main_path))


def ref_exists(main_path: Path, name: str) -> bool:
    """True if `name` exists as a local branch OR as `origin/<name>`.

    A base branch that is only fetched (never checked out locally) is still a
    valid merge target: /ddaro:merge works against `origin/<base>`, so verify
    must not nag about it."""
    if not name:
        return False
    if local_ref_exists(main_path, name):
        return True
    return bool(
        _git(["rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{name}"], main_path)
    )


def detect_base_branch(main_path: Path) -> str:
    """Resolve the repo's base branch. Never raises; falls back to `main`."""
    try:
        head = _git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], main_path)
        if head.startswith("origin/") and len(head) > len("origin/"):
            return head[len("origin/"):]
        for cand in _CANDIDATES:
            if local_ref_exists(main_path, cand):
                return cand
    except Exception:
        pass
    return FALLBACK


# --- config file I/O ------------------------------------------------------

def _config_path(main_path: Path) -> Path:
    return main_path / ".ddaro" / "config.json"


def _load(main_path: Path) -> dict:
    p = _config_path(main_path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return json.loads(p.read_text(encoding="utf-8"))


def _save(main_path: Path, cfg: dict) -> None:
    """Atomic write: temp file in the same directory + os.replace, so two
    sessions upgrading at once cannot leave a half-written config.json
    (a broken config silently disables EVERY fail-open hook). Unknown keys
    are preserved because `cfg` is the full parsed dict."""
    p = _config_path(main_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=".config.", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def ensure_schema(main_path: Path) -> list:
    """Bring config.json up to SCHEMA_VERSION. Returns a list of
    "key=value" strings for what changed (empty when already current).
    Raises FileNotFoundError when there is no config.json - ensure-schema
    never CREATES a config (that is the first-run wizard's job)."""
    cfg = _load(main_path)
    changed = []

    if not cfg.get("base_branch"):
        cfg["base_branch"] = detect_base_branch(main_path)
        changed.append(f"base_branch={cfg['base_branch']}")
    elif not ref_exists(main_path, str(cfg["base_branch"])):
        print(
            f"[ddaro] base_branch '{cfg['base_branch']}' not found in {main_path}; "
            f"keeping. Fix with /ddaro:config base_branch <name>",
            file=sys.stderr,
        )

    for key, default in _KEYS_WITH_DEFAULTS.items():
        if key not in cfg:
            cfg[key] = default
            changed.append(f"{key}={default}")

    try:
        current = int(cfg.get("schema_version") or 0)
    except (TypeError, ValueError):
        current = 0
    if current < SCHEMA_VERSION:
        cfg["schema_version"] = SCHEMA_VERSION
        changed.append(f"schema_version={SCHEMA_VERSION}")

    if changed:
        _save(main_path, cfg)
    return changed


def set_key(main_path: Path, key: str, value: str) -> None:
    cfg = _load(main_path)
    if key == "base_branch" and not ref_exists(main_path, value):
        print(
            f"[ddaro] warning: branch '{value}' not found in {main_path}; writing anyway",
            file=sys.stderr,
        )
    cfg[key] = value
    _save(main_path, cfg)


# --- CLI ------------------------------------------------------------------

_USAGE = (
    "usage: config_tool.py detect <main> | verify <main> <name> | "
    "ensure-schema <main> | set <main> <key> <value>"
)


def main(argv: list) -> int:
    for stream in (sys.stdout, sys.stderr):  # Claude Code reads output as UTF-8
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        if len(argv) >= 2 and argv[0] == "detect":
            print(detect_base_branch(Path(argv[1])))
            return 0
        if len(argv) >= 3 and argv[0] == "verify":
            return 0 if ref_exists(Path(argv[1]), argv[2]) else 1
        if len(argv) >= 2 and argv[0] == "ensure-schema":
            try:
                changed = ensure_schema(Path(argv[1]))
            except FileNotFoundError as e:
                # Not a ddaro project (yet): nothing to migrate, never create.
                print(f"[ddaro] ensure-schema: no config at {e}; nothing to do", file=sys.stderr)
                return 0
            if changed:
                print(f"[ddaro] config upgraded to schema {SCHEMA_VERSION} ({', '.join(changed)})")
            return 0
        if len(argv) >= 4 and argv[0] == "set":
            set_key(Path(argv[1]), argv[2], argv[3])
            return 0
    except FileNotFoundError as e:
        print(f"[ddaro] config not found: {e}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as e:
        print(f"[ddaro] config_tool failed: {e}", file=sys.stderr)
        return 1
    print(_USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
