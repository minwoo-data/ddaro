"""Shared helpers for ddaro main_protection hooks.

Philosophy: fail open on any exception. Blocking a user because our hook
misread a file is worse than missing an unwanted commit. strict mode is
opt-in, so users who want the guarantee accept the cost of occasional
misses when Python / config / environment goes sideways.

The protective hooks (main_protection, branch naming, ...) never shell out.
The merge-gate helpers at the bottom (0.10.0) use git/gh only to classify a
command that was already identified as a gate target (branch lookup,
`@{push}`, `gh pr view`, `gh pr list`), each with a time limit, and the
merge-gate hook fails CLOSED once a target is identified (merge-gate.md L9).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Optional


def read_stdin_text() -> str:
    """All of stdin, decoded as UTF-8 regardless of the OS locale.

    Claude Code sends hook payloads as raw UTF-8 JSON and Git Bash heredocs
    are UTF-8 too, but Python's default pipe encoding on Windows is the ANSI
    code page (cp1252 on a US-locale install) with surrogateescape: Korean
    turns into mojibake plus lone surrogates that later crash a UTF-8 file
    write. Decode the bytes ourselves (utf-8-sig also drops a PowerShell BOM).
    """
    buf = getattr(sys.stdin, "buffer", None)
    if buf is None:
        return sys.stdin.read()
    return buf.read().decode("utf-8-sig", errors="replace")


def utf8_stdio() -> None:
    """Best effort: make print() emit UTF-8, which is what Claude Code decodes
    hook / command output as. No-op where a stream cannot be reconfigured."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def read_payload() -> Optional[dict]:
    """Read a JSON payload from stdin. Return None on any error."""
    try:
        raw = read_stdin_text()
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


# --- 0.8.0: base branch / snapshot helpers ---------------------------------

DEFAULT_BASE_BRANCH = "main"


def base_branch(cfg: Optional[dict]) -> str:
    """The merge-target branch (`config.base_branch`), default `main`.

    Hooks read ONLY this cached value - detection lives in config_tool.py
    (a subprocess-driven CLI the slash commands run), so the blocking
    PreToolUse path never shells out."""
    try:
        v = str((cfg or {}).get("base_branch") or "").strip()
    except Exception:
        v = ""
    return v or DEFAULT_BASE_BRANCH


def persistence_enabled(cfg: Optional[dict]) -> bool:
    """`context_persistence` master switch (absent == true). Gates every
    context-MD write: hook, write, enrich, init."""
    return (cfg or {}).get("context_persistence", True) is not False


def snapshot_enabled(cfg: Optional[dict]) -> bool:
    """HOOK-MODE gate only: persistence on AND `auto_snapshot` not `off`
    (absent == on). `auto_snapshot: off` means 'do not snapshot every plain
    git commit automatically' - /ddaro:commit (enrich/write) still writes."""
    if not persistence_enabled(cfg):
        return False
    return str((cfg or {}).get("auto_snapshot", "on")).strip().lower() != "off"


def worktree_root(path: Path) -> Optional[Path]:
    """Walk up from `path` to the first directory that contains `.git`
    (a directory for the main worktree, a FILE for a linked worktree).
    Returns None when no git boundary is found or on any error."""
    try:
        p = Path(path).resolve()
    except Exception:
        return None
    for candidate in [p, *p.parents]:
        try:
            if (candidate / ".git").exists():
                return candidate
        except Exception:
            continue
    return None


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


_MSYS_DRIVE_RE = re.compile(r"^/(?:cygdrive/)?([a-zA-Z])(?=/|$)")


def native_path(raw: str, windows: Optional[bool] = None) -> str:
    """Translate a shell path to one Python can open.

    Claude Code's Bash tool on Windows is Git Bash, so commands routinely carry
    MSYS drive paths (`/c/Users/x`) or Cygwin ones (`/cygdrive/c/x`); Python on
    Windows reads `/c/Users/x` as `C:\\c\\Users\\x`. Also expands a leading `~`.
    `windows` defaults to the running OS (parameter exists for tests)."""
    if windows is None:
        windows = os.name == "nt"
    if raw.startswith("~"):
        raw = os.path.expanduser(raw)
    if windows:
        m = _MSYS_DRIVE_RE.match(raw)
        if m:
            raw = f"{m.group(1).upper()}:" + (raw[m.end():] or "/")
    return raw


