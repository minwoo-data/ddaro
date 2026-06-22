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


def _load_config_at(dir_path: Path) -> Optional[dict]:
    """Parse `<dir>/.ddaro/config.json` if present. None on absence/error."""
    cfg_path = dir_path / ".ddaro" / "config.json"
    try:
        if cfg_path.is_file():
            return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _main_worktree_root(cwd: Path) -> Optional[Path]:
    """If `cwd` is a LINKED git worktree, return its main worktree root by
    following the `.git` file -> gitdir -> commondir pointers. Filesystem-only
    (no subprocess). Returns None when cwd is the main worktree (its `.git` is
    a directory, already covered by the parent walk), is not a git repo, or on
    any error.

    Why this exists: `.ddaro/config.json` is gitignored, so a sibling worktree
    created by `/ddaro:start` (or adopted) usually has NO config of its own and
    none up its parent chain -- only the MAIN worktree carries it. Without this
    resolution every ddaro hook no-ops in such worktrees and the user silently
    loses all protection (branch_naming, main_protection, ...). Resolving the
    main config keeps enforcement uniform across every worktree of the repo.
    A non-ddaro repo costs only a couple of extra file reads here (no subprocess,
    no behaviour change) and still resolves to None.
    """
    git_marker = cwd / ".git"
    try:
        # A linked worktree's `.git` is a FILE ("gitdir: <path>"); the main
        # worktree's `.git` is a directory -> nothing to resolve here.
        if not git_marker.is_file():
            return None
        content = git_marker.read_text(encoding="utf-8").strip()
        if not content.startswith("gitdir:"):
            return None
        gitdir = Path(content[len("gitdir:"):].strip())
        if not gitdir.is_absolute():
            gitdir = (cwd / gitdir).resolve()
        # `<gitdir>/commondir` (git-sanctioned) points at the shared `.git` dir.
        commondir_file = gitdir / "commondir"
        if commondir_file.is_file():
            rel = commondir_file.read_text(encoding="utf-8").strip()
            common = (gitdir / rel).resolve()  # <main>/.git
            return common.parent
        # Fallback for the standard layout:
        # <gitdir> == <main>/.git/worktrees/<name>.
        return gitdir.parent.parent.parent
    except Exception:
        return None


def find_ddaro_config(cwd: Path) -> Optional[dict]:
    """Locate the ddaro `.ddaro/config.json` for `cwd`. Walk up from cwd; if
    nothing is found up the tree, fall back to the MAIN worktree's config when
    cwd is a linked git worktree (its own `.ddaro/` is typically absent because
    `.ddaro/` is gitignored). Return parsed dict on success, None otherwise.
    Never raises."""
    try:
        p = cwd.resolve()
    except Exception:
        return None

    # Fast path: this worktree (or an ancestor) carries the config.
    for candidate in [p, *p.parents]:
        cfg = _load_config_at(candidate)
        if cfg is not None:
            return cfg

    # Sibling fallback: a linked worktree with no local/ancestor config still
    # belongs to the ddaro project if its MAIN worktree carries one.
    main_root = _main_worktree_root(p)
    if main_root is not None:
        cfg = _load_config_at(main_root)
        if cfg is not None:
            return cfg

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
