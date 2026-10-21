#!/usr/bin/env python3
"""ddaro config CLI (0.8.0): base-branch detection + schema migration.
0.10.0 adds the merge-gate keys (schema 4), `init`, `is_weakening` and the gate marker file.

The merge target used to be hardcoded as `main` throughout the ddaro skill.
`config.base_branch` replaces that literal; this script is the ONLY place the
detection logic and the schema-3 migration live, so the slash commands shell
out to it instead of re-implementing the git probing / JSON editing in prose.

Usage (called by the slash commands, never by hooks):

    python config_tool.py detect <main_worktree>            # prints branch name, exit 0
    python config_tool.py verify <main_worktree> <name>     # exit 0 if refs/heads/<name> OR refs/remotes/origin/<name> exists, else 1
    python config_tool.py ensure-schema <main_worktree>     # idempotent; prints 1 line only when it changed something; no config -> exit 0, creates nothing
    python config_tool.py set <main_worktree> <key> <value> # write one key (base_branch warns on verify failure); no config -> exit 1
    python config_tool.py init <main_worktree> [key=value ...] # create config.json (schema 4 defaults); exit 1 when one exists
    python config_tool.py set <main_worktree> planning_patterns '["docs/**", ".planning/**"]'   # list keys take a JSON array

Writes are atomic (temp file + os.replace), taken under the short config lock
(`.ddaro/config.lock`), and preserve unknown keys.

Merge gate (0.10.0, schema 4): `merge_gate` off|warn|strict, `gate_block_severity`
CRIT|HIGH|MED, `gate_verify` auto|none. `set` accepts only those values for these
keys. Setting `merge_gate` to warn/strict leaves `<git-common-dir>/ddaro-gate`
(the marker the hook reads when `<main>` has no config any more); only `off`
removes it. `is_weakening(key, old, new)` is the L12 definition the merge-gate
hook imports: a weaker `merge_gate`, a higher `gate_block_severity`, `gate_verify`
auto -> none, any `base_branch` change, any `planning_patterns` change except a
pure removal. The hook, not this module, decides whether the gate is on.

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

Hooks read `cfg.get("base_branch") or "main"` via `_shared.base_branch(cfg)`;
the protective hooks never shell out. The merge-gate hook imports
`is_weakening` and `GATE_KEYS` from here (pure functions, no subprocess).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _shared import file_lock, gate_marker_path  # noqa: E402

FALLBACK = "main"
SCHEMA_VERSION = 4
_CANDIDATES = ("main", "master")
# Merge gate (schema 4): key -> allowed values, first one is the default.
GATE_KEYS = {
    "merge_gate": ("off", "warn", "strict"),
    "gate_block_severity": ("MED", "CRIT", "HIGH"),
    "gate_verify": ("auto", "none"),
}
_KEYS_WITH_DEFAULTS = {"auto_snapshot": "on"}
_KEYS_WITH_DEFAULTS.update({k: v[0] for k, v in GATE_KEYS.items()})
_GATE_STRENGTH = {"off": 0, "warn": 1, "strict": 2}
_SEVERITY_RANK = {"MED": 0, "HIGH": 1, "CRIT": 2}


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
    if not _config_path(main_path).is_file():
        raise FileNotFoundError(str(_config_path(main_path)))   # never create .ddaro/ for a non-project
    with file_lock(_lock_path(main_path)):
        return _ensure_schema_locked(main_path)


def _lock_path(main_path: Path) -> Path:
    return main_path / ".ddaro" / "config.lock"


def _ensure_schema_locked(main_path: Path) -> list:
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


LIST_KEYS = ("planning_patterns", "protected_worktrees", "external_patterns")


def decode_value(key: str, value: str):
    """`set` stores list-valued keys as lists: the value is a JSON array, or a
    single pattern. Everything else stays a string."""
    if key in LIST_KEYS:
        try:
            v = json.loads(value)
        except ValueError:
            return [value]
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise ValueError(f"{key} must be a JSON array of strings (got {value!r})")
        return v
    return value


def set_key(main_path: Path, key: str, value: str) -> None:
    if key in GATE_KEYS and value not in GATE_KEYS[key]:
        raise ValueError(f"{key} must be one of {', '.join(GATE_KEYS[key])} (got {value!r})")
    stored = decode_value(key, value)
    if not _config_path(main_path).is_file():
        raise FileNotFoundError(str(_config_path(main_path)))
    with file_lock(_lock_path(main_path)):
        cfg = _load(main_path)
        if key == "base_branch" and not ref_exists(main_path, value):
            print(
                f"[ddaro] warning: branch '{value}' not found in {main_path}; writing anyway",
                file=sys.stderr,
            )
        cfg[key] = stored
        _save(main_path, cfg)
        if key == "merge_gate":
            _update_marker(main_path, value)      # inside the lock: config and marker move together


def _update_marker(main_path: Path, mode: str) -> None:
    """`<git-common-dir>/ddaro-gate`: present while the gate is warn/strict so
    deleting `.ddaro/` cannot turn the gate off (L10). Only `off` removes it."""
    marker = gate_marker_path(main_path)
    if marker is None:
        return
    try:
        if mode == "off":
            if marker.exists():
                marker.unlink()
        else:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(f"merge_gate={mode}\n", encoding="utf-8")
    except OSError as e:
        print(f"[ddaro] warning: gate marker {marker} not updated: {e}", file=sys.stderr)


def init_config(main_path: Path, pairs: list) -> dict:
    """Create `<main>/.ddaro/config.json` when none exists (schema 4 defaults +
    the given key=value pairs), then run the schema fill. Refuses (FileExistsError)
    when a config is already there: `init` never overwrites (L11)."""
    with file_lock(_lock_path(main_path)):
        p = _config_path(main_path)
        if p.exists():
            raise FileExistsError(str(p))
        cfg = {"schema_version": SCHEMA_VERSION, "main_worktree": main_path.resolve().as_posix()}
        for pair in pairs:
            k, eq, v = pair.partition("=")
            if not eq or not k:
                raise ValueError(f"init expects key=value, got {pair!r}")
            if k in GATE_KEYS and v not in GATE_KEYS[k]:
                raise ValueError(f"{k} must be one of {', '.join(GATE_KEYS[k])} (got {v!r})")
            if k in LIST_KEYS:
                cfg[k] = decode_value(k, v)
            else:
                try:
                    cfg[k] = json.loads(v)
                except ValueError:
                    cfg[k] = v
        _save(main_path, cfg)
        _ensure_schema_locked(main_path)
        final = _load(main_path)
        if str(final.get("merge_gate", "off")).lower() != "off":
            _update_marker(main_path, str(final["merge_gate"]))
        return final


def is_weakening(key: str, old, new) -> bool:
    """L12: does changing `key` from `old` to `new` weaken the merge gate?
    Pure; the caller applies it only while `merge_gate` is not off. Unknown
    `merge_gate` values count as strict and unknown severities as MED."""
    if key == "merge_gate":
        o = _GATE_STRENGTH.get(_norm(old), 2)
        n = _GATE_STRENGTH.get(_norm(new), 2)
        return n < o
    if key == "gate_block_severity":
        o = _SEVERITY_RANK.get(str(old or "MED").strip().upper(), 0)
        n = _SEVERITY_RANK.get(str(new or "MED").strip().upper(), 0)
        return n > o
    if key == "gate_verify":
        return _norm(old) != "none" and _norm(new) == "none"
    if key == "base_branch":
        return (old or FALLBACK) != (new or FALLBACK)      # absent == `main`, as _shared.base_branch reads it
    if key == "planning_patterns":
        o = list(old or [])
        n = list(new or [])
        if o == n:
            return False
        # Only a pure removal (every new entry was already there) is harmless.
        return not (len(n) < len(o) and all(x in o for x in n))
    return False


def _norm(v) -> str:
    return str(v if v is not None else "off").strip().lower()


def weakening_changes(old_cfg: dict, new_cfg: dict) -> list:
    """Keys whose change from old_cfg to new_cfg is weakening (L12). Absent
    gate keys count as their defaults."""
    out = []
    for key in ("merge_gate", "gate_block_severity", "gate_verify", "base_branch", "planning_patterns"):
        default = GATE_KEYS.get(key, (None,))[0]
        o = (old_cfg or {}).get(key, default)
        n = (new_cfg or {}).get(key, default)
        if is_weakening(key, o, n):
            out.append(key)
    return out


# --- CLI ------------------------------------------------------------------

_USAGE = (
    "usage: config_tool.py detect <main> | verify <main> <name> | "
    "ensure-schema <main> | set <main> <key> <value> | init <main> [key=value ...]"
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
        if len(argv) >= 2 and argv[0] == "init":
            try:
                cfg = init_config(Path(argv[1]), argv[2:])
            except FileExistsError as e:
                print(f"[ddaro] init refused: config already exists at {e}; use set", file=sys.stderr)
                return 1
            print(f"[ddaro] config created (schema {cfg.get('schema_version')}, base_branch={cfg.get('base_branch')})")
            return 0
    except FileNotFoundError as e:
        print(f"[ddaro] config not found: {e}", file=sys.stderr)
        return 1
    except TimeoutError as e:
        print(f"[ddaro] config_tool refused: {e}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as e:
        print(f"[ddaro] config_tool failed: {e}", file=sys.stderr)
        return 1
    print(_USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