def _join_dir(cwd: Path, raw: str) -> Path:
    try:
        p = Path(native_path(raw))
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


def command_git_commit_targets(command: str, cwd: Path, follow_cd: bool = False) -> list:
    """Worktree dirs a `git commit` in `command` would land in.

    One Path per `git [global-opts] commit ...` invocation (the effective
    target dir after -C / --work-tree, defaulting to cwd). `git commit-graph`,
    `git log --grep=commit`, and `git merge` do NOT match. Never raises.

    `follow_cd=True` (0.8.0, used by the snapshot hook only) also tracks
    `cd <dir>` / `pushd <dir>` segments, so in `cd ../wt && git commit` the
    commit resolves to `../wt` relative to `cwd`. Default False keeps the
    protective hooks' behaviour unchanged."""
    targets = []
    try:
        here = cwd
        for seg in _split_segments(command):
            toks = _tokenize(seg)
            if follow_cd and toks:
                head = toks[0].lstrip("(")
                if head in ("cd", "pushd") and len(toks) > 1 and not toks[1].startswith("-"):
                    here = _join_dir(here, toks[1])
                    continue
            base = here if follow_cd else cwd
            for i, tok in enumerate(toks):
                if tok == "git" or tok.endswith("/git"):
                    target, sub = _scan_git_invocation(toks, i + 1, base)
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


# --- 0.10.0: merge gate helpers --------------------------------------------
#
# Everything below is NEW surface for the merge gate (hooks/gate.py and
# hooks/check-merge-gate.py). Nothing above changed: the protective hooks keep
# their exact behaviour (tests/test_shared.py pins the return contracts). The
# gate helpers may shell out to git, but only to classify a command that was
# already identified as a gate target (branch lookup, `@{push}`, `gh pr view`,
# `gh pr list`), each with its own time limit. `check-worktree-branch-match`
# already uses `git symbolic-ref` the same way.

# (hashlib, subprocess and time are imported inside the functions that use them, so the
#  existing hooks' import of this module pays nothing for the gate helpers.)

_TOKEN_LEAD = "({!"
_TOKEN_TAIL = ")};"


def strip_token(tok: str) -> str:
    """Peel shell grouping punctuation off a token before comparing it:
    leading `(`, `{`, `!` and trailing `)`, `}`, `;` (L8)."""
    try:
        return tok.lstrip(_TOKEN_LEAD).rstrip(_TOKEN_TAIL)
    except Exception:
        return tok


def segments_with_cwd(command: str, cwd: Path) -> list:
    """Split `command` into segments and give each its effective cwd.

    Returns a list of dicts `{"text", "tokens", "cwd"}` in order. `cd <dir>` /
    `pushd <dir>` segments are included (their own `cwd` is the directory
    BEFORE the change) and every later segment's `cwd` reflects them, relative
    paths resolved against the previous cwd. This is the cd tracking that
    `command_git_commit_targets(follow_cd=True)` keeps private, extracted so the
    merge gate can scan every token of every segment. Never raises."""
    out = []
    try:
        here = Path(cwd)
        for seg in _split_segments(command):
            toks = _tokenize(seg)
            out.append({"text": seg, "tokens": toks, "cwd": here})
            if toks:
                head = strip_token(toks[0])
                if head in ("cd", "pushd") and len(toks) > 1 and not toks[1].startswith("-"):
                    here = _join_dir(here, strip_token(toks[1]))
    except Exception:
        pass
    return out


def scan_git_global_opts(tokens: list, start: int, cwd: Path):
    """Gate-side git option scanner. Like `_scan_git_invocation` but a
    relative `-C` accumulates on the previous one (as git itself does:
    `git -C a -C b` runs in `cwd/a/b`), and the `-c key=value` pairs are
    returned too. Returns (target_dir, subcommand, sub_index, configs) where
    sub_index is the token index of the subcommand (or None)."""
    target = Path(cwd)
    configs = []
    i = start
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if not tok.startswith("-"):
            return target, strip_token(tok), i, configs
        key, eq, inline = tok.partition("=")
        if key in _GIT_DIR_OPTS:
            val = None
            if eq:
                val = inline
            elif i + 1 < n:
                val = tokens[i + 1]
                i += 1
            if val is not None:
                target = _join_dir(target if key == "-C" else Path(cwd), val)
            i += 1
            continue
        if key == "-c":
            if eq:
                configs.append(inline)
            elif i + 1 < n:
                configs.append(tokens[i + 1])
                i += 1
            i += 1
            continue
        if key in _GIT_OPTS_WITH_ARG and not eq:
            i += 2
            continue
        i += 1
    return target, None, None, configs


