#!/usr/bin/env python3
"""ddaro PreToolUse hook: the merge gate guard (0.10.0, merge-gate.md L8-L13).

Registered once for `Bash|Edit|Write|NotebookEdit`. With `merge_gate: off`
(the default) it changes nothing. In `warn` it lets every command run and adds
an `additionalContext` warning for the model. In `strict` it blocks (exit 2):

- `gh pr merge` without `--match-head-commit <PR head>`; with it, when that
  head has no PASS (`gate.status`), unless the PR is docs-only or a person
  approved the commit. `--auto`, a merge chained after a branch-changing git
  command, and a PR head that is not local are blocked too.
- `gh api` that is not a GET; `gh alias set|import`; git aliases (`-c alias.*`,
  `config alias.*`).
- `git push` to the base branch (explicit refspec, `--all`, `--mirror`,
  `--delete`, or an implied target), `-c push.*|remote.*|branch.*`, and a push
  to a branch whose open PR has auto-merge on while the pushed commit is not
  mergeable.
- Human-only commands: `gate.py approve|reset`, `gate.py close` without
  `--merged`, a weakening `config_tool.py set`, `config_tool.py init` where a
  config exists.
- Writes (Edit/Write/NotebookEdit and shell write targets: redirects, tee,
  sed -i, truncate, cp/mv destinations, rm/mv sources, python/node write
  opens, `git clean -x`) to `<main>/.ddaro/config.json` when weakening,
  `.ddaro/gates/**`, `.ddaro/verify.json`, a run folder's `prism-report.json`
  / `prism-run.json`, the `.ddaro` folder itself, or a `.ddaro/config.json`
  outside `<main>`.

Gate settings are read from `<main>/.ddaro/config.json` only (`<main>` =
parent of `git rev-parse --git-common-dir`, resolved per segment after cd /
`-C`); a nearer config is ignored (L10). A `<main>` whose config is unparseable,
or which has the `ddaro-gate` marker but no config, counts as strict (L9).

Fast path: stdlib only, `tool_input.command` must contain `git`, `gh`,
`gate.py`, `config_tool.py` or `.ddaro` as a word; Edit/Write paths must
contain `.ddaro`. Everything else exits before importing anything heavy. Once
a command is identified as a gate target, any exception (ImportError included)
blocks in strict (L9); an exception before identification falls back to the
raw-text regexes.

The hook never prints `permissionDecision` (allow would skip the user's own
permission prompt). Known gaps are listed in the design document's threat
model: commands inside scripts / `bash -c` / `eval` / command substitution,
the user's own terminal and `!` commands, hooks that cannot run.
"""

from __future__ import annotations

import json
import re
import sys

# --- fast path (stdlib only) ------------------------------------------------

_WORD = r"(?<![A-Za-z0-9_\-])(?:{})(?![A-Za-z0-9_\-])"
FAST_RE = re.compile(_WORD.format(r"git(?:\.exe)?|gh(?:\.exe)?|gate\.py|config_tool\.py|\.ddaro"), re.I)
RAW_GH_RE = re.compile(r"\bgh(\.exe)?\b.*\b(pr\s+merge|api)\b", re.S)
RAW_PUSH_RE = re.compile(r"\bgit(\.exe)?\b.*\bpush\b", re.S)
RAW_SCRIPT_RE = re.compile(r"gate\.py|config_tool\.py|\.ddaro[/\\]")


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
        return not (isinstance(cmd, str) and FAST_RE.search(cmd))
    if tool in ("Edit", "Write", "NotebookEdit"):
        p = ti.get("file_path") or ti.get("notebook_path") or ""
        return ".ddaro" not in str(p)
    return True


# --- slow path --------------------------------------------------------------

