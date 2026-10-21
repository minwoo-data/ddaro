#!/usr/bin/env python3
"""ddaro PreToolUse hook: the merge gate guard (0.10.0, merge-gate.md L8-L13, L11).

Registered once for `Bash|Edit|Write|NotebookEdit`. With `merge_gate: off`
(the default) it changes nothing. In `warn` it lets every command run and adds
an `additionalContext` warning for the model. In `strict` it blocks (exit 2):

- `gh pr merge` without `--match-head-commit <PR head>`; with it, when that
  head has no PASS (`gate.status`), unless the PR is docs-only or a person
  approved the commit. `--auto`, a merge chained after a branch-changing git
  command, and a PR head that is not local are blocked too.
- `gh api` that is not a GET (file bodies and GraphQL bodies that cannot be
  read inline count as writes); `gh alias set|import`; shell (`!`) git or gh
  aliases; git aliases created with `-c alias.*` / `config alias.*`.
- `git push` to the base branch (explicit or wildcard refspec, `--all`,
  `--mirror`, `--delete`, an implied target, `send-pack`), `-c push.*|remote.*|
  branch.*`, and a push to a branch whose open PR has auto-merge on while the
  pushed commit is not mergeable.
- Human-only commands: `gate.py approve|reset`, `gate.py close` without
  `--merged`, a weakening `config_tool.py set`, `config_tool.py init` where a
  config exists or where the gate marker says the gate is on.
- Writes (Edit/Write/NotebookEdit and shell write targets: redirects, tee,
  sed -i, truncate, cp/mv/install destinations incl. `-t`, rm/mv sources,
  python/node write calls, `git clean -x`, `git stash --all`) to
  `<main>/.ddaro/config.json` when weakening or when the file would stop
  parsing, `.ddaro/gates/**`, `.ddaro/verify.json`, a run folder's
  `prism-report.json` / `prism-run.json`, the `.ddaro` folder itself (globs
  included), a `.ddaro/config.json` outside `<main>`, the gate marker
  `<git-common-dir>/ddaro-gate`, and git's own config files (alias source).

Gate settings are read from `<main>/.ddaro/config.json` only (`<main>` =
parent of `git rev-parse --git-common-dir`, resolved per segment after cd /
`-C`); a nearer config is ignored (L10). A `<main>` whose config is unparseable,
or which has the `ddaro-gate` marker but no config, counts as strict (L9).

Fast path, stdlib only: `tool_input.command` must contain `git`, `gh`,
`gate.py`, `config_tool.py` or `.ddaro` as a word (case-insensitive); Edit/
Write paths must contain `.ddaro` or end in `ddaro-gate`. Then a filesystem
only lookup (no subprocess) decides whether ANY directory the command touches
(payload cwd, every `cd`, every `-C`, the edited file's repo) belongs to a
repository whose gate is on; when none does the hook exits before importing
anything heavy. Once a gate target is identified, any exception (ImportError
included) blocks in strict (L9); an exception before identification falls back
to raw-text regexes judged with the same filesystem-only lookup.

The hook never prints `permissionDecision` (allow would skip the user's own
permission prompt). Known gaps are listed in the design document's threat
model: commands inside scripts / `bash -c` / `eval` / command substitution, the
user's own terminal and `!` commands, hooks that cannot run, copies of the
gate scripts under another name, a cwd outside every repository combined with
a variable that was set in another command.
"""

from __future__ import annotations

import json
import os
import re
import sys

# --- fast path (stdlib only) ------------------------------------------------

_WORD = r"(?<![A-Za-z0-9_\-])(?:{})(?![A-Za-z0-9_])"
FAST_RE = re.compile(_WORD.format(r"git(?:\.exe)?|git-[a-z-]+(?:\.exe)?|gh(?:\.exe)?|gate\.py|config_tool\.py|\.ddaro|ddaro-gate|\.gitconfig|config\.yml"), re.I)
RAW_GH_RE = re.compile(r"\bgh(\.exe)?\b.*\b(pr\s+merge|api)\b", re.S | re.I)
RAW_PUSH_RE = re.compile(r"\bgit(\.exe)?\b.*\b(push|send-pack)\b", re.S | re.I)
RAW_SCRIPT_RE = re.compile(r"gate\.py|config_tool\.py|\.ddaro[/\\]|ddaro-gate", re.I)
_CD_SPLIT = re.compile(r"&&|\|\||;|&|\||\n|`")
GLOB_RE = re.compile(r"[*?\[{]")
WRITE_SHAPE_RE = re.compile(r">|\b(tee|cp|mv|rm|rmdir|install|dd|rsync|truncate|shred|unlink)\b|\bsed\b.*\s-i|\bperl\b.*\s-\w*i", re.S)
ENV_ALIAS_RE = re.compile(r"^(GIT_CONFIG_PARAMETERS|GIT_CONFIG_COUNT|GIT_CONFIG_KEY_\d+|GIT_CONFIG_VALUE_\d+|GIT_CONFIG_GLOBAL|GIT_CONFIG_SYSTEM|GIT_CONFIG_NOSYSTEM|HOME|XDG_CONFIG_HOME|GH_CONFIG_DIR|GIT_EXEC_PATH|GIT_DIR|GIT_COMMON_DIR)=")


def _read_payload():
    try:
        raw = sys.stdin.buffer.read()
    except Exception:
        return None
    try:
        return json.loads(raw.decode("utf-8-sig", errors="replace"))
    except Exception:
        return None


def _fast_reject(payload) -> bool:
    """True when this payload cannot be a gate target."""
    if not isinstance(payload, dict):
        return True
    tool = payload.get("tool_name") or ""
    ti = payload.get("tool_input") or {}
    if tool == "Bash":
        cmd = ti.get("command")
        if not isinstance(cmd, str):
            return True
        if FAST_RE.search(cmd):
            return False
        # a glob in a write command may expand to a protected path (`.ddar[o]/gates/x`)
        return not (GLOB_RE.search(cmd) and WRITE_SHAPE_RE.search(cmd))
    if tool in ("Edit", "Write", "NotebookEdit"):
        p = str(ti.get("file_path") or ti.get("notebook_path") or "").replace("\\", "/").lower()
        return ".ddaro" not in p and not p.endswith(("/ddaro-gate", "/.git/config", "/.gitconfig", "/config.yml", "/git/config"))
    return True


def _fs_repo(path: str):
    """(main, common_dir) for `path` by walking up to a `.git` entry and
    following a linked worktree's gitdir -> commondir. Filesystem only.
    (None, None) when no `.git` is found or anything fails."""
    try:
        p = os.path.abspath(path)
        while True:
            marker = os.path.join(p, ".git")
            if os.path.isdir(marker):
                return p, marker
            if os.path.isfile(marker):
                with open(marker, encoding="utf-8", errors="replace") as fh:
                    content = fh.read().strip()
                if not content.startswith("gitdir:"):
                    return None, None
                gitdir = content[len("gitdir:"):].strip()
                if not os.path.isabs(gitdir):
                    gitdir = os.path.normpath(os.path.join(p, gitdir))
                cd_file = os.path.join(gitdir, "commondir")
                if os.path.isfile(cd_file):
                    with open(cd_file, encoding="utf-8", errors="replace") as fh:
                        rel = fh.read().strip()
                    common = os.path.normpath(os.path.join(gitdir, rel))
                else:
                    common = os.path.dirname(os.path.dirname(gitdir))
                return os.path.dirname(common), common
            parent = os.path.dirname(p)
            if parent == p:
                return None, None
            p = parent
    except Exception:
        return None, None


