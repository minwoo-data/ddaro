"""Shared helpers for ddaro main_protection hooks.

Philosophy: fail open on any exception. Blocking a user because our hook
misread a file is worse than missing an unwanted commit. strict mode is
opt-in, so users who want the guarantee accept the cost of occasional
misses when Python / config / environment goes sideways.
"""

from __future__ import annotations

import json
import os
import re
import shlex
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


# --- git commit detection -------------------------------------------------
#
# Shared by check-main-bash.py (main_protection) and
# check-worktree-branch-match.py. A naive `git\s+commit` regex misses
# `git -C <path> commit`, `git -c k=v commit`, `git --work-tree=<p> commit`
# etc. (global options sit between `git` and the subcommand) and a `commit\b`
# regex wrongly matches `git commit-graph`. This tokenizer skips global
# options - consuming their arguments - and matches the `commit` subcommand
# exactly, while also resolving the effective target worktree from
# -C / --work-tree so main_protection can reason about WHERE a commit lands,
# not just the cwd it was launched from. Best-effort; fails open (returns
# "nothing found"), never raises.

_SEG_SPLIT_RE = re.compile(r"&&|\|\||;|&|\||\n|`")

# Global options that consume the FOLLOWING token as their argument when not
# written in --opt=value form.
_GIT_OPTS_WITH_ARG = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--exec-path", "--super-prefix", "--config-env",
}
# Global options whose value sets the working directory the commit lands in.
_GIT_DIR_OPTS = {"-C", "--work-tree"}


def _split_segments(command: str) -> list:
    return [s for s in _SEG_SPLIT_RE.split(command) if s.strip()]


def _tokenize(segment: str) -> list:
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def _join_dir(cwd: Path, raw: str) -> Path:
    try:
        p = Path(raw)
        return p if p.is_absolute() else (cwd / p)
    except Exception:
        return cwd


def _scan_git_invocation(tokens: list, start: int, cwd: Path):
    """Given everything after a `git` token, skip global options (consuming
    their args) and return (target_dir, subcommand). target_dir reflects
    -C / --work-tree overrides; subcommand is the first positional or None."""
    target = cwd
    i = start
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if not tok.startswith("-"):
            return target, tok  # first positional token is the subcommand
        key, eq, inline = tok.partition("=")
        if key in _GIT_DIR_OPTS:
            if eq:
                target = _join_dir(cwd, inline)
            elif i + 1 < n:
                target = _join_dir(cwd, tokens[i + 1])
                i += 1
            i += 1
            continue
        if key in _GIT_OPTS_WITH_ARG and not eq:
            i += 2  # consume the option and its separate argument
            continue
        i += 1  # bare flag, or --opt=value (self-contained)
    return target, None


def command_git_commit_targets(command: str, cwd: Path) -> list:
    """Worktree dirs a `git commit` in `command` would land in.

    One Path per `git [global-opts] commit ...` invocation (the effective
    target dir after -C / --work-tree, defaulting to cwd). `git commit-graph`,
    `git log --grep=commit`, and `git merge` do NOT match. Never raises."""
    targets = []
    try:
        for seg in _split_segments(command):
            toks = _tokenize(seg)
            for i, tok in enumerate(toks):
                if tok == "git" or tok.endswith("/git"):
                    target, sub = _scan_git_invocation(toks, i + 1, cwd)
                    if sub == "commit":
                        targets.append(target)
    except Exception:
        return targets
    return targets


def command_has_git_commit(command: str) -> bool:
    """True if `command` contains a `git commit` (exact subcommand), robust to
    global options. Target-agnostic. Never raises."""
    try:
        return bool(command_git_commit_targets(command, Path(".")))
    except Exception:
        return False