HOOK_DEADLINE = 20.0
GH_TIMEOUT = 10
BUILTIN_GIT = {
    "add", "am", "annotate", "apply", "archive", "bisect", "blame", "branch", "bundle", "cat-file", "checkout",
    "cherry", "cherry-pick", "clean", "clone", "commit", "commit-graph", "config", "describe", "diff", "difftool",
    "fetch", "format-patch", "fsck", "gc", "grep", "init", "log", "ls-files", "ls-remote", "ls-tree", "merge",
    "merge-base", "merge-tree", "mv", "notes", "pull", "push", "range-diff", "rebase", "reflog", "remote",
    "repack", "replace", "reset", "restore", "rev-list", "rev-parse", "revert", "rm", "shortlog", "show",
    "show-ref", "sparse-checkout", "stash", "status", "submodule", "switch", "symbolic-ref", "tag", "update-ref",
    "whatchanged", "worktree", "for-each-ref", "name-rev", "var", "version", "help",
}
BRANCH_CHANGING = {"push", "commit", "merge", "rebase", "reset", "cherry-pick", "am"}


class Finding:
    def __init__(self, mode: str, message: str, kind: str):
        self.mode = mode          # strict | warn
        self.message = message
        self.kind = kind


class Guard:
    def __init__(self, payload: dict):
        import os
        import time
        from pathlib import Path
        import _shared as sh
        import config_tool as ct
        self.os, self.time, self.Path, self.sh, self.ct = os, time, Path, sh, ct
        self.payload = payload
        self.started = time.monotonic()
        self.findings: list = []
        self.identified = False
        self._mode_cache: dict = {}
        self._gate_mod = None

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

    def main_of(self, path):
        try:
            return self.sh.main_root_of(self.Path(path))
        except Exception:
            return None

    def mode_for(self, main) -> str:
        """off | warn | strict for `<main>` (L9/L10)."""
        if main is None:
            return "off"
        key = str(main)
        if key in self._mode_cache:
            return self._mode_cache[key]
        cfg, st = self.sh.load_main_config_status(main)
        if st == "ok":
            mode = self.sh.gate_mode(cfg)
        elif st == "unparseable":
            mode = "strict"
        else:
            marker = self.sh.gate_marker_path(main)
            mode = "strict" if (marker is not None and marker.exists()) else "off"
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
        url = self.sh.git_out(["remote", "get-url", "origin"], main, timeout=5) or ""
        return self.repo_slug(url)

    @staticmethod
    def repo_slug(s: str) -> str:
        s = s.strip().lower()
        s = re.sub(r"^[a-z]+://", "", s)
        s = re.sub(r"^[^@/]+@", "", s)       # git@host:
        s = s.replace(":", "/")
        s = re.sub(r"\.git$", "", s.rstrip("/"))
        parts = [p for p in s.split("/") if p]
        if len(parts) >= 2 and "." in parts[0] and len(parts) >= 3:
            parts = parts[1:]                # drop the host
        return "/".join(parts[-2:]) if len(parts) >= 2 else s

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
        main = self.main_of(tp.parent if tp.suffix or not tp.exists() else tp)
        if main is None:
            return
        mode = self.mode_for(main)
        if mode == "off":
            return
        main_n = self.norm_path(main)
        rel = norm[len(main_n) + 1:] if norm.startswith(main_n + "/") else None
        if rel is None:
            if re.search(r"(^|/)\.ddaro/config\.json$", norm):
                self.note(main, self.msg_outside_config(tp), "config_outside")
            return
        if rel == ".ddaro/config.json":
            self.identified = True
            new_text = None
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
            if new_text is not None:
                try:
                    old_cfg = json.loads(cur) if cur.strip() else {}
                except Exception:
                    old_cfg = {}
                try:
                    new_cfg = json.loads(new_text)
                except Exception:
                    new_cfg = None
                if isinstance(new_cfg, dict) and isinstance(old_cfg, dict):
                    weak = self.ct.weakening_changes(old_cfg, new_cfg)
                    if weak:
                        self.note(main, self.msg_weaken(weak), "weaken")
            return
        if rel.startswith(".ddaro/gates/") or rel == ".ddaro/verify.json":
            self.note(main, self.msg_protected(rel), "protected")
            return
        m = re.match(r"^\.ddaro/runs/[^/]+/[^/]+/(prism-report\.json|prism-run\.json)$", rel)
        if m:
            self.note(main, self.msg_protected(rel), "protected")

    # --- Bash
    def bash(self, cmd: str):
        cwd = self.sh.cwd_from_payload(self.payload)
        segments = self.sh.segments_with_cwd(cmd, cwd)
        branch_changing_before = False
        for seg in segments:
            toks = seg["tokens"]
            seg_cwd = seg["cwd"]
            stripped = [self.sh.strip_token(t) for t in toks]
            self.check_deadline()
            for i, tok in enumerate(toks):
                if self.sh.is_git_token(tok):
                    changed = self.git_invocation(toks, i, seg_cwd, seg["text"])
                    branch_changing_before = branch_changing_before or changed
                elif self.sh.is_gh_token(tok):
                    self.gh_invocation(stripped, i, seg_cwd, branch_changing_before)
                else:
                    base = self.sh.strip_token(tok).replace("\\", "/").rsplit("/", 1)[-1].lower()
                    if base in ("gate.py", "config_tool.py"):
                        self.script_invocation(base, stripped, i, seg_cwd)
            self.shell_writes(seg["text"], stripped, seg_cwd)

    # --- git (L13, L11 aliases)
    def git_invocation(self, toks: list, i: int, seg_cwd, text: str) -> bool:
        target, sub, idx, configs = self.sh.scan_git_global_opts(toks, i + 1, seg_cwd)
        main = self.main_of(target)
        for c in configs:
            if c.lower().startswith("alias."):
                self.note(main, self.msg_human(f"git alias via -c ({c.split('=')[0]})"), "alias")
        if sub is None:
            return False
        if sub == "config" and any(self.sh.strip_token(t).lower().startswith("alias.") for t in toks[idx + 1:]):
            self.note(main, self.msg_human("git config alias.*"), "alias")
            return False
        if sub not in BUILTIN_GIT and main is not None and self.mode_for(main) != "off":
            expansion = self.sh.git_out(["config", "--get", f"alias.{sub}"], target, timeout=5)
            if expansion and not expansion.startswith("!"):
                try:
                    sub = self.sh._tokenize(expansion)[0]
                except Exception:
                    pass
        if sub == "push":
            self.push(toks, idx + 1, target, main, configs)
        if sub == "clean" and main is not None:
            flags = [self.sh.strip_token(t) for t in toks[idx + 1:] if t.startswith("-")]
            if any(f in ("-x", "-X") or (f.startswith("-") and not f.startswith("--") and ("x" in f or "X" in f)) for f in flags):
                if self.norm_path(target) == self.norm_path(main):
                    self.note(main, self.msg_protected(".ddaro (git clean -x/-X in <main>)"), "protected")
        return sub in BRANCH_CHANGING

    def push(self, toks: list, start: int, target, main, configs: list):
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
        args = [self.sh.strip_token(t) for t in toks[start:]]
        opts, positionals = [], []
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
                opts.append(a)
                continue
            positionals.append(a)
        remote = positionals[0] if positionals else None
        refspecs = positionals[1:]
        if delete:
            for r in refspecs:
                if self._dst(r) == base:
                    self.note(main, self.msg_push(f"deletes {base}"), "push", mode)
                    return
            return
        if refspecs:
            pushed_branch = None
            for r in refspecs:
                dst = self._dst(r)
                if dst == base:
                    self.note(main, self.msg_push(f"refspec `{r}` targets {base}"), "push", mode)
                    return
                if dst == "HEAD" or dst == "@":
                    cur = self.sh.git_out(["symbolic-ref", "--short", "-q", "HEAD"], target, timeout=5)
                    if cur == base:
                        self.note(main, self.msg_push(f"HEAD is {base}"), "push", mode)
                        return
                    pushed_branch = cur
                else:
                    pushed_branch = dst
            self.auto_merge_guard(main, target, pushed_branch, refspecs[0], mode)
            return
        # implied target
        gcfg = []
        for c in configs:
            gcfg += ["-c", c]
        cur = self.sh.git_out(gcfg + ["symbolic-ref", "--short", "-q", "HEAD"], target, timeout=5)
        if cur == base:
            self.note(main, self.msg_push(f"current branch is {base}"), "push", mode)
            return
        pd = (self.sh.git_out(gcfg + ["config", "--get", "push.default"], target, timeout=5) or "").strip().lower()
        if pd == "matching":
            self.note(main, self.msg_push("push.default=matching pushes every matching branch, including the base"), "push", mode)
            return
        upstream = self.sh.git_out(gcfg + ["rev-parse", "--abbrev-ref", "@{push}"], target, timeout=5)
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

    def auto_merge_guard(self, main, target, branch, src_spec: str, mode: str):
        if not branch:
            return
        self.check_deadline()
        gh = self.gate().gh_json(["pr", "list", "--head", branch, "--state", "open", "--json", "number,autoMergeRequest"],
                                 main, timeout=GH_TIMEOUT)
        data, err = gh
        if err:
            self.findings.append(Finding("warn", f"[ddaro] merge_gate: auto-merge state of {branch} unknown ({err}); push allowed (known gap)", "automerge_unknown"))
            return
        prs = [p for p in (data or []) if isinstance(p, dict) and p.get("autoMergeRequest")]
        if not prs:
            return
        src = src_spec.lstrip("+").split(":", 1)[0] or "HEAD"
        sha = self.sh.git_out(["rev-parse", "--verify", "--quiet", f"{src}^{{commit}}"], target, timeout=5)
        st = self.gate().compute_status(main, branch, sha, repo=self.gate().Repo(main))
        if not st.get("mergeable"):
            self.note(main, f"[ddaro] merge_gate: PR #{prs[0].get('number')} on {branch} has auto-merge on and {(sha or '?')[:7]} "
                            f"is not mergeable ({st.get('reason')}). A push would merge it.\n  next: {st.get('next')} "
                            f"(or a person turns auto-merge off)", "push", mode)

    # --- gh
    def gh_invocation(self, toks: list, i: int, seg_cwd, branch_changing_before: bool):
        args = toks[i + 1:]
        if not args:
            return
        main = self.main_of(seg_cwd)
        if args[0] == "alias" and len(args) > 1 and args[1] in ("set", "import"):
            self.note(main, self.msg_human(f"gh alias {args[1]}"), "alias")
            return
        if args[0] == "api":
            self.gh_api(args[1:], main)
            return
        if args[0] == "pr" and len(args) > 1 and args[1] == "merge":
            self.gh_pr_merge(args[2:], main, branch_changing_before)

    def gh_api(self, args: list, main):
        if main is None:
            return
        positional = [a for a in args if not a.startswith("-")]
        if positional and positional[0] == "graphql":
            # a GraphQL query is a read; only a mutation writes
            if any(re.search(r"\bmutation\b", a) for a in args):
                self.note(main, self.msg_human("gh api graphql mutation"), "api")
            return
        method = "GET"
        has_field = False
        body_mutation = False
        explicit_get = False
        j = 0
        while j < len(args):
            a = args[j]
            if a in ("-X", "--method") and j + 1 < len(args):
                method = args[j + 1].upper()
                explicit_get = method == "GET"
                j += 2
                continue
            if a.startswith("-X") and len(a) > 2:
                method = a[2:].upper()
                explicit_get = method == "GET"
            elif a.startswith("--method="):
                method = a.split("=", 1)[1].upper()
                explicit_get = method == "GET"
            elif a in ("-f", "-F", "--field", "--raw-field", "--input") or a.startswith(("-f", "-F", "--field=", "--raw-field=", "--input=")):
                has_field = True
                if a in ("-f", "-F", "--field", "--raw-field", "--input"):
                    j += 1
            if re.search(r"\bmutation\b", a):
                body_mutation = True
            j += 1
        write = (method != "GET") or (has_field and not explicit_get) or body_mutation
        if write:
            self.note(main, self.msg_human("gh api (not a GET)"), "api")

    def gh_pr_merge(self, args: list, main, branch_changing_before: bool):
        if main is None:
            return
        mode = self.mode_for(main)
        if mode == "off":
            return
        self.identified = True
        selector = None
        repo_flag = None
        match_head = None
        auto = False
        method_flags = []
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
        view_args = ["pr", "view"] + ([selector] if selector else []) + (["-R", repo_flag] if repo_flag else []) + \
                    ["--json", "headRefName,headRefOid,baseRefName,state,files,changedFiles"]
        data, err = self.gate().gh_json(view_args, main, timeout=GH_TIMEOUT)
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
        repo = self.gate().Repo(main)
        if not repo.has_commit(head_oid):
            self.note(main, f"[ddaro] merge_gate: PR head {head_oid[:7]} is not local.\n  next: git fetch origin {head_branch} {self.sh.base_branch(self.cfg_for(main))} then retry", "merge", mode)
            return
        files = [f.get("path") for f in (data.get("files") or []) if isinstance(f, dict) and f.get("path")]
        local_head = repo.rev(f"refs/heads/{head_branch}")
        st = self.gate().compute_status(main, head_branch, head_oid, repo=repo, pr_files=files,
                                        pr_changed_files=data.get("changedFiles"), local_head=local_head)
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
        if unresolvable:
            main = self.main_of(seg_cwd)
        else:
            main = self.Path(self.sh.native_path(main_arg))
            if not main.is_absolute():
                main = self.Path(seg_cwd) / main
            main = self.main_of(main) or main
        if script == "gate.py":
            if sub in ("approve", "reset"):
                self.note(main, self.msg_human(f"gate.py {sub}"), "human")
            elif sub == "close" and "--merged" not in args:
                self.note(main, self.msg_human("gate.py close (without --merged)"), "human")
            return
        # config_tool.py
        if sub == "init":
            if main is not None and (self.Path(main) / ".ddaro" / "config.json").exists():
                self.note(main, self.msg_human("config_tool.py init where a config exists"), "human")
            return
        if sub == "set" and len(args) >= 4:
            key, value = args[2], args[3]
            if main is None:
                return
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
        if head == "tee":
            targets += pos
        elif head == "sed" and any(t == "-i" or t.startswith("-i") or t.startswith("--in-place") for t in toks[1:]):
            targets += pos[1:] if len(pos) > 1 else pos
        elif head == "truncate":
            targets += pos
        elif head in ("cp", "mv") and len(pos) >= 2:
            targets.append(pos[-1])
            if head == "mv":
                targets += pos[:-1]
        elif head in ("rm", "rmdir", "unlink"):
            targets += pos
        elif head in ("python", "python3", "py", "node") and re.search(r"""open\(|writeFile|createWriteStream|unlink|rename|rmSync|os\.remove|os\.replace""", text):
            targets += re.findall(r"""['"]([^'"]*\.ddaro[^'"]*)['"]""", text)
        for t in targets:
            self.protected_write(t, seg_cwd)

    def protected_write(self, raw: str, seg_cwd):
        if ".ddaro" not in raw.replace("\\", "/"):
            return
        p = self.Path(self.sh.native_path(raw))
        if not p.is_absolute():
            p = self.Path(seg_cwd) / p
        norm = self.norm_path(p)
        main = self.main_of(p.parent if not p.is_dir() else p)
        if main is None:
            return
        main_n = self.norm_path(main)
        if not norm.startswith(main_n + "/"):
            if re.search(r"(^|/)\.ddaro/config\.json$", norm):
                self.note(main, self.msg_outside_config(p), "config_outside")
            return
        rel = norm[len(main_n) + 1:]
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