def _fs_mode(main, common) -> str:
    """off | warn | strict for `<main>` from its config and the marker, stdlib only."""
    if not main:
        return "off"
    cfg_path = os.path.join(main, ".ddaro", "config.json")
    has_marker = bool(common) and os.path.exists(os.path.join(common, "ddaro-gate"))
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as fh:
                cfg = json.load(fh)
            if not isinstance(cfg, dict):
                return "strict"
        except Exception:
            return "strict"
        v = cfg.get("merge_gate")
        if v is None:
            s = "off"
        else:
            s = str(v).strip().lower()
            if s not in ("off", "warn", "strict"):
                s = "strict"
        if s != "off":
            return s
        # config says off while a person's marker says on: the config was replaced, not set
        return "strict" if has_marker else "off"
    return "strict" if has_marker else "off"


def _native(raw: str) -> str:
    m = re.match(r"^/(?:cygdrive/)?([a-zA-Z])(?=/|$)", raw)
    if m and os.name == "nt":
        raw = f"{m.group(1).upper()}:" + (raw[m.end():] or "/")
    if raw.startswith("~"):
        raw = os.path.expanduser(raw)
    return raw


def _context_dirs(payload) -> list:
    """Every directory a command may act in: payload cwd, each `cd`/`pushd`
    target, each `git -C` target, the edited file's directory. Stdlib only."""
    ti = payload.get("tool_input") or {}
    cwd = str(payload.get("cwd") or os.getcwd())
    dirs = [cwd]
    tool = payload.get("tool_name") or ""
    if tool != "Bash":
        p = str(ti.get("file_path") or ti.get("notebook_path") or "")
        if p:
            dirs.append(os.path.dirname(_native(p)) or cwd)
        return dirs
    cmd = str(ti.get("command") or "")
    here = cwd
    import shlex
    for seg in _CD_SPLIT.split(cmd):
        try:
            toks = shlex.split(seg, posix=True)
        except ValueError:
            raise RuntimeError("unparseable segment")      # caller: no early exit, go to the slow path
        if not toks:
            continue
        head = toks[0].lstrip("({!")
        if head in ("cd", "pushd") and len(toks) > 1 and not toks[1].startswith("-"):
            tgt = _native(toks[1].strip("'\"").rstrip(");}"))
            here = tgt if os.path.isabs(tgt) else os.path.join(here, tgt)
            dirs.append(here)
            continue
        dirs.append(here)
        for k, t in enumerate(toks):
            if t in ("-C", "--work-tree") and k + 1 < len(toks):
                tgt = _native(toks[k + 1].strip("'\""))
                dirs.append(tgt if os.path.isabs(tgt) else os.path.join(here, tgt))
            elif t.startswith("-C") and len(t) > 2:
                tgt = _native(t[2:].strip("'\""))
                dirs.append(tgt if os.path.isabs(tgt) else os.path.join(here, tgt))
            elif t.startswith("--work-tree="):
                tgt = _native(t.split("=", 1)[1].strip("'\""))
                dirs.append(tgt if os.path.isabs(tgt) else os.path.join(here, tgt))
            else:
                val = t.split("=", 1)[1] if "=" in t else t      # `NAME=/path` assignments count too
                m = re.match(r"^(\d*)(>>?|&>)(.+)$", val)
                if m:
                    val = m.group(3)
                val = _native(val.strip("'\""))
                if val.startswith("/") or re.match(r"^[A-Za-z]:/", val):
                    dirs.append(val)
                    dirs.append(os.path.dirname(val))
                elif not val.startswith("-") and ("/" in val or "\\" in val or os.path.isdir(os.path.join(here, val))):
                    joined = os.path.join(here, val.replace("\\", "/"))      # relative paths resolve against the segment cwd
                    dirs.append(joined)
                    dirs.append(os.path.dirname(joined))
    return dirs


def _any_gated(payload) -> str:
    """The strongest gate mode among the command's context directories
    (filesystem only). `off` means no subprocess is worth running."""
    best = "off"
    seen = set()
    for d in _context_dirs(payload):
        main, common = _fs_repo(d)
        key = main or ""
        if key in seen:
            continue
        seen.add(key)
        mode = _fs_mode(main, common)
        if mode == "strict":
            return "strict"
        if mode == "warn":
            best = "warn"
    return best


# --- slow path --------------------------------------------------------------

HOOK_DEADLINE = 20.0
GH_TIMEOUT = 10
GIT_TIMEOUT = 5
BUILTIN_GIT = {
    "add", "am", "annotate", "apply", "archive", "bisect", "blame", "branch", "bundle", "cat-file", "checkout",
    "cherry", "cherry-pick", "clean", "clone", "commit", "commit-graph", "config", "describe", "diff", "difftool",
    "fetch", "format-patch", "fsck", "gc", "grep", "init", "log", "ls-files", "ls-remote", "ls-tree", "merge",
    "merge-base", "merge-tree", "mv", "notes", "pull", "push", "range-diff", "rebase", "reflog", "remote",
    "repack", "replace", "reset", "restore", "rev-list", "rev-parse", "revert", "rm", "shortlog", "show",
    "show-ref", "sparse-checkout", "stash", "status", "submodule", "switch", "symbolic-ref", "tag", "update-ref",
    "whatchanged", "worktree", "for-each-ref", "name-rev", "var", "version", "help", "send-pack", "http-push",
    "lfs", "flow", "filter-repo", "credential", "maintenance", "count-objects", "verify-pack", "hash-object",
    "update-index", "read-tree", "write-tree", "mktree", "mailinfo", "mailsplit", "daemon", "instaweb", "gui",
    "citool", "bugreport", "diagnose", "interpret-trailers", "stripspace", "rerere", "prune", "fast-export",
    "fast-import", "request-pull", "merge-file", "diff-tree", "diff-index", "diff-files", "show-branch",
}
BRANCH_CHANGING = {"push", "commit", "merge", "rebase", "reset", "cherry-pick", "am", "send-pack"}
PUSH_LIKE = {"push", "send-pack", "http-push"}
GH_COMMANDS = {"alias", "api", "auth", "browse", "codespace", "completion", "config", "extension", "gist", "gpg-key",
               "issue", "label", "org", "pr", "project", "release", "repo", "ruleset", "run", "search", "secret",
               "ssh-key", "status", "variable", "workflow", "cache", "attestation", "help", "version", "ext", "co",
               "copilot", "preview"}


class Finding:
    def __init__(self, mode: str, message: str, kind: str):
        self.mode = mode          # strict | warn
        self.message = message
        self.kind = kind