def _basename_lower(tok: str) -> str:
    t = strip_token(tok).replace("\\", "/").lower()
    return t.rsplit("/", 1)[-1]


def is_git_token(tok: str) -> bool:
    """`git`, `git.exe`, or a path ending in one of them."""
    return _basename_lower(tok) in ("git", "git.exe")


def is_gh_token(tok: str) -> bool:
    """`gh`, `gh.exe`, or a path ending in one of them."""
    return _basename_lower(tok) in ("gh", "gh.exe")


def run_cmd(args: list, cwd: Optional[Path] = None, timeout: float = 10.0, env: Optional[dict] = None):
    """Run a command, kill its whole process tree on timeout. Returns
    (returncode, stdout, stderr) with text decoded as UTF-8; returncode is
    None when the command could not run or timed out. Never raises."""
    import subprocess
    try:
        kwargs = dict(cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
        if env is not None:
            kwargs["env"] = env
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(args, **kwargs)
    except Exception as e:  # FileNotFoundError, OSError, ...
        return None, "", str(e)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=5)
        except Exception:
            out, err = b"", b""
        return None, out.decode("utf-8", "replace"), (err.decode("utf-8", "replace") + "\n[timeout]")
    return proc.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def kill_tree(proc) -> None:
    """Terminate `proc` and every descendant. Best effort, never raises."""
    import subprocess
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=10)
        else:
            import signal
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def git_out(args: list, cwd: Path, timeout: float = 10.0) -> Optional[str]:
    """`git <args>` in cwd; stripped stdout on exit 0, None otherwise."""
    rc, out, _ = run_cmd(["git", *args], cwd=cwd, timeout=timeout)
    if rc != 0:
        return None
    return out.strip()


def main_root_of(path: Path) -> Optional[Path]:
    """`<main>` for any path inside a repository: the parent of
    `git rev-parse --git-common-dir` (L10). None outside a repository."""
    try:
        p = Path(path)
        if not p.is_dir():
            p = p.parent
        common = git_out(["rev-parse", "--path-format=absolute", "--git-common-dir"], p)
        if not common:
            common = git_out(["rev-parse", "--git-common-dir"], p)
            if not common:
                return None
            c = Path(common)
            if not c.is_absolute():
                top = git_out(["rev-parse", "--show-toplevel"], p)
                c = (Path(top) if top else p) / c
            common = str(c)
        return Path(common).resolve().parent
    except Exception:
        return None


def load_main_config_status(main: Optional[Path]):
    """(cfg or None, status) for `<main>/.ddaro/config.json`; status is one
    of `ok`, `missing`, `unparseable`. Gate keys are read ONLY through this
    (L10): a config nearer to cwd than `<main>` is never consulted."""
    if main is None:
        return None, "missing"
    p = Path(main) / ".ddaro" / "config.json"
    try:
        if not p.is_file():
            return None, "missing"
        text = p.read_text(encoding="utf-8")
    except Exception:
        return None, "unparseable"
    try:
        cfg = json.loads(text)
    except Exception:
        return None, "unparseable"
    if not isinstance(cfg, dict):
        return None, "unparseable"
    return cfg, "ok"


def gate_mode(cfg: Optional[dict]) -> str:
    """`merge_gate` normalized: off | warn | strict. Absent = off; an unknown
    value counts as strict (L12: unknown values err toward the gate)."""
    if cfg is None:
        return "off"
    v = cfg.get("merge_gate")
    if v is None:
        return "off"
    s = str(v).strip().lower()
    return s if s in ("off", "warn", "strict") else "strict"


def gate_marker_path(main: Path) -> Optional[Path]:
    """`$(git rev-parse --git-common-dir)/ddaro-gate` (L10). Left by
    config_tool when the gate is warn/strict, removed only when set to off."""
    try:
        common = git_out(["rev-parse", "--path-format=absolute", "--git-common-dir"], Path(main))
        if common:
            return Path(common) / "ddaro-gate"
        dotgit = Path(main) / ".git"
        if dotgit.is_dir():
            return dotgit / "ddaro-gate"
    except Exception:
        pass
    return None