def _fallback(payload) -> int:
    """L9: parsing failed before identification. Raw regexes decide; strict is
    judged from the cwd's <main> (and the marker file)."""
    try:
        from pathlib import Path
        import _shared as sh
        ti = payload.get("tool_input") or {}
        tool = payload.get("tool_name") or ""
        text = str(ti.get("command") or "") if tool == "Bash" else str(ti.get("file_path") or ti.get("notebook_path") or "")
        hit = bool(RAW_GH_RE.search(text) or RAW_PUSH_RE.search(text) or RAW_SCRIPT_RE.search(text))
        if not hit:
            return 0
        cwd = sh.cwd_from_payload(payload)
        main = sh.main_root_of(cwd)
        cfg, st = sh.load_main_config_status(main)
        mode = sh.gate_mode(cfg) if st == "ok" else ("strict" if st == "unparseable" else "off")
        if mode == "off" and main is not None:
            marker = sh.gate_marker_path(main)
            if marker is not None and marker.exists():
                mode = "strict"
        if mode == "strict":
            print("[ddaro] merge_gate: could not parse this command and it looks like a gate target (merge / push / gate script / .ddaro write).\n"
                  "  split it into plain commands, or a person runs it with `!`", file=sys.stderr)
            return 2
        return 0
    except Exception:
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