class Guard:
    def __init__(self, payload: dict):
        import time
        from pathlib import Path
        import _shared as sh
        import config_tool as ct
        self.time, self.Path, self.sh, self.ct = time, Path, sh, ct
        self.payload = payload
        self.started = time.monotonic()
        self.findings: list = []
        self.identified = False
        self._mode_cache: dict = {}
        self._gate_mod = None
        self._gh_alias_cache = None
        self.payload_cwd = sh.cwd_from_payload(payload)

    # --- helpers
    def gate(self):
        if self._gate_mod is None:
            import gate as gate_mod
            self._gate_mod = gate_mod
        return self._gate_mod

    def deadline_left(self) -> float:
        return HOOK_DEADLINE - (self.time.monotonic() - self.started)

    def check_deadline(self):
        if self.deadline_left() <= 0:
            raise TimeoutError("hook deadline (20 s) exceeded")

    def git_timeout(self) -> float:
        return max(1.0, min(GIT_TIMEOUT, self.deadline_left()))

    def gh_timeout(self) -> int:
        return max(1, min(GH_TIMEOUT, int(self.deadline_left())))

    def main_of(self, path):
        """(main or None, status) status: ok | not_repo | git_failed."""
        try:
            p = self.Path(path)
            hops = 0
            while not p.exists() and p.parent != p and hops < 64:
                p = p.parent            # a file or folder that does not exist yet: judge by its nearest ancestor
                hops += 1
            if not p.exists():
                return None, "not_repo"
            if not p.is_dir():
                p = p.parent
            rc, out, _ = self.sh.run_cmd(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=p,
                                         timeout=self.git_timeout())
            if rc is None:
                return None, "git_failed"
            if rc != 0 or not out.strip():
                return None, "not_repo"
            return self.Path(out.strip()).resolve().parent, "ok"
        except Exception:
            return None, "git_failed"

    def main_or_refuse(self, path, what: str):
        """Resolve `<main>` for a command already recognised as a gate target.
        Falls back to the payload cwd's repository; a git failure or an
        unresolvable location is refused when any context is gated (L9)."""
        main, st = self.main_of(path)
        if main is not None:
            return main
        main2, st2 = self.main_of(self.payload_cwd)
        if main2 is not None and st != "git_failed":
            return main2
        mode = _any_gated(self.payload)
        if mode != "off":
            self.identified = True
            if st == "git_failed" or st2 == "git_failed":
                msg = (f"[ddaro] merge_gate: git could not run while checking `{what}`; refused.\n"
                       "  fix git / PATH and retry, or a person runs it with `!`")
            else:
                msg = (f"[ddaro] merge_gate: `{what}` runs in a directory the gate cannot resolve; refused.\n"
                       "  run it from inside the repository, or a person runs it with `!`")
            self.findings.append(Finding(mode, msg, "unresolvable"))
        return None

    def mode_for(self, main) -> str:
        """off | warn | strict for `<main>` (L9/L10)."""
        if main is None:
            return "off"
        key = str(main)
        if key in self._mode_cache:
            return self._mode_cache[key]
        cfg, st = self.sh.load_main_config_status(main)
        marker = self.sh.gate_marker_path(main)
        has_marker = marker is not None and marker.exists()
        if st == "ok":
            mode = self.sh.gate_mode(cfg)
            if mode == "off" and has_marker:
                mode = "strict"      # a config saying off while the marker exists was not written by config_tool
        elif st == "unparseable":
            mode = "strict"
        else:
            mode = "strict" if has_marker else "off"
        self._mode_cache[key] = mode
        return mode

    def cfg_for(self, main):
        cfg, _ = self.sh.load_main_config_status(main)
        return cfg or {}

    def note(self, main, message: str, kind: str, mode: str = None):
        m = mode or self.mode_for(main)
        if m == "off":
            return
        self.identified = True
        self.findings.append(Finding(m, message, kind))

    def norm_path(self, p) -> str:
        try:
            return self.Path(p).resolve().as_posix().lower()
        except Exception:
            return str(p).replace("\\", "/").lower()

    def origin_slug(self, main) -> str:
        url = self.sh.git_out(["remote", "get-url", "origin"], main, timeout=self.git_timeout()) or ""
        return self.repo_slug(url)

    @staticmethod
    def repo_slug(s: str) -> str:
        s = s.strip().lower()
        s = re.sub(r"^[a-z]+://", "", s)
        s = re.sub(r"^[^@/]+@", "", s)       # git@host:
        s = s.replace(":", "/")
        s = re.sub(r"\.git$", "", s.rstrip("/"))
        parts = [p for p in s.split("/") if p]
        if len(parts) >= 3 and "." in parts[0]:
            parts = parts[1:]                # drop the host
        return "/".join(parts[-2:]) if len(parts) >= 2 else s

    def protected_paths(self, main) -> set:
        """Normalized absolute paths that only ddaro's scripts (or a person) may write:
        the gate marker, git's config files (alias sources), gh's config."""
        out = set()
        marker = self.sh.gate_marker_path(main)
        if marker is not None:
            out.add(self.norm_path(marker))
            out.add(self.norm_path(marker.parent / "config"))
        try:
            home = self.Path.home()
            out.add(self.norm_path(home / ".gitconfig"))
            out.add(self.norm_path(home / ".config" / "git" / "config"))
            out.add(self.norm_path(home / ".config" / "gh" / "config.yml"))
            appdata = os.environ.get("APPDATA")
            if appdata:
                out.add(self.norm_path(self.Path(appdata) / "GitHub CLI" / "config.yml"))
        except Exception:
            pass
        return out

    # --- entry
    def run(self):
        tool = self.payload.get("tool_name") or ""
        ti = self.payload.get("tool_input") or {}
        if tool == "Bash":
            self.bash(str(ti.get("command") or ""))
        else:
            self.edit(tool, ti)

    # --- Edit / Write / NotebookEdit (L11)
    def edit(self, tool: str, ti: dict):
        target = ti.get("file_path") or ti.get("notebook_path") or ""
        if not target:
            return
        tp = self.Path(str(self.sh.native_path(str(target))))
        norm = self.norm_path(tp)
        main, st = self.main_of(tp.parent if tp.suffix or not tp.exists() else tp)
        if main is None:
            if norm.endswith(("/.gitconfig", "/.config/git/config", "/config.yml")):
                main = self.main_or_refuse(self.payload_cwd, f"{tool} {tp}")
                if main is not None and norm in self.protected_paths(main):
                    self.note(main, self.msg_protected(tp.name), "protected")
                return
            if st == "git_failed":
                self.main_or_refuse(tp.parent, f"{tool} {tp}")
            return
        mode = self.mode_for(main)
        if mode == "off":
            return
        if norm in self.protected_paths(main):
            self.note(main, self.msg_protected(tp.name), "protected")
            return
        main_n = self.norm_path(main)
        rel = norm[len(main_n) + 1:] if norm.startswith(main_n + "/") else None
        if rel is None:
            if re.search(r"(^|/)\.ddaro/config\.json$", norm):
                self.note(main, self.msg_outside_config(tp), "config_outside")
            return
        if rel == ".ddaro/config.json":
            self.identified = True
            try:
                cur = (main / ".ddaro" / "config.json").read_text(encoding="utf-8")
            except Exception:
                cur = ""
            if tool == "Write":
                new_text = str(ti.get("content") or "")
            elif tool == "Edit":
                old_s, new_s = str(ti.get("old_string") or ""), str(ti.get("new_string") or "")
                if old_s and old_s in cur:
                    new_text = cur.replace(old_s, new_s) if ti.get("replace_all") else cur.replace(old_s, new_s, 1)
                else:
                    new_text = cur
            else:
                new_text = ""
            corrupt = False
            try:
                if not cur.strip():
                    raise ValueError("empty")
                old_cfg = json.loads(cur)
                if not isinstance(old_cfg, dict):
                    raise ValueError("not a dict")
            except Exception:
                # The current file does not parse, so the gate is strict right now (L9):
                # the baseline for "weakening" is strict, not the defaults.
                old_cfg = {"merge_gate": "strict"}
                corrupt = True
            try:
                new_cfg = json.loads(new_text)
            except Exception:
                new_cfg = None
            if not isinstance(new_cfg, dict):
                self.note(main, self.msg_weaken(["config.json would stop parsing"]), "weaken")
                return
            if corrupt:
                old_cfg["base_branch"] = new_cfg.get("base_branch")     # unknowable from a corrupt file
            weak = self.ct.weakening_changes(old_cfg, new_cfg)
            if weak:
                self.note(main, self.msg_weaken(weak), "weaken")
            return
        if rel.startswith(".ddaro/gates/") or rel == ".ddaro/verify.json":
            self.note(main, self.msg_protected(rel), "protected")
            return
        if re.match(r"^\.ddaro/runs/[^/]+/[^/]+/(prism-report\.json|prism-run\.json)$", rel):
            self.note(main, self.msg_protected(rel), "protected")

    # --- Bash
    def bash(self, cmd: str):
        self._cmd = cmd
        branch_changing_before = False
        for seg in self.segments(cmd):
            toks = seg["tokens"]
            seg_cwd = seg["cwd"]
            stripped = [self.sh.strip_token(t) for t in toks]
            self.check_deadline()
            env_prefix = [t for t in toks if ENV_ALIAS_RE.match(t)] + \
                         [t for t in seg.get("exports", []) if ENV_ALIAS_RE.match(t)]
            for i, tok in enumerate(toks):
                base = self.sh.strip_token(tok).replace("\\", "/").rsplit("/", 1)[-1].lower()
                dashed = re.fullmatch(r"git-([a-z][a-z-]*)(\.exe)?", base)
                if env_prefix and (self.sh.is_git_token(tok) or dashed or self.sh.is_gh_token(tok)):
                    m, st = self.main_of(seg_cwd)
                    if m is None:
                        m = self.main_or_refuse(seg_cwd, tok)
                    self.note(m, self.msg_human(f"git/gh with a config-redirecting environment ({env_prefix[0].split('=')[0]})"), "alias")
                if self.sh.is_git_token(tok):
                    changed = self.git_invocation(toks, i, seg_cwd)
                    branch_changing_before = branch_changing_before or changed
                elif dashed and all(re.match(r"^[A-Za-z_][A-Za-z0-9_]*=|^env$|^exec$", self.sh.strip_token(x)) for x in toks[:i]):
                    # dashed-form binary `git-push ...` in command position is `git push ...`
                    changed = self.git_invocation(["git", dashed.group(1)] + toks[i + 1:], 0, seg_cwd)
                    branch_changing_before = branch_changing_before or changed
                elif self.sh.is_gh_token(tok):
                    self.gh_invocation(stripped, i, seg_cwd, branch_changing_before)
                elif base in ("gate.py", "config_tool.py"):
                    self.script_invocation(base, stripped, i, seg_cwd)
            self.shell_writes(seg["text"], stripped, seg_cwd)

    def segments(self, cmd: str) -> list:
        """Segments with their effective cwd. Like `_shared.segments_with_cwd`
        but resolves simple `NAME=value` assignments of the same command into
        later `$NAME` tokens, and does not follow a `cd` whose target is still
        unresolvable (`$`, backtick) or does not exist: the shell's cwd is then
        unknown and the previous one is kept."""
        out = []
        env = {}
        exports = []
        here = self.Path(self.payload_cwd)
        for seg in self.sh._split_segments(cmd):
            toks = [self._subst(t, env) for t in self.sh._tokenize(seg)]
            body = toks[1:] if (toks and toks[0] == "export") else toks
            if body:
                m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", body[0])
                if m and (len(body) == 1 or body is not toks):
                    env[m.group(1)] = m.group(2)
                    exports.append(body[0])
            out.append({"text": seg, "tokens": toks, "cwd": here, "exports": list(exports)})
            if toks:
                head = self.sh.strip_token(toks[0])
                if head in ("cd", "pushd") and len(toks) > 1 and not toks[1].startswith("-"):
                    tgt = self.sh.strip_token(toks[1])
                    if "$" in tgt or "`" in tgt:
                        continue
                    nxt = self.sh._join_dir(here, tgt)
                    if nxt.is_dir():
                        here = nxt
        return out

    @staticmethod
    def _subst(tok: str, env: dict) -> str:
        if "$" not in tok or not env:
            return tok

        def rep(m):
            name = m.group(1) or m.group(2)
            return env.get(name, m.group(0))
        return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)", rep, tok)

    # --- git (L13, L11 aliases)
    def git_invocation(self, toks: list, i: int, seg_cwd, depth: int = 0) -> bool:
        target, sub, idx, configs = self.sh.scan_git_global_opts(toks, i + 1, seg_cwd)
        main, st = self.main_of(target)
        if main is None and st == "git_failed":
            main = self.main_or_refuse(target, "git")
        for c in configs:
            if c.lower().startswith("alias."):
                self.note(main, self.msg_human(f"git alias via -c ({c.split('=')[0]})"), "alias")
        for t in toks[i + 1:idx if idx is not None else len(toks)]:
            if t.lower().startswith("--config-env=alias.") or t.lower() == "--config-env":
                self.note(main, self.msg_human("git --config-env alias.*"), "alias")
        if sub is None:
            return False
        rest = toks[idx + 1:]
        if sub == "config" and any(self.sh.strip_token(t).lower().startswith("alias.") for t in rest):
            self.note(main, self.msg_human("git config alias.*"), "alias")
            return False
        if sub not in BUILTIN_GIT and main is not None and self.mode_for(main) != "off" and depth < 3:
            gcfg = []
            for c in configs:
                gcfg += ["-c", c]
            rc, out, _ = self.sh.run_cmd(["git", *gcfg, "config", "--get", f"alias.{sub}"], cwd=target, timeout=self.git_timeout())
            expansion = out.strip() if rc == 0 else None
            if rc is None or (rc not in (0, 1)):
                self.note(main, self.msg_human(f"git `{sub}`: alias lookup failed"), "alias")
                return True
            if not expansion:
                self.note(main, self.msg_human(f"git `{sub}` is not a builtin and no alias resolves it"), "alias")
                return True
            if expansion:
                if expansion.startswith("!"):
                    self.note(main, self.msg_human(f"git alias `{sub}` runs a shell command ({expansion[:40]})"), "alias")
                    return True
                try:
                    exp_toks = self.sh._tokenize(expansion)
                except Exception:
                    exp_toks = expansion.split()
                if exp_toks:
                    # re-scan the expansion with the user's arguments appended
                    return self.git_invocation(["git"] + exp_toks + rest, 0, target, depth + 1)
        if sub in PUSH_LIKE:
            self.push(rest, target, main, configs)
        if sub == "clean" and main is not None:
            flags = [self.sh.strip_token(t) for t in rest if t.startswith("-")]
            if any(f in ("-x", "-X") or (f.startswith("-") and not f.startswith("--") and ("x" in f or "X" in f)) for f in flags):
                if self.norm_path(target) == self.norm_path(main):
                    self.note(main, self.msg_protected(".ddaro (git clean -x/-X in <main>)"), "protected")
        if sub == "stash" and main is not None:
            flags = []
            skip = False
            for t in rest:
                if skip:
                    skip = False
                    continue
                t = self.sh.strip_token(t)
                if t in ("-m", "--message"):
                    skip = True
                    continue
                if t.startswith("-"):
                    flags.append(t)
            all_f = any(f in ("-a", "--all") or (f.startswith("-") and not f.startswith("--") and "a" in f) for f in flags)
            unt_f = any(f in ("-u", "--include-untracked") or (f.startswith("-") and not f.startswith("--") and "u" in f) for f in flags)
            ignored = self.sh.run_cmd(["git", "check-ignore", "-q", ".ddaro"], cwd=target, timeout=self.git_timeout())[0] == 0
            if all_f or (unt_f and not ignored):
                if self.norm_path(target) == self.norm_path(main):
                    self.note(main, self.msg_protected(".ddaro (git stash --all/--include-untracked in <main>)"), "protected")
        return sub in BRANCH_CHANGING

    def push(self, args_raw: list, target, main, configs: list):
        if main is None:
            return
        mode = self.mode_for(main)
        if mode == "off":
            return
        self.identified = True
        cfg = self.cfg_for(main)
        base = self.sh.base_branch(cfg)
        for c in configs:
            k = c.split("=", 1)[0].lower()
            if k.startswith(("push.", "remote.", "branch.")):
                self.note(main, self.msg_push(f"`-c {k}` changes where the push goes"), "push", mode)
                return
        args = [self.sh.strip_token(t) for t in args_raw]
        positionals = []
        delete = False
        skip_next = False
        for a in args:
            if skip_next:
                skip_next = False
                continue
            if a in ("--all", "--mirror"):
                self.note(main, self.msg_push(f"`{a}` includes {base}"), "push", mode)
                return
            if a in ("--delete", "-d"):
                delete = True
                continue
            if a.startswith("-"):
                if a in ("-o", "--push-option", "--receive-pack", "--exec", "--repo"):
                    skip_next = True
                continue
            positionals.append(a)
        refspecs = positionals[1:]
        if delete:
            for r in refspecs:
                dst = self._dst(r)
                if dst == base or "*" in dst:
                    self.note(main, self.msg_push(f"deletes {base}"), "push", mode)
                    return
            return
        if refspecs:
            pairs = []
            for r in refspecs:
                dst = self._dst(r)
                if "*" in r:
                    self.note(main, self.msg_push(f"wildcard refspec `{r}` may include {base}"), "push", mode)
                    return
                if dst == base:
                    self.note(main, self.msg_push(f"refspec `{r}` targets {base}"), "push", mode)
                    return
                if dst in ("HEAD", "@"):
                    cur = self.sh.git_out(["symbolic-ref", "--short", "-q", "HEAD"], target, timeout=self.git_timeout())
                    if cur == base:
                        self.note(main, self.msg_push(f"HEAD is {base}"), "push", mode)
                        return
                    pairs.append((r, cur))
                else:
                    pairs.append((r, dst))
            for r, branch in pairs:
                if self.auto_merge_guard(main, target, branch, r, mode):
                    return
            return
        # implied target
        gcfg = []
        for c in configs:
            gcfg += ["-c", c]
        cur = self.sh.git_out(gcfg + ["symbolic-ref", "--short", "-q", "HEAD"], target, timeout=self.git_timeout())
        if cur == base:
            self.note(main, self.msg_push(f"current branch is {base}"), "push", mode)
            return
        pd = (self.sh.git_out(gcfg + ["config", "--get", "push.default"], target, timeout=self.git_timeout()) or "").strip().lower()
        if pd == "matching":
            self.note(main, self.msg_push("push.default=matching pushes every matching branch, including the base"), "push", mode)
            return
        upstream = self.sh.git_out(gcfg + ["rev-parse", "--abbrev-ref", "@{push}"], target, timeout=self.git_timeout())
        if upstream and upstream.split("/", 1)[-1] == base:
            self.note(main, self.msg_push(f"@{{push}} is {upstream}"), "push", mode)
            return
        self.auto_merge_guard(main, target, cur, "HEAD", mode)

    @staticmethod
    def _dst(refspec: str) -> str:
        r = refspec.lstrip("+")
        dst = r.split(":", 1)[1] if ":" in r else r
        if dst.startswith("refs/heads/"):
            dst = dst[len("refs/heads/"):]
        return dst

    def auto_merge_guard(self, main, target, branch, src_spec: str, mode: str) -> bool:
        """True when a finding was raised."""
        if not branch:
            return False
        self.check_deadline()
        data, err = self.gate().gh_json(["pr", "list", "--head", branch, "--state", "open", "--json", "number,autoMergeRequest"],
                                        main, timeout=self.gh_timeout())
        if err:
            self.findings.append(Finding("warn", f"[ddaro] merge_gate: auto-merge state of {branch} unknown ({err}); push allowed (known gap)", "automerge_unknown"))
            return False
        prs = [p for p in (data or []) if isinstance(p, dict) and p.get("autoMergeRequest")]
        if not prs:
            return False
        src = src_spec.lstrip("+").split(":", 1)[0] or "HEAD"
        sha = self.sh.git_out(["rev-parse", "--verify", "--quiet", f"{src}^{{commit}}"], target, timeout=self.git_timeout())
        repo = self.gate().Repo(main, timeout=self.git_timeout())
        st = self.gate().compute_status(main, branch, sha, repo=repo, deadline=self.check_deadline)
        if not st.get("mergeable"):
            self.note(main, f"[ddaro] merge_gate: PR #{prs[0].get('number')} on {branch} has auto-merge on and {(sha or '?')[:7]} "
                            f"is not mergeable ({st.get('reason')}). A push would merge it.\n  next: {st.get('next')} "
                            f"(or a person turns auto-merge off)", "push", mode)
            return True
        return False

    # --- gh
    def gh_alias(self, name: str, main) -> str:
        if self._gh_alias_cache is None:
            self._gh_alias_cache = {}
            import shutil
            gh = shutil.which("gh")
            if gh:
                rc, out, _ = self.sh.run_cmd([gh, "alias", "list"], cwd=main, timeout=self.gh_timeout())
                if rc == 0:
                    for line in out.splitlines():
                        k, sep, v = line.partition(":")
                        if sep:
                            self._gh_alias_cache[k.strip()] = v.strip()
        return self._gh_alias_cache.get(name, "")

    def gh_invocation(self, toks: list, i: int, seg_cwd, branch_changing_before: bool):
        args = toks[i + 1:]
        if not args:
            return
        main, st = self.main_of(seg_cwd)
        if main is None:
            main = self.main_or_refuse(seg_cwd, "gh " + " ".join(args[:2]))
            if main is None:
                return
        first = args[0]
        if first == "alias" and len(args) > 1 and args[1] in ("set", "import"):
            self.note(main, self.msg_human(f"gh alias {args[1]}"), "alias")
            return
        if first not in GH_COMMANDS and not first.startswith("-") and self.mode_for(main) != "off":
            expansion = self.gh_alias(first, main)
            if expansion.startswith("!"):
                self.note(main, self.msg_human(f"gh alias `{first}` runs a shell command"), "alias")
                return
            if not expansion:
                self.note(main, self.msg_human(f"gh `{first}` is not a gh command and no alias resolves it"), "alias")
                return
            if expansion:
                try:
                    exp = self.sh._tokenize(expansion)
                except Exception:
                    exp = expansion.split()
                args = exp + args[1:]
                first = args[0] if args else ""
        if first == "api":
            self.gh_api(args[1:], main)
            return
        if first == "pr" and len(args) > 1 and args[1] == "merge":
            self.gh_pr_merge(args[2:], main, branch_changing_before, seg_cwd)

    def gh_api(self, args: list, main):
        value_flags = {"-H", "--header", "-p", "--preview", "-q", "--jq", "-t", "--template", "--hostname", "--cache",
                       "-X", "--method", "-f", "-F", "--field", "--raw-field", "--input"}
        positional = []
        k = 0
        while k < len(args):
            a = args[k]
            if a in value_flags and k + 1 < len(args):
                k += 2
                continue
            if not a.startswith("-"):
                positional.append(a)
            k += 1
        file_body = False
        values = []
        method = "GET"
        explicit_get = False
        j = 0
        while j < len(args):
            a = args[j]
            if a == "--input" and j + 1 < len(args):
                file_body = True
                j += 2
                continue
            if a.startswith("--input="):
                file_body = True
            elif a in ("-X", "--method") and j + 1 < len(args):
                method = args[j + 1].upper()
                explicit_get = method == "GET"
                j += 2
                continue
            elif a.startswith("--method="):
                method = a.split("=", 1)[1].upper()
                explicit_get = method == "GET"
            elif re.match(r"^-[a-zA-Z]*X", a) and not a.startswith("--"):
                tail = a[a.index("X") + 1:]
                if tail:
                    method = tail.upper()
                elif j + 1 < len(args):
                    method = args[j + 1].upper()
                    j += 1
                explicit_get = method == "GET"
            elif a in ("--field", "--raw-field") or re.fullmatch(r"-[a-zA-Z]*[fF]", a):
                if j + 1 < len(args):
                    values.append(args[j + 1])
                    j += 2
                    continue
            elif a.startswith(("--field=", "--raw-field=")):
                values.append(a.split("=", 1)[1])
            elif re.match(r"^-[a-zA-Z]*?[fF].", a) and not a.startswith("--"):
                k = re.match(r"^-[a-zA-Z]*?([fF])", a).start(1)
                values.append(a[k + 1:])
            j += 1
        if any(v.split("=", 1)[-1].startswith("@") for v in values):
            file_body = True
        if positional and positional[0] == "graphql" and method == "GET":
            inline = [v.split("=", 1)[1] for v in values if v.startswith("query=") and not v.split("=", 1)[1].startswith("@")]
            if file_body or not inline or any(re.search(r"\bmutation\b|[$`]", q) for q in inline):
                self.note(main, self.msg_human("gh api graphql with a mutation, or a body the gate cannot read"), "api")
            return
        has_field = bool(values) or file_body
        body_mutation = any(re.search(r"\bmutation\b", a) for a in args)
        if (method != "GET") or (has_field and not explicit_get) or body_mutation or file_body:
            self.note(main, self.msg_human("gh api (not a GET)"), "api")

    def gh_pr_merge(self, args: list, main, branch_changing_before: bool, seg_cwd=None):
        mode = self.mode_for(main)
        if mode == "off":
            return
        self.identified = True
        selector = None
        repo_flag = None
        match_head = None
        auto = False
        method_flags = []
        value_flags = {"-t", "--subject", "-b", "--body", "-F", "--body-file", "-A", "--author-email"}
        j = 0
        while j < len(args):
            a = args[j]
            if a in ("-R", "--repo") and j + 1 < len(args):
                repo_flag = args[j + 1]
                j += 2
                continue
            if a.startswith("--repo="):
                repo_flag = a.split("=", 1)[1]
            elif a == "--match-head-commit" and j + 1 < len(args):
                match_head = args[j + 1]
                j += 2
                continue
            elif a.startswith("--match-head-commit="):
                match_head = a.split("=", 1)[1]
            elif a == "--auto":
                auto = True
            elif a in ("--merge", "--squash", "--rebase", "-m", "-s", "-r"):
                method_flags.append(a)
            elif a in value_flags and j + 1 < len(args):
                j += 2
                continue
            elif not a.startswith("-") and selector is None:
                selector = a
            j += 1
        if repo_flag and self.repo_slug(repo_flag) != self.origin_slug(main):
            return                       # another repository: not this gate's business
        if selector and "://" in selector and self.repo_slug(selector.split("/pull/")[0]) != self.origin_slug(main):
            return
        if auto:
            self.note(main, "[ddaro] merge_gate: `gh pr merge --auto` is a person's call.\n  run it yourself: ! gh pr merge <N> --auto ...", "merge", mode)
            return
        if branch_changing_before:
            self.note(main, "[ddaro] merge_gate: 머지는 따로 실행 - a branch-changing git command precedes `gh pr merge` in the same line.\n  run the push/commit first, then `gh pr merge` as its own command", "merge", mode)
            return
        self.check_deadline()
        view_cwd = seg_cwd if (seg_cwd is not None and self.Path(seg_cwd).is_dir()) else main
        view_args = ["pr", "view"] + ([selector] if selector else []) + (["-R", repo_flag] if repo_flag else []) + \
                    ["--json", "headRefName,headRefOid,baseRefName,state,files,changedFiles"]
        data, err = self.gate().gh_json(view_args, view_cwd, timeout=self.gh_timeout())
        if err or not isinstance(data, dict):
            self.note(main, f"[ddaro] merge_gate: could not read the PR ({err or 'no data'}); merge refused.\n  next: check `gh auth status` / network, then retry", "merge", mode)
            return
        head_oid = str(data.get("headRefOid") or "")
        head_branch = str(data.get("headRefName") or "")
        sel = selector or data.get("number") or ""
        if data.get("state") == "MERGED":
            return
        if not match_head or match_head.lower() != head_oid.lower():
            fixed = f"gh pr merge {sel} {' '.join(method_flags) or '--squash'} --delete-branch=false --match-head-commit {head_oid}"
            self.note(main, f"[ddaro] merge_gate: gh pr merge needs --match-head-commit.\n  run instead: {fixed}\n"
                            "  (text inside a PR body or commit message? write it to a file and pass --body-file / git commit -F)", "merge", mode)
            return
        repo = self.gate().Repo(main, timeout=self.git_timeout())
        self.check_deadline()
        if not repo.has_commit(head_oid):
            self.note(main, f"[ddaro] merge_gate: PR head {head_oid[:7]} is not local.\n  next: git fetch origin {head_branch} {self.sh.base_branch(self.cfg_for(main))} then retry", "merge", mode)
            return
        files = [f.get("path") for f in (data.get("files") or []) if isinstance(f, dict) and f.get("path")]
        local_head = repo.rev(f"refs/heads/{head_branch}")
        st = self.gate().compute_status(main, head_branch, head_oid, repo=repo, pr_files=files,
                                        pr_changed_files=data.get("changedFiles"), local_head=local_head,
                                        deadline=self.check_deadline)
        if st.get("mergeable"):
            if st.get("questions"):
                self.findings.append(Finding("warn", "[ddaro] merge_gate: 확인되지 않은 의심 " + str(len(st["questions"])) + "건 (not blocking):\n  " + "\n  ".join(st["questions"]), "questions"))
            return
        lines = [f"[ddaro] merge_gate: {head_branch} has no PASS for {head_oid[:7]} ({st.get('reason')})."]
        lj = st.get("last_judged")
        if lj:
            lines.append(f"  last judged: run {lj['run']} {lj['outcome']} @ {(lj.get('head') or '?')[:7]}")
        if st.get("since"):
            lines.append("  since then: " + ", ".join(f"{x['file']} ({x['kind']})" for x in st["since"][:8]) + " -> re-check required")
        if st.get("open_blockers"):
            lines.append(f"  open blockers: {len(st['open_blockers'])}")
        lines.append(f"  next: {st.get('next') or '/ddaro check'}")
        self.note(main, "\n".join(lines), "merge", mode)

    # --- gate.py / config_tool.py (L11)
    def script_invocation(self, script: str, toks: list, i: int, seg_cwd):
        args = toks[i + 1:]
        if not args:
            return
        sub = args[0]
        main_arg = args[1] if len(args) > 1 else None
        unresolvable = main_arg is None or "$" in main_arg or "`" in main_arg
        person_only = (script == "gate.py" and (sub in ("approve", "reset") or (sub == "close" and "--merged" not in args))) or \
                      (script == "config_tool.py" and sub in ("set", "init"))
        if unresolvable:
            main, st = self.main_of(seg_cwd)
            if main is None:
                main, st = self.main_of(self.payload_cwd)
            if main is None:
                if person_only:
                    mode = _any_gated(self.payload)
                    if mode != "off":
                        self.identified = True
                        self.findings.append(Finding(mode, self.msg_human(f"{script} {sub} (its <main> argument could not be resolved)"), "human"))
                return
        else:
            p = self.Path(self.sh.native_path(main_arg))
            if not p.is_absolute():
                p = self.Path(seg_cwd) / p
            main, st = self.main_of(p)
            if main is None:
                main = p
        if script == "gate.py":
            if sub in ("approve", "reset"):
                self.note(main, self.msg_human(f"gate.py {sub}"), "human")
            elif sub == "close" and "--merged" not in args:
                self.note(main, self.msg_human("gate.py close (without --merged)"), "human")
            return
        # config_tool.py
        if sub == "init":
            if (self.Path(main) / ".ddaro" / "config.json").exists():
                self.note(main, self.msg_human("config_tool.py init where a config exists"), "human")
                return
            marker = self.sh.gate_marker_path(main)
            if marker is not None and marker.exists():
                pairs = dict(a.split("=", 1) for a in args[2:] if "=" in a)
                recorded = "strict"
                try:
                    recorded = marker.read_text(encoding="utf-8").strip().split("=", 1)[1].strip() or "strict"
                except Exception:
                    pass
                if self.ct.is_weakening("merge_gate", recorded, pairs.get("merge_gate", "off")) or \
                        any(k in pairs for k in ("gate_block_severity", "gate_verify", "base_branch", "planning_patterns")):
                    self.note(main, self.msg_weaken(["init while the gate marker is present"]), "weaken", "strict")
            return
        if sub == "set" and len(args) >= 4:
            key, value = args[2], args[3]
            cfg = self.cfg_for(main)
            if key in ("merge_gate", "gate_block_severity", "gate_verify", "base_branch", "planning_patterns"):
                default = self.ct.GATE_KEYS.get(key, (None,))[0]
                old = cfg.get(key, default)
                new = value
                if key == "planning_patterns":
                    try:
                        new = json.loads(value)
                    except Exception:
                        new = [value]
                if self.ct.is_weakening(key, old, new) or (key in self.ct.GATE_KEYS and value not in self.ct.GATE_KEYS[key]):
                    self.note(main, self.msg_weaken([key]), "weaken")

    # --- shell writes (L11)
    def shell_writes(self, text: str, toks: list, seg_cwd):
        targets = []
        for k, t in enumerate(toks):
            m = re.match(r"^(\d*)(>>?|&>)(.*)$", t)
            if m:
                if m.group(3):
                    targets.append(m.group(3))
                elif k + 1 < len(toks):
                    targets.append(toks[k + 1])
        if not toks:
            return
        head = toks[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
        pos = [t for t in toks[1:] if not t.startswith("-")]
        tdir = None
        for k, t in enumerate(toks[1:], 1):
            if t in ("-t", "--target-directory") and k + 1 < len(toks):
                tdir = toks[k + 1]
            elif t.startswith("--target-directory="):
                tdir = t.split("=", 1)[1]
            elif t.startswith("-t") and len(t) > 2 and not t.startswith("--"):
                tdir = t[2:]
        if head == "tee":
            targets += pos
        elif head == "sed" and any(t == "-i" or t.startswith("-i") or t.startswith("--in-place") for t in toks[1:]):
            targets += pos[1:] if len(pos) > 1 else pos
        elif head in ("truncate", "dd", "install", "rsync"):
            targets += pos
            targets += [t.split("=", 1)[1] for t in toks[1:] if t.startswith("of=")]
        elif head in ("cp", "mv") and (len(pos) >= 2 or tdir):
            if tdir:
                targets.append(tdir)
                targets += pos
            else:
                targets.append(pos[-1])
                if head == "mv":
                    targets += pos[:-1]
        elif head in ("rm", "rmdir", "unlink", "shred"):
            targets += pos
        elif head == "perl" and any(t.startswith("-") and "i" in t and "e" in t for t in toks[1:]):
            targets += pos
        elif (re.fullmatch(r"(python(\d(\.\d+)?)?|py|pypy3?|node|nodejs|deno|bun)(\.exe)?", head) or head in ("uv", "poetry", "npx")) and \
                re.search(r"open\(|writeFile|createWriteStream|unlink|rename|rmSync|rm\(|os\.remove|os\.replace|write_text|write_bytes|shutil\.|\.replace\(|copyFile|mkdir|rmdir", getattr(self, "_cmd", text)):
            targets += re.findall(r"""['"]([^'"]*(?:\.ddaro|ddaro-gate)[^'"]*)['"]""", getattr(self, "_cmd", text), flags=re.I)
        for t in targets:
            self.protected_write(t, seg_cwd)

    def protected_write(self, raw: str, seg_cwd):
        low = raw.replace("\\", "/").lower()
        has_glob = bool(re.search(r"[*?\[{]", raw))
        if has_glob:
            # judge every expansion (plus the literal) so `.ddar[o]/gates/x` or `ddaro-gat[e]` cannot hide
            import glob as _glob
            try:
                pat = self.sh.native_path(raw)
                if not self.Path(pat).is_absolute():
                    pat = str(self.Path(seg_cwd) / pat)
                matches = _glob.glob(pat, recursive=True)[:200]
            except Exception:
                matches = []
            for m in matches:
                self.protected_write_literal(m, seg_cwd, from_glob=True)
            if not (".ddaro" in low or "ddaro-gate" in low or "/.git/" in low or matches):
                return
        elif ".ddaro" not in low and "ddaro-gate" not in low and not low.endswith(("/.git/config", "/.gitconfig", "/config.yml")):
            return
        self.protected_write_literal(raw, seg_cwd, from_glob=False, has_glob=has_glob)

    def protected_write_literal(self, raw: str, seg_cwd, from_glob: bool = False, has_glob: bool = False):
        p = self.Path(self.sh.native_path(raw))
        if not p.is_absolute():
            p = self.Path(seg_cwd) / p
        probe = p
        if has_glob:
            keep = []
            for part in p.as_posix().split("/"):
                if re.search(r"[*?\[{]", part):
                    break
                keep.append(part)
            probe = self.Path("/".join(keep)) if keep else self.Path(seg_cwd)
        norm = self.norm_path(p)
        main, st = self.main_of(probe if probe.is_dir() else probe.parent)
        if main is None and has_glob:
            main, st = self.main_of(p.parent)
        if main is None:
            tail_global = norm.endswith(("/.gitconfig", "/.config/git/config", "/config.yml"))
            if tail_global:
                main = self.main_or_refuse(self.payload_cwd, f"write to {raw}")
                if main is not None and norm in self.protected_paths(main):
                    self.note(main, self.msg_protected(p.name), "protected")
                return
            if st == "git_failed":
                self.main_or_refuse(probe, f"write to {raw}")
            return
        if norm in self.protected_paths(main):
            self.note(main, self.msg_protected(p.name), "protected")
            return
        common = self.sh.gate_marker_path(main)
        if common is not None and (norm == self.norm_path(common.parent) or norm.startswith(self.norm_path(common.parent) + "/")):
            self.note(main, self.msg_protected(f"{p.name} (inside the git common dir)"), "protected")
            return
        main_n = self.norm_path(main)
        if not norm.startswith(main_n + "/"):
            if re.search(r"(^|/)\.ddaro/config\.json$", norm):
                self.note(main, self.msg_outside_config(p), "config_outside")
            return
        rel = norm[len(main_n) + 1:]
        if rel.startswith(".ddaro") and (has_glob or from_glob):
            self.note(main, self.msg_protected(f"{rel} (a glob under .ddaro)"), "protected")
            return
        if rel in (".ddaro", ".ddaro/config.json", ".ddaro/verify.json") or rel.startswith(".ddaro/gates") \
                or re.match(r"^\.ddaro/runs/[^/]+/[^/]+/(prism-report\.json|prism-run\.json)$", rel):
            self.note(main, self.msg_protected(rel), "protected")

    # --- messages
    @staticmethod
    def msg_human(what: str) -> str:
        return (f"[ddaro] merge_gate: `{what}` is a person's command.\n"
                "  run it yourself from the prompt: ! <the same command>")

    @staticmethod
    def msg_weaken(keys: list) -> str:
        return (f"[ddaro] merge_gate: this change weakens the gate ({', '.join(keys)}).\n"
                "  a person does it: ! python <plugin>/hooks/config_tool.py set <main> <key> <value>")

    @staticmethod
    def msg_protected(rel: str) -> str:
        return (f"[ddaro] merge_gate: `{rel}` is written only by ddaro's scripts.\n"
                "  to read it use `cat` or the Read tool; to change gate state a person runs the gate.py command with `!`")

    @staticmethod
    def msg_outside_config(p) -> str:
        return (f"[ddaro] merge_gate: a `.ddaro/config.json` outside <main> ({p}) would shadow the gate settings.\n"
                "  the gate reads <main>/.ddaro/config.json only; a person edits that one")

    @staticmethod
    def msg_push(why: str) -> str:
        return (f"[ddaro] merge_gate: push to the base branch refused ({why}).\n"
                "  push your work branch and run /ddaro merge; a person pushes to the base with `!`")


def _emit(findings: list) -> int:
    strict = [f for f in findings if f.mode == "strict"]
    if strict:
        print("\n".join(f.message for f in strict), file=sys.stderr)
        return 2
    if findings:
        ctx = "\n".join(("[warn] " if f.mode == "warn" and f.kind not in ("questions", "automerge_unknown") else "") + f.message for f in findings)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": ctx}}))
    return 0


FALLBACK_MSG = ("[ddaro] merge_gate: could not parse this command and it looks like a gate target (merge / push / gate script / .ddaro write).\n"
                "  split it into plain commands, or a person runs it with `!`")


def _fallback(payload) -> int:
    """L9: parsing failed before identification. Raw regexes decide (stdlib
    only); strict / warn come from the filesystem-only lookup."""
    try:
        ti = payload.get("tool_input") or {}
        tool = payload.get("tool_name") or ""
        text = str(ti.get("command") or "") if tool == "Bash" else str(ti.get("file_path") or ti.get("notebook_path") or "")
        hit = bool(RAW_GH_RE.search(text) or RAW_PUSH_RE.search(text) or RAW_SCRIPT_RE.search(text))
        if not hit:
            return 0
    except Exception:
        return 0
    try:
        mode = _any_gated(payload)
    except Exception:
        mode = "strict"
    if mode == "strict":
        print(FALLBACK_MSG, file=sys.stderr)
        return 2
    if mode == "warn":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "[warn] " + FALLBACK_MSG}}))
    return 0


def main() -> int:
    payload = _read_payload()
    if _fast_reject(payload):
        return 0
    for stream in (sys.stdout, sys.stderr):      # Claude Code decodes hook output as UTF-8
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        if _any_gated(payload) == "off":
            return 0                              # no gated repository near this command: no subprocess, no imports
    except Exception:
        pass                                      # could not tell: the slow path decides
    try:
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        guard = Guard(payload)
    except Exception:
        return _fallback(payload)
    try:
        guard.run()
    except Exception as e:  # ImportError, TimeoutError, anything: strict blocks once identified (L9)
        if guard.identified:
            msgs = [f.message for f in guard.findings if f.mode == "strict"]
            msgs.append(f"[ddaro] merge_gate: guard failed after identifying a gate target ({type(e).__name__}: {e}); refused.\n"
                        "  a person can run the command with `!`")
            print("\n".join(msgs), file=sys.stderr)
            return 2
        return _fallback(payload)
    return _emit(guard.findings)


if __name__ == "__main__":
    sys.exit(main())