def parse_lock(path: Path) -> Optional[dict]:
    """Read a ddaro `.ddaro/LOCK`: JSON, or the old `key=value` lines
    (donghaeng's `branch=d-busan`). None when absent or unreadable."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except Exception:
        return None
    try:
        d = json.loads(text)
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    out = {}
    for line in text.splitlines():
        k, eq, v = line.partition("=")
        if eq and k.strip():
            out[k.strip()] = v.strip()
    return out or None


def claude_config_dir() -> Path:
    """`~/.claude`, or `$CLAUDE_CONFIG_DIR` when set (Claude Code's own
    override; also what the tests use)."""
    v = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    return Path(v) if v else Path.home() / ".claude"


def prism_install_path() -> tuple:
    """(installPath, None) of the installed prism from
    `installed_plugins.json` `prism@haroom_plugins` (E18), or (None, reason).
    The cache folder is never searched: several versions sit side by side."""
    p = claude_config_dir() / "plugins" / "installed_plugins.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"{p} not found"
    except Exception as e:
        return None, f"{p} unreadable: {e}"
    plugins = data.get("plugins", data) if isinstance(data, dict) else None
    if not isinstance(plugins, dict):
        return None, f"{p}: no plugins map"
    entry = plugins.get("prism@haroom_plugins")
    if isinstance(entry, list):
        entry = entry[0] if entry else None
    if not isinstance(entry, dict):
        return None, "prism@haroom_plugins not installed"
    ip = entry.get("installPath")
    if not ip:
        return None, "prism@haroom_plugins has no installPath"
    return Path(str(ip)), None


def prism_report_contract(install_path: Path) -> tuple:
    """(major:int, None) from `<installPath>/skills/prism/report-contract.json`,
    or (None, reason). prism <= 0.5.x has no such file."""
    f = Path(install_path) / "skills" / "prism" / "report-contract.json"
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        major = int(str(data["report_contract"]).split(".")[0])
    except FileNotFoundError:
        return None, f"{f} not found"
    except Exception as e:
        return None, f"{f} unreadable: {e}"
    return major, None


class file_lock:
    """Short OS lock on `path` (msvcrt.locking on Windows, fcntl.flock
    elsewhere), used as a context manager. Released when the process dies.
    Raises TimeoutError("locked by pid N") when not acquired within `timeout`
    seconds (L1). The locked byte is byte 0; the holder's pid is written from
    byte 1 so a waiter can read it (Windows byte-range locks are mandatory)."""

    def __init__(self, path, timeout: float = 5.0):
        self.path = Path(path)
        self.timeout = timeout
        self.fh = None
        self.locked = False

    def __enter__(self):
        import time
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = fh = open(self.path, "a+")
        try:
            deadline = time.monotonic() + self.timeout
            while True:
                try:
                    if os.name == "nt":
                        import msvcrt
                        fh.seek(0)
                        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.locked = True
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        owner = ""
                        try:
                            fh.seek(1)
                            owner = fh.read(64).strip()
                        except Exception:
                            pass
                        raise TimeoutError(f"locked by pid {owner or '?'}")
                    time.sleep(0.1)
            try:
                fh.seek(0)
                fh.truncate()
                fh.write(" " + str(os.getpid()))
                fh.flush()
            except Exception:
                pass
        except BaseException:
            fh.close()
            self.fh = None
            raise
        return self

    def __exit__(self, *exc):
        fh = self.fh
        if fh is None:
            return False
        if self.locked:
            try:
                if os.name == "nt":
                    import msvcrt
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
        fh.close()
        self.fh = None
        return False


def branch_enc(branch: str) -> str:
    """Percent-encode a branch name (everything outside `a-z 0-9 - _`,
    uppercase included) and append `.` + the first 8 hex of sha1 of the exact
    name: `branch_enc("d-busan") == "d-busan.f486a3be"` (L2)."""
    import hashlib
    safe = set("abcdefghijklmnopqrstuvwxyz0123456789-_")
    enc = "".join(c if c in safe else "".join(f"%{b:02X}" for b in c.encode("utf-8")) for c in branch)
    return f"{enc}.{hashlib.sha1(branch.encode('utf-8')).hexdigest()[:8]}"
