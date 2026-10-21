#!/usr/bin/env python3
"""ddaro merge gate (0.10.0): the single writer of `<main>/.ddaro/gates/`.

The gate turns `/ddaro check` from a model judgement into a script judgement
and ties every PASS to a commit SHA. `/ddaro merge` and the PreToolUse hook
`check-merge-gate.py` ask this module (`status`) whether a commit may be
merged; nothing else reads or writes the state files.

    python gate.py status       <main> [--branch <b>] [--head <sha>]      read-only
    python gate.py check-begin  <wt> [--full]                              run rules
    python gate.py check-record <wt> --run <id>                            judge rules
    python gate.py close        <main> <branch> --merged --pr <N>          merge confirmation (L2)
    python gate.py retire       <main> <branch>                            after the branch is deleted
    python gate.py close        <main> <branch>                     [human] close the cycle without confirmation
    python gate.py approve      <main> <branch> --head <sha> --reason "<text>"   [human]
    python gate.py reset        <main> <branch>                     [human] move an unparseable state file aside

Every judgement exits 0 with one JSON object on stdout whose `outcome` is PASS,
BLOCK, STALE, ERROR, REFUSED or OK (L7); a non-zero exit is a script failure.
`summary` carries the lines the command file prints verbatim.

State: `<main>/.ddaro/gates/<branch_enc>.json` (schema 1). Runs and blockers
belong to a PR cycle; the cycle number only moves through the merge
confirmation (a MERGED PR on this branch whose head descends from a run of the
current cycle). Closed cycles move to `gates/archive/<branch_enc>/cycle-<n>.json`.
Writes happen under a short OS lock (`gates/<branch_enc>.lock`), re-read the
file first, go through a temp file + fsync + os.replace and leave a `.bak`.
Unknown fields are preserved.

Design: `docs/design/merge-gate.md` (v3.3; the L*, D*, rule numbers below refer
to it). Report contract: prism 0.6.0 `skills/prism/references/report-contract.md`.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from _shared import (  # noqa: E402
    base_branch,
    branch_enc,
    file_lock,
    load_main_config_status,
    main_root_of,
    parse_lock,
    prism_install_path,
    prism_report_contract,
    run_cmd,
    utf8_stdio,
)

STATE_SCHEMA = 1
CONTRACT_MAJORS = (2, 2)  # (min, max) report_contract major this gate understands
DEFECT_LENSES = ("correctness", "security", "state", "integration", "testability")
STATUSES = ("SUSPECTED", "SUPPORTED", "REPRODUCED", "REJECTED")
SEVERITIES = ("LOW", "MED", "HIGH", "CRIT")
SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}
GROUNDED = ("SUPPORTED", "REPRODUCED")
DOC_EXTS = {".md", ".mdx", ".txt", ".rst", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
# The gate's document default is NARROWER than check-main-edit's: `.claude/**` holds
# slash commands with inline `!` bash and allowed-tools, which must be reviewed.
DEFAULT_PLANNING_PATTERNS = [".planning/**", ".gsd/**", "STATE.md", "ROADMAP.md", "CHANGELOG.md"]
NEVER_DOC_PREFIXES = (".claude/", ".github/", ".ddaro/")
INDENT_SENSITIVE = {".py", ".yml", ".yaml", ".pyi", ".nim", ".coffee", ".haml", ".pug", ".sass", ".styl"}
LOCK_TIMEOUT = 5.0
VERIFY_BUDGET = 540
GH_TIMEOUT = 20
FETCH_TIMEOUT = 60
SHA40 = re.compile(r"^[0-9a-f]{40}$")
REPORT_FILE = "prism-report.json"
RUN_FILE = "prism-run.json"
BLOCKERS_FILE = "blockers.json"
MSG_PRISM_OLD = "prism 0.6.0 이상 필요"
MSG_DDARO_OLD = "ddaro를 업데이트하라"
MSG_OUT_UNKNOWN = "prism이 `--out`을 모름(0.6.0 미만이 로드됨): `claude plugin update prism` 후 세션 재시작"
MSG_CYCLE_CLOSED = "주기가 이미 닫힘"
MSG_TREE_CHANGED = "리뷰 중 트리가 바뀜"


class GateError(Exception):
    """A script failure (non-zero exit), never a judgement."""


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def posix(p) -> str:
    """`C:/...` style absolute path (Git Bash keeps forward slashes intact)."""
    return Path(p).resolve().as_posix()


def norm_claim(s) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(s or ""))).strip()


def loose(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def quote_from_evidence(ev) -> str:
    """Same rule as prism's `quoteFromEvidence`: text after an em/en dash or
    ` - `, else the whole string."""
    s = str(ev if ev is not None else "")
    m = re.search(r"[\u2014\u2013]\s*(.+)$", s) or re.search(r"\s-\s+(.+)$", s)
    return (m.group(1) if m else s).strip()


# --- git ------------------------------------------------------------------

class GitUnavailable(Exception):
    """git could not run or timed out: never a verdict on anything."""


class Repo:
    def __init__(self, root: Path, timeout: float = 30):
        self.root = Path(root)
        self.timeout = timeout

    def run(self, args, timeout=None):
        t = self.timeout if timeout is None else min(timeout, self.timeout) if self.timeout else timeout
        rc, out, err = run_cmd(["git", "-c", "core.quotepath=false", *args], cwd=self.root, timeout=t)
        if rc is None:
            raise GitUnavailable(f"git {' '.join(str(a) for a in args[:3])}: {err.strip()[-200:] or 'could not run'}")
        return rc, out, err

    def out(self, args, timeout=None) -> Optional[str]:
        rc, out, _ = self.run(args, timeout)
        return out.strip() if rc == 0 else None

    def ok(self, args, timeout=None) -> bool:
        rc, _, _ = self.run(args, timeout)
        return rc == 0

    def toplevel(self) -> Optional[Path]:
        t = self.out(["rev-parse", "--show-toplevel"])
        return Path(t) if t else None

    def rev(self, ref: str) -> Optional[str]:
        v = self.out(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
        return v if v and SHA40.match(v) else None

    def head(self) -> Optional[str]:
        return self.rev("HEAD")

    def branch(self) -> Optional[str]:
        return self.out(["symbolic-ref", "--short", "-q", "HEAD"])

    def dirty_tracked(self) -> list:
        out = self.out(["status", "--porcelain", "--untracked-files=no"])
        return [line[3:] for line in out.splitlines() if line.strip()] if out else []

    def is_ancestor(self, a: str, b: str) -> bool:
        return self.ok(["merge-base", "--is-ancestor", a, b])

    def merge_base(self, a: str, b: str) -> Optional[str]:
        return self.out(["merge-base", a, b])

    def has_commit(self, sha: str) -> bool:
        return bool(sha) and self.ok(["cat-file", "-e", f"{sha}^{{commit}}"])

    def diff_names(self, a: str, b: str, renames=False) -> Optional[list]:
        args = ["diff", "--name-only", "-M" if renames else "--no-renames", a, b]
        out = self.out(args)
        return None if out is None else [unquote_git_path(l) for l in out.splitlines() if l]

    def blob(self, sha: str, path: str) -> Optional[str]:
        return self.out(["rev-parse", "--verify", "--quiet", f"{sha}:{path}"])

    def file_lines(self, sha: str, path: str) -> Optional[list]:
        rc, out, _ = self.run(["cat-file", "blob", f"{sha}:{path}"])
        if rc != 0:
            return None
        return out.splitlines()

    def grep_symbol(self, sha: str, symbol: str) -> bool:
        rc, out, _ = self.run(["grep", "-w", "-q", "-e", symbol, sha, "--"])
        return rc == 0

    def ref_exists(self, ref: str) -> bool:
        return self.ok(["rev-parse", "--verify", "--quiet", ref])

    def base_ref(self, base: str) -> Optional[str]:
        for ref in (f"refs/remotes/origin/{base}", f"refs/heads/{base}"):
            if self.ref_exists(ref):
                return ref
        return None


def unquote_git_path(p: str) -> str:
    """Undo git's C-style path quoting (`"a/\\354\\225\\234.py"`): strip the
    quotes and decode `\\ooo` octal bytes and `\\"`, `\\\\`, `\\t`, `\\n`. The diffs
    run with `core.quotepath=false`, so this only matters for `"` and `\\`."""
    s = str(p)
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        body = s[1:-1]
        out = bytearray()
        i = 0
        while i < len(body):
            c = body[i]
            if c == "\\" and i + 1 < len(body):
                n = body[i + 1]
                if n in "01234567" and i + 3 < len(body):
                    out += bytes([int(body[i + 1:i + 4], 8)])
                    i += 4
                    continue
                out += {"n": b"\n", "t": b"\t", '"': b'"', "\\": b"\\", "r": b"\r"}.get(n, n.encode("utf-8"))
                i += 2
                continue
            out += c.encode("utf-8")
            i += 1
        return out.decode("utf-8", "replace")
    return s


# --- state ----------------------------------------------------------------

def gates_dir(main: Path) -> Path:
    return Path(main) / ".ddaro" / "gates"


def state_path(main: Path, branch: str) -> Path:
    return gates_dir(main) / f"{branch_enc(branch)}.json"


def lock_path(main: Path, branch: str) -> Path:
    return gates_dir(main) / f"{branch_enc(branch)}.lock"


def archive_dir(main: Path, branch: str) -> Path:
    return gates_dir(main) / "archive" / branch_enc(branch)


def runs_dir(main: Path, branch: str) -> Path:
    return Path(main) / ".ddaro" / "runs" / branch_enc(branch)


def new_state(branch: str) -> dict:
    return {"schema": STATE_SCHEMA, "branch": branch, "cycle": 1, "next_run": 1,
            "runs": [], "blockers": [], "approvals": [], "closes": []}


def _read_json(path: Path, retries: int = 5):
    """JSON of `path`, or raises. PermissionError (Windows: a writer is mid
    replace) is retried briefly."""
    for i in range(retries):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except PermissionError:
            if i == retries - 1:
                raise
            time.sleep(0.1)


def read_json_or_none(path: Path):
    try:
        return _read_json(path)
    except Exception:
        return None


def load_state(main: Path, branch: str):
    """(state, status). status: ok | missing | unreadable | newer. A missing
    file yields a fresh in-memory state. `branch` inside the file must match."""
    p = state_path(main, branch)
    if not p.exists():
        return new_state(branch), "missing"
    try:
        st = _read_json(p)
    except Exception:
        return None, "unreadable"
    if not isinstance(st, dict) or not isinstance(st.get("runs"), list):
        return None, "unreadable"
    try:
        schema = int(st.get("schema") or 0)
    except (TypeError, ValueError):
        schema = 0
    if schema > STATE_SCHEMA:
        return st, "newer"
    if st.get("branch") != branch:
        return st, "branch_mismatch"
    st.setdefault("blockers", [])
    st.setdefault("approvals", [])
    st.setdefault("closes", [])
    st.setdefault("next_run", 1 + max([r.get("run", 0) for r in st["runs"]] + [0]))
    return st, "ok"


def write_json_atomic(path: Path, data, keep_bak: bool = True) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if keep_bak and path.exists():
            try:
                shutil.copyfile(path, str(path) + ".bak")
            except OSError:
                pass
        for i in range(10):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if i == 9:
                    raise
                time.sleep(0.1)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_state(main: Path, branch: str, state: dict) -> None:
    if state.get("branch") != branch:
        raise GateError(f"state file branch {state.get('branch')!r} != {branch!r}; refusing to write")
    write_json_atomic(state_path(main, branch), state)


def locked(main: Path, branch: str):
    return file_lock(lock_path(main, branch), LOCK_TIMEOUT)


def archive_path(main: Path, branch: str, cycle: int) -> Path:
    return archive_dir(main, branch) / f"cycle-{cycle}.json"


# --- domain helpers -------------------------------------------------------

def cycle_runs(state: dict) -> list:
    c = state.get("cycle")
    return [r for r in state.get("runs", []) if r.get("cycle") == c]


def judged_runs(state: dict) -> list:
    return [r for r in cycle_runs(state)
            if r.get("kind") == "review" and r.get("outcome") in ("PASS", "BLOCK")]


def last_judged(state: dict) -> Optional[dict]:
    js = judged_runs(state)
    return max(js, key=lambda r: r.get("run", 0)) if js else None


def find_run(state: dict, run_no: int) -> Optional[dict]:
    for r in state.get("runs", []):
        if r.get("run") == run_no:
            return r
    return None


def open_blockers(state: dict) -> list:
    c = state.get("cycle")
    return [b for b in state.get("blockers", []) if b.get("cycle") == c and b.get("open", True)]


def blocker_public(b: dict) -> dict:
    keys = ("id", "file", "lines", "symbol", "category", "severity", "claim", "head",
            "first_run", "unverified", "needs_human")
    return {k: b.get(k) for k in keys}


def blocker_for_prism(b: dict) -> dict:
    out = {"id": b["id"], "file": b.get("file") or "", "lines": b.get("lines"), "symbol": b.get("symbol"),
           "category": b.get("category"), "severity": b.get("severity"), "claim": b.get("claim") or "",
           "evidence": list(b.get("evidence") or [])}
    if b.get("unverified"):
        out["unverified"] = True
    return out


def sev_rank(s) -> int:
    return SEV_RANK.get(str(s), -1)


def block_threshold(cfg: Optional[dict]) -> int:
    v = str((cfg or {}).get("gate_block_severity") or "MED").strip().upper()
    return SEV_RANK.get(v, SEV_RANK["MED"])


def glob_match(path: str, pattern: str) -> bool:
    """`**` any depth (incl. none), `*` within one segment, `?` one char."""
    pat = pattern.replace("\\", "/")
    if pat.startswith("./"):
        pat = pat[2:]
    rx = ""
    i = 0
    while i < len(pat):
        c = pat[i]
        if pat.startswith("**/", i):
            rx += "(?:.*/)?"
            i += 3
        elif pat.startswith("**", i):
            rx += ".*"
            i += 2
        elif c == "*":
            rx += "[^/]*"
            i += 1
        elif c == "?":
            rx += "[^/]"
            i += 1
        else:
            rx += re.escape(c)
            i += 1
    return re.fullmatch(rx, path) is not None


def planning_patterns(cfg: Optional[dict]) -> list:
    """`planning_patterns` as a list of strings; anything else (a raw JSON
    string written by an old `set`, a non-list) falls back to the default."""
    pats = (cfg or {}).get("planning_patterns")
    if isinstance(pats, list) and all(isinstance(x, str) for x in pats) and pats:
        return pats
    return DEFAULT_PLANNING_PATTERNS


def is_doc(path: str, cfg: Optional[dict]) -> bool:
    """A document: matches `planning_patterns`, has a document extension, and
    does not live under `.claude/`, `.github/` or `.ddaro/` (executable config
    for the agent or CI is never a document, whatever the patterns say)."""
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    p = p.lstrip("/")
    if Path(p).suffix.lower() not in DOC_EXTS:
        return False
    if p.startswith(NEVER_DOC_PREFIXES):
        return False
    return any(glob_match(p, pat) for pat in planning_patterns(cfg))


def relpath_in_repo(file: str, root: Path) -> str:
    f = str(file or "").replace("\\", "/")
    try:
        fp = Path(f)
        if fp.is_absolute():
            return fp.resolve().relative_to(Path(root).resolve()).as_posix()
    except Exception:
        pass
    return f.lstrip("/") if f.startswith("/") and len(f) > 1 else f


# --- prism availability (run rule 1) ---------------------------------------

def prism_check():
    """(install_path, None) or (None, REFUSED message)."""
    ip, err = prism_install_path()
    if ip is None:
        return None, f"{MSG_PRISM_OLD} ({err})"
    major, err = prism_report_contract(ip)
    if major is None:
        return None, f"{MSG_PRISM_OLD} ({err})"
    if major > CONTRACT_MAJORS[1]:
        return None, f"{MSG_DDARO_OLD} (prism report_contract {major}, ddaro supports {CONTRACT_MAJORS[1]})"
    if major < CONTRACT_MAJORS[0]:
        return None, f"{MSG_PRISM_OLD} (report_contract {major})"
    return ip, None


# --- verify (run rule 4) ---------------------------------------------------

def select_verify(main: Path, cfg: Optional[dict], changed_files: list):
    """(commands, block_reason, note). `verify.json` wins when present; else
    `gate_verify: none` lets the run through with a note; else BLOCK."""
    vj = Path(main) / ".ddaro" / "verify.json"
    if vj.is_file():
        try:
            spec = _read_json(vj)
        except Exception as e:
            return [], f"verify.json unreadable: {e}", None
        entries = spec.get("commands") if isinstance(spec, dict) else None
        default = spec.get("default") if isinstance(spec, dict) else None
        cmds = []
        unmatched = []
        for f in changed_files:
            hit = None
            for ent in entries or []:
                if isinstance(ent, dict) and ent.get("pattern") and ent.get("run") and glob_match(f, str(ent["pattern"])):
                    hit = str(ent["run"])
                    break
            if hit is None:
                unmatched.append(f)
            elif hit not in cmds:
                cmds.append(hit)
        if unmatched:
            if default:
                if str(default) not in cmds:
                    cmds.append(str(default))
            else:
                return [], "이 파일들에 맞는 명령이 없음: verify.json에 default 추가 (" + ", ".join(unmatched[:5]) + ")", None
        if not cmds:
            return [], "이 파일들에 맞는 명령이 없음: verify.json에 default 추가", None
        return cmds, None, None
    if str((cfg or {}).get("gate_verify") or "auto").strip().lower() == "none":
        return [], None, "verify: none (gate_verify none, recorded by a person)"
    return [], "테스트 명령 미설정: <main>/.ddaro/verify.json 을 만들거나 사람이 `config_tool.py set <main> gate_verify none`", None


def bash_path():
    """Absolute Git Bash on Windows (found from `git --exec-path`, never
    System32's WSL launcher), `/bin/bash` elsewhere. (path, error)."""
    if os.name != "nt":
        return "/bin/bash", None
    rc, out, _ = run_cmd(["git", "--exec-path"], timeout=10)
    if rc != 0 or not out.strip():
        return None, "git --exec-path failed"
    exec_path = Path(out.strip())
    for parent in [exec_path, *exec_path.parents]:
        for cand in (parent / "bin" / "bash.exe", parent / "usr" / "bin" / "bash.exe"):
            if cand.is_file() and "system32" not in str(cand).lower():
                return str(cand), None
    return None, "Git Bash not found next to git --exec-path"


def verify_budget() -> int:
    """540 s (L: inside the Bash tool's 600 s). `DDARO_GATE_VERIFY_BUDGET` only
    shortens it (tests); a shorter budget can only turn a run into a BLOCK."""
    try:
        v = int(os.environ.get("DDARO_GATE_VERIFY_BUDGET", "") or VERIFY_BUDGET)
        return max(1, min(v, VERIFY_BUDGET))
    except ValueError:
        return VERIFY_BUDGET


def run_verify(repo_root: Path, commands: list, budget: Optional[int] = None):
    """Run each command in Git Bash with CI=1 at the worktree root. Returns
    (results, failed_reason). A command past the shared budget is killed with
    its tree and counts as a failure ("시간 초과")."""
    sh, err = bash_path()
    if sh is None:
        return [], f"shell: {err}"
    env = dict(os.environ)
    env["CI"] = "1"
    results = []
    deadline = time.monotonic() + (budget if budget is not None else verify_budget())
    for cmd in commands:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            results.append({"cmd": cmd, "exit": None, "seconds": 0, "error": "시간 초과"})
            return results, "시간 초과"
        t0 = time.monotonic()
        rc, out, serr = run_cmd([sh, "-lc", cmd], cwd=repo_root, timeout=remaining, env=env)
        secs = round(time.monotonic() - t0, 1)
        tail = (out + serr).strip().splitlines()[-20:]
        res = {"cmd": cmd, "exit": rc, "seconds": secs, "tail": tail}
        results.append(res)
        if rc is None:
            res["error"] = "시간 초과" if "[timeout]" in serr else serr.strip()
            return results, res["error"] or "could not run"
        if rc != 0:
            return results, f"{cmd} -> exit {rc}"
    return results, None


# --- gh --------------------------------------------------------------------

def gh_json(args: list, cwd: Path, timeout: int = GH_TIMEOUT):
    """(data, None) or (None, reason)."""
    gh = shutil.which("gh")
    if not gh:
        return None, "gh not found"
    rc, out, err = run_cmd([gh, *args], cwd=cwd, timeout=timeout)
    if rc != 0:
        return None, (err.strip().splitlines() or ["gh failed"])[-1]
    try:
        return json.loads(out), None
    except Exception as e:
        return None, f"gh output not JSON: {e}"


def confirm_merged(state: dict, main: Path, repo: Repo, branch: str, base: str, pr: Optional[int] = None) -> dict:
    """L2 merge confirmation: the ONLY path that raises `cycle`. Returns
    {"closed": bool, "pr": N|None, "note": str}. Mutates `state` on success
    (archives the closed cycle's runs and blockers)."""
    if pr is not None:
        data, err = gh_json(["pr", "view", str(pr), "--json", "number,state,baseRefName,headRefName,headRefOid"], main)
        cands = [data] if data else []
    else:
        data, err = gh_json(["pr", "list", "--head", branch, "--base", base, "--state", "merged",
                             "--limit", "20", "--json", "number,state,baseRefName,headRefName,headRefOid"], main)
        cands = data if isinstance(data, list) else []
    if err:
        return {"closed": False, "pr": None, "note": f"머지 확인 못 함 ({err})"}
    closed_nums = {c.get("pr") for c in state.get("closes", [])}
    heads = [r.get("head") for r in cycle_runs(state) if r.get("head")]
    heads += [a.get("head") for a in state.get("approvals", []) if a.get("cycle") == state.get("cycle") and a.get("head")]
    fetched = 0
    notes = []
    for c in cands:
        if not isinstance(c, dict) or c.get("state") != "MERGED":
            continue
        if c.get("baseRefName") != base or c.get("headRefName") != branch:
            continue
        num = c.get("number")
        if num in closed_nums:
            continue
        pr_head = str(c.get("headRefOid") or "")
        if not SHA40.match(pr_head):
            continue
        if not repo.has_commit(pr_head):
            if fetched >= 1:
                notes.append(f"PR #{num} merged but head {pr_head[:7]} not local (one fetch per check)")
                continue
            fetched += 1
            try:
                rc, _, err = repo.run(["fetch", "origin", f"pull/{num}/head"], timeout=FETCH_TIMEOUT)
            except GitUnavailable as e:
                notes.append(f"PR #{num} merged but fetch could not run ({e})")
                continue
            if not repo.has_commit(pr_head):
                tail = (err.strip().splitlines() or ["?"])[-1]
                notes.append(f"PR #{num} merged but head {pr_head[:7]} not local after fetch (exit {rc}: {tail})")
                continue
        if any(h == pr_head or repo.is_ancestor(h, pr_head) for h in heads):
            close_cycle(state, main, branch, {"pr": num, "merged_head": pr_head, "how": "auto_detected" if pr is None else "merge_command"})
            return {"closed": True, "pr": num, "note": f"PR #{num} merged; cycle -> {state['cycle']}"}
        notes.append(f"PR #{num} merged but its head {pr_head[:7]} descends from no run of cycle {state.get('cycle')}")
    return {"closed": False, "pr": None, "note": "; ".join(notes) if notes else "merged PR not found"}


def close_cycle(state: dict, main: Path, branch: str, close_info: dict) -> None:
    """Archive the current cycle's runs and blockers, record the close, bump."""
    cyc = state["cycle"]
    runs = [r for r in state["runs"] if r.get("cycle") == cyc]
    blockers = [b for b in state.get("blockers", []) if b.get("cycle") == cyc]
    arch_p = archive_path(main, branch, cyc)
    arch = read_json_or_none(arch_p) if arch_p.exists() else None
    if not isinstance(arch, dict):
        if arch_p.exists():
            aside = arch_p.with_name(f"{arch_p.stem}.corrupt-{_dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
            try:
                os.replace(arch_p, aside)
                close_info = dict(close_info, note=f"unreadable archive moved to {aside.name}")
            except OSError:
                pass
        arch = {"branch": branch, "cycle": cyc, "runs": [], "blockers": []}
    arch["runs"] = [r for r in arch.get("runs", []) if r.get("run") not in {x.get("run") for x in runs}] + runs
    arch["blockers"] = [b for b in arch.get("blockers", []) if b.get("id") not in {x.get("id") for x in blockers}] + blockers
    arch["closed"] = dict(close_info, cycle=cyc, at=now_iso())
    write_json_atomic(arch_p, arch, keep_bak=False)
    state["runs"] = [r for r in state["runs"] if r.get("cycle") != cyc]
    state["blockers"] = [b for b in state.get("blockers", []) if b.get("cycle") != cyc]
    state["closes"].append(dict(close_info, cycle=cyc, at=now_iso()))
    state["cycle"] = cyc + 1


# --- diff analysis for rule 6 ---------------------------------------------

_LINE_COMMENT = {
    "//": {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".go",
           ".rs", ".swift", ".kt", ".kts", ".scala", ".dart", ".php", ".m", ".mm", ".groovy", ".zig"},
    "#": {".py", ".pyi", ".sh", ".bash", ".zsh", ".rb", ".pl", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf",
          ".r", ".ps1", ".nim", ".tf", ".dockerfile", ".mk", ".coffee", ".ex", ".exs", ".jl"},
    "--": {".sql", ".lua", ".hs", ".elm", ".ada"},
}


def _comment_token(ext: str) -> Optional[str]:
    ext = ext.lower()
    for tok, exts in _LINE_COMMENT.items():
        if ext in exts:
            return tok
    return None


def code_part(line: str, ext: str) -> str:
    """The code of a source line: full-line comment -> "", a trailing line
    comment (`//`, `#`, `--`, `/* */`, `<!-- -->`) and surrounding whitespace
    removed. Strings are not parsed; a `//` inside a string counts as a
    comment start, which only makes the gate stricter."""
    s = str(line).strip()
    if not s:
        return ""
    for pre in ("//", "#", "/*", "*", "--", "<!--", ";;"):
        if s.startswith(pre):
            # `*` as a comment continuation only when the line is `* ...` (not `*=`, `**`).
            if pre == "*" and (len(s) > 1 and s[1] not in " \t/"):
                continue
            if pre == "#" and ext.lower() in {".cs", ".c", ".h", ".cpp", ".hpp", ".cc", ".rs", ".swift"}:
                # `#include`, `#[derive]`, `#region` are code
                continue
            if pre == "--" and _comment_token(ext) != "--":
                continue
            return ""
    tok = _comment_token(ext)
    if tok:
        idx = s.find(tok)
        if idx > 0:
            s = s[:idx]
    s = re.sub(r"/\*.*?\*/", "", s)
    s = re.sub(r"<!--.*?-->", "", s)
    return s.strip()


def norm_code(line: str, ext: str) -> str:
    """Comparison key for a line's code: the code part, whitespace-collapsed
    and lowercased; indent-sensitive files (`.py`, `.yml`, ...) keep the
    leading indent width, so a re-indent counts as a change."""
    key = loose(code_part(line, ext))
    if ext.lower() in INDENT_SENSITIVE and key:
        raw = str(line)
        key = f"{len(raw) - len(raw.lstrip())}:{key}"
    return key


def punct_only(code: str) -> bool:
    return re.sub(r"[\s\[\]\(\)\{\};,:]", "", code) == ""


_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def diff_index(repo: Repo, old: str, new: str) -> dict:
    """Parsed `git diff -M -U0 old new`: {new_path: {"old_path", "hunks": [
    {"old_start", "old_count", "new_start", "new_count", "minus": [text],
    "plus": [(lineno, text)]}], "deleted": bool}}. Whitespace-only hunks are
    dropped (`-w`) except for indent-sensitive files, which are diffed exactly."""
    index = {}
    for ws in (True, False):
        rc, out, _ = repo.run(["diff", "-M", "-U0", "--no-color"] + (["-w"] if ws else []) + [old, new], timeout=120)
        if rc != 0:
            continue
        cur = None
        for line in out.splitlines():
            if line.startswith("diff --git "):
                cur = {"old_path": None, "new_path": None, "hunks": [], "deleted": False}
                continue
            if cur is None:
                continue
            if line.startswith("rename from "):
                cur["old_path"] = unquote_git_path(line[len("rename from "):])
            elif line.startswith("rename to "):
                cur["new_path"] = unquote_git_path(line[len("rename to "):])
            elif line.startswith("deleted file"):
                cur["deleted"] = True
            elif line.startswith("--- "):
                p = unquote_git_path(line[4:])
                if p != "/dev/null":
                    cur["old_path"] = p[2:] if p.startswith("a/") else p
            elif line.startswith("+++ "):
                p = unquote_git_path(line[4:])
                if p != "/dev/null":
                    cur["new_path"] = p[2:] if p.startswith("b/") else p
                key = cur["new_path"] or cur["old_path"]
                ext = Path(key or "").suffix.lower()
                wanted = (ext not in INDENT_SENSITIVE) if ws else (ext in INDENT_SENSITIVE)
                if wanted and key is not None:
                    index[key] = cur
                else:
                    cur = None
            elif line.startswith("@@"):
                m = _HUNK.match(line)
                if m:
                    cur["hunks"].append({"old_start": int(m.group(1)), "old_count": int(m.group(2) or 1),
                                         "new_start": int(m.group(3)), "new_count": int(m.group(4) or 1),
                                         "minus": [], "plus": []})
            elif cur["hunks"]:
                h = cur["hunks"][-1]
                if line.startswith("+") and not line.startswith("+++"):
                    h["plus"].append((h["new_start"] + len(h["plus"]), line[1:]))
                elif line.startswith("-") and not line.startswith("---"):
                    h["minus"].append(line[1:])
    return index


def entry_by_old_path(index: dict, old_path: str) -> Optional[dict]:
    for e in index.values():
        if e.get("old_path") == old_path:
            return e
    return index.get(old_path)


def parse_lines(lines) -> Optional[tuple]:
    m = re.match(r"^\s*(\d+)(?:\s*-\s*(\d+))?\s*$", str(lines or ""))
    if not m:
        return None
    a = int(m.group(1))
    b = int(m.group(2) or a)
    return (a, b)


def closing_check(repo: Repo, blocker: dict, rec: dict, run_head: str, base_fallback: str):
    """Rule 6 for a REJECTED record whose quote verified. Returns
    `fixed` | `removed` | None."""
    old = blocker.get("head") if repo.has_commit(blocker.get("head") or "") else base_fallback
    if not old or not repo.has_commit(old):
        return None
    index = diff_index(repo, old, run_head)
    ec = rec.get("_evidence_check") or {}
    rec_file = relpath_in_repo(rec.get("file") or "", repo.root)
    ext = Path(rec_file).suffix
    quote_lines = [int(x) for x in (ec.get("quote_lines") or []) if isinstance(x, int) or str(x).isdigit()]
    entry = index.get(rec_file)
    if entry and quote_lines:
        for h in entry["hunks"]:
            minus_codes = {norm_code(m, ext) for m in h["minus"]}
            for ln, text in h["plus"]:
                if ln in quote_lines:
                    cp = code_part(text, ext)
                    if cp and not punct_only(cp) and norm_code(text, ext) not in minus_codes:
                        return "fixed"
    # removed: the originally quoted line is gone from the file at run_head
    b_file = blocker.get("file") or ""
    b_ext = Path(b_file).suffix
    quotes = [loose(q) for q in (blocker.get("quotes") or []) if len(loose(q)) >= 8]
    entry = entry_by_old_path(index, b_file)
    if entry and quotes:
        new_path = entry.get("new_path") or b_file
        head_lines = None if entry.get("deleted") else repo.file_lines(run_head, new_path)
        head_codes = {norm_code(l, b_ext) for l in (head_lines or [])} - {""}
        for h in entry["hunks"]:
            for m in h["minus"]:
                cpm = norm_code(m, b_ext)
                if not cpm or not any(q in loose(m) for q in quotes):
                    continue
                if head_lines is None:
                    sym = blocker.get("symbol")
                    if sym and repo.grep_symbol(run_head, sym):
                        continue
                    return "removed"
                if cpm not in head_codes:
                    return "removed"
    return None


def shift_lines(repo: Repo, blocker: dict, run_head: str, base_fallback: str):
    """Move `blocker.lines` by the hunk offsets of its file between B.head and
    run_head. Returns (new_lines or None, inside_modified_hunk)."""
    rng = parse_lines(blocker.get("lines"))
    if not rng:
        return None, False
    old = blocker.get("head") if repo.has_commit(blocker.get("head") or "") else base_fallback
    if not old:
        return None, False
    entry = entry_by_old_path(diff_index(repo, old, run_head), blocker.get("file") or "")
    if not entry:
        return blocker.get("lines"), False
    a, b = rng
    delta = 0
    extend = 0
    for h in entry["hunks"]:
        os_, oc = h["old_start"], h["old_count"]
        o_end = os_ + max(oc, 1) - 1
        if oc == 0:
            # pure insertion after old line os_: before the range shifts it, inside extends it
            if os_ < a:
                delta += h["new_count"]
            elif os_ < b:
                extend += h["new_count"]
            continue
        if o_end < a:
            delta += h["new_count"] - oc
        elif os_ <= b and o_end >= a:
            return blocker.get("lines"), True
    na, nb = a + delta, b + delta + extend
    return (f"{na}-{nb}" if nb != na else str(na)), False


# --- report judgement (rules 1-8) -----------------------------------------

def read_report(run_dir: Path):
    p = Path(run_dir) / REPORT_FILE
    if not p.is_file():
        return None
    try:
        data = _read_json(p)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def report_sha256(run_dir: Path) -> Optional[str]:
    try:
        return hashlib.sha256((Path(run_dir) / REPORT_FILE).read_bytes()).hexdigest()
    except Exception:
        return None


def contract_major(meta: dict):
    v = meta.get("report_contract")
    if v is None:
        return None
    try:
        return int(str(v).split(".")[0])
    except (TypeError, ValueError):
        return None


def check_record_format(rec, idx: int) -> Optional[str]:
    if not isinstance(rec, dict):
        return f"레코드 형식 오류: #{idx} not an object"
    rid = rec.get("id") or rec.get("candidate_id") or f"#{idx}"
    if rec.get("status") not in STATUSES:
        return f"레코드 형식 오류: {rid} status {rec.get('status')!r}"
    if rec.get("severity") not in SEVERITIES:
        return f"레코드 형식 오류: {rid} severity {rec.get('severity')!r}"
    if rec.get("status") in GROUNDED:
        for fld in ("file", "lines", "evidence"):
            v = rec.get(fld)
            if v in (None, "", []):
                return f"레코드 형식 오류: {rid} {fld} 없음"
    if not isinstance(rec.get("candidate_id"), str) or not rec.get("candidate_id"):
        return f"레코드 형식 오류: {rid} candidate_id 없음"
    return None


def judge_report(state: dict, run: dict, report: dict, repo: Repo, cfg: Optional[dict]) -> dict:
    """Rules 3-8 against `report` for `run`. Returns a result dict; the caller
    applies `blocker_updates` / `new_blockers` to the state under the lock."""
    res = {"outcome": None, "errors": [], "new_blockers": [], "closed": [], "needs_human": [],
           "questions": [], "followups": [], "grounding": [], "lenses_completed": [],
           "blocker_updates": {}, "meta_ok": True}
    errors = res["errors"]
    meta = report.get("meta")
    findings = report.get("findings")
    if not isinstance(meta, dict):
        errors.append("meta 없음")
        meta = {}
        res["meta_ok"] = False
    if not isinstance(findings, list):
        errors.append("findings 없음")
        findings = []
        res["meta_ok"] = False

    major = contract_major(meta)
    if major is None:
        errors.append(f"{MSG_PRISM_OLD} (meta.report_contract 없음)")
    elif major > CONTRACT_MAJORS[1]:
        errors.append(f"{MSG_DDARO_OLD} (report_contract {major})")
    elif major < CONTRACT_MAJORS[0]:
        errors.append(f"{MSG_PRISM_OLD} (report_contract {major})")

    rejudge = run.get("scope") == "rejudge"
    if meta.get("run_tag") != run.get("run_tag"):
        errors.append(f"meta 불일치: run_tag {meta.get('run_tag')!r} != {run.get('run_tag')!r}")
        res["meta_ok"] = False
    if meta.get("head") != run.get("head"):
        errors.append(f"meta 불일치: head {meta.get('head')!r} != {run.get('head')!r}")
        res["meta_ok"] = False
    expected_scope = "rejudge" if rejudge else "diff"
    if meta.get("scope") != expected_scope:
        errors.append(f"meta 불일치: scope {meta.get('scope')!r} (실행 {run.get('scope')} -> {expected_scope})")
        res["meta_ok"] = False
    if rejudge:
        if meta.get("range") is not None:
            errors.append(f"meta 불일치: rejudge range {meta.get('range')!r} (null 이어야 함)")
            res["meta_ok"] = False
    elif meta.get("range") != run.get("range"):
        errors.append(f"meta 불일치: range {meta.get('range')!r} != {run.get('range')!r}")
        res["meta_ok"] = False
    if meta.get("tree_changed") is True:
        errors.append(f"{MSG_TREE_CHANGED} (meta.tree_changed)")
    if meta.get("lens_set") != "defect":
        errors.append(f"meta.lens_set {meta.get('lens_set')!r} != defect")
    if meta.get("mode") == "quick":
        errors.append("meta.mode quick")
    if meta.get("unmapped_findings"):
        errors.append(f"unmapped_findings {len(meta.get('unmapped_findings'))}")
    completed = [l for l in (meta.get("lenses_completed") or []) if isinstance(l, str)]
    res["lenses_completed"] = completed
    if not rejudge and set(completed) != set(DEFECT_LENSES):
        missing = sorted(set(DEFECT_LENSES) - set(completed))
        errors.append(f"렌즈 미완료: {len(completed)}/5 (missing {', '.join(missing) or '?'})")

    valid = []
    for i, rec in enumerate(findings):
        e = check_record_format(rec, i)
        if e:
            errors.append(e)
        else:
            valid.append(rec)
    rec_cids = [r["candidate_id"] for r in valid]
    passed_ids = list(run.get("blockers_passed") or [])
    for cid in meta.get("candidate_ids") or []:
        if isinstance(cid, str) and not cid.startswith("blocker:") and cid not in rec_cids:
            errors.append(f"후보 레코드 누락: {cid}")
    if rejudge:
        for bid in passed_ids:
            n = rec_cids.count(f"blocker:{bid}")
            if n != 1:
                errors.append(f"rejudge 대응 오류: blocker:{bid} 레코드 {n}개")
        allowed = {f"blocker:{b}" for b in passed_ids}
        for cid in rec_cids:
            if cid not in allowed:
                errors.append(f"rejudge 대응 오류: 예상 밖 레코드 {cid}")

    threshold = block_threshold(cfg)
    is_error = bool(errors)
    open_now = {b["id"]: b for b in open_blockers(state)}
    base_fallback = run.get("merge_base") or run.get("head")

    def same_key(b: dict, rec: dict) -> bool:
        return (relpath_in_repo(b.get("file") or "", repo.root) == relpath_in_repo(rec.get("file") or "", repo.root)
                and (b.get("symbol") or "") == (rec.get("symbol") or "")
                and (b.get("category") or "") == (rec.get("category") or "")
                and norm_claim(b.get("claim")) == norm_claim(rec.get("claim")))

    def rec_lines(rec: dict):
        return str(rec.get("lines")) if rec.get("lines") not in (None, "") else None

    new_counter = 0

    def make_blocker(rec: dict, unverified: bool) -> dict:
        nonlocal new_counter
        new_counter += 1
        ev = rec.get("evidence") if isinstance(rec.get("evidence"), list) else []
        return {"id": f"b{run['run']}-{new_counter}", "cycle": state["cycle"],
                "file": relpath_in_repo(rec.get("file") or "", repo.root), "lines": rec_lines(rec),
                "symbol": rec.get("symbol"), "category": rec.get("category"), "severity": rec.get("severity"),
                "claim": norm_claim(rec.get("claim")), "evidence": [str(e) for e in ev],
                "quotes": [quote_from_evidence(e) for e in ev], "head": run["head"], "first_run": run["run"],
                "unverified": unverified, "open": True, "needs_human": False, "created": now_iso()}

    # Findings (non-blocker records): rules 4, 5, 8.
    if res["meta_ok"]:
        for rec in valid:
            cid = rec["candidate_id"]
            if cid.startswith("blocker:"):
                continue
            status, sev = rec["status"], rec["severity"]
            above = sev_rank(sev) >= threshold
            gf = rec.get("grounding_failed") is True
            desc = f"{sev} {status} {relpath_in_repo(rec.get('file') or '', repo.root)}:{rec.get('lines') or '?'} {rec.get('symbol') or ''}  {norm_claim(rec.get('claim'))}".strip()
            if status in GROUNDED and above:
                merged = next((b for b in list(open_now.values()) + res["new_blockers"] if same_key(b, rec)), None)
                if merged is not None:
                    if not gf and merged.get("id") in open_now:
                        upd = res["blocker_updates"].setdefault(merged["id"], {})
                        upd.update({"unverified": False, "head": run["head"],
                                    "file": relpath_in_repo(rec.get("file") or "", repo.root),
                                    "lines": rec_lines(rec) or merged.get("lines")})
                    continue
                res["new_blockers"].append(make_blocker(rec, False))
            elif (gf and above) or (status == "SUSPECTED" and sev == "CRIT"):
                if not is_error:
                    res["grounding"].append(desc)
                if any(same_key(b, rec) for b in list(open_now.values()) + res["new_blockers"]):
                    continue
                res["new_blockers"].append(make_blocker(rec, True))
            elif status in GROUNDED:
                res["followups"].append(desc)
            elif status == "SUSPECTED":
                res["questions"].append(desc)

    # Blockers passed to this run: rule 6. Skipped entirely on ERROR (an ERROR
    # run never closes anything; it only adds).
    if not is_error:
        for bid in passed_ids:
            b = open_now.get(bid)
            if b is None:
                continue
            recs = [r for r in valid if r["candidate_id"] == f"blocker:{bid}"]
            if len(recs) != 1:
                continue
            rec = recs[0]
            status = rec["status"]
            upd = res["blocker_updates"].setdefault(bid, {})
            if rec.get("grounding_failed") is True:
                res["grounding"].append(f"blocker {bid}: 근거 단계 실패")
                continue
            if status in GROUNDED:
                above = sev_rank(rec["severity"]) >= threshold
                if b.get("unverified") and not above:
                    upd.update({"open": False, "closed_by": "unverified_below_threshold", "closed_run": run["run"]})
                    res["closed"].append({"id": bid, "file": b.get("file"), "closed_by": "unverified_below_threshold"})
                    continue
                upd["unverified"] = False
                upd["head"] = run["head"]
                upd["file"] = relpath_in_repo(rec.get("file") or b.get("file") or "", repo.root)
                rl = rec_lines(rec)
                if rl:
                    upd["lines"] = rl
                else:
                    nl, inside = shift_lines(repo, b, run["head"], base_fallback)
                    if nl:
                        upd["lines"] = nl
                    if inside:
                        upd["needs_human"] = True
                        res["needs_human"].append(bid)
                continue
            if status == "REJECTED":
                if b.get("unverified"):
                    upd.update({"open": False, "closed_by": "unverified_rejected", "closed_run": run["run"]})
                    res["closed"].append({"id": bid, "file": b.get("file"), "closed_by": "unverified_rejected"})
                    continue
                ec = rec.get("_evidence_check") or {}
                if ec.get("quote_found") is True:
                    how = closing_check(repo, b, rec, run["head"], base_fallback)
                    if how:
                        upd.update({"open": False, "closed_by": how, "closed_run": run["run"]})
                        res["closed"].append({"id": bid, "file": b.get("file"), "closed_by": how})
                    else:
                        upd["needs_human"] = True
                        res["needs_human"].append(bid)
                continue
            # SUSPECTED without grounding_failed: stays open, nothing moves.

    if is_error:
        res["outcome"] = "ERROR"
    else:
        res["outcome"] = "PASS"
    return res


def apply_judgement(state: dict, run: dict, res: dict, finalized_late: bool = False) -> dict:
    """Write the judgement into `state` (caller holds the lock): blockers
    added/updated, the open union re-merged (L6), the run recorded."""
    cyc = state["cycle"]
    for bid, upd in res["blocker_updates"].items():
        for b in state["blockers"]:
            if b.get("id") == bid and b.get("cycle") == cyc:
                b.update(upd)
    for nb in res["new_blockers"]:
        state["blockers"].append(nb)
    union = open_blockers(state)
    passed = set(run.get("blockers_passed") or [])
    carried = [b["id"] for b in union if b["id"] not in passed and b["id"] not in {n["id"] for n in res["new_blockers"]}]
    if res["outcome"] == "ERROR":
        outcome = "ERROR"
    elif union or res["grounding"]:
        outcome = "BLOCK"
    else:
        outcome = "PASS"
    run.update({
        "outcome": outcome, "finished": now_iso(), "finalized_late": bool(finalized_late),
        "errors": res["errors"], "new_blockers": [n["id"] for n in res["new_blockers"]],
        "open_blockers": [blocker_public(b) for b in union], "carried_blockers": carried,
        "closed_blockers": res["closed"], "needs_human": res["needs_human"],
        "grounding": res["grounding"], "questions": res["questions"], "followups": res["followups"],
    })
    run["report"] = dict(run.get("report") or {}, lenses_completed=res["lenses_completed"])
    if "error" in run and outcome != "ERROR":
        del run["error"]
    elif outcome == "ERROR":
        run["error"] = "; ".join(res["errors"])[:2000]
    return run


def record_abandoned(run: dict) -> None:
    run.update({"outcome": "ERROR", "error": "abandoned", "finished": now_iso(), "finalized_late": False,
                "open_blockers": run.get("open_blockers") or []})


def finalize_pending(state: dict, main: Path, repo: Repo, cfg: Optional[dict]) -> list:
    """L6 for every run of the current cycle that is unrecorded, or recorded
    as abandoned but now has a report. Returns the runs it finalized."""
    done = []
    for run in cycle_runs(state):
        if run.get("kind") != "review":
            if run.get("outcome") is None:
                run.update({"outcome": "ERROR", "error": "abandoned (verify)", "finished": now_iso(), "finalized_late": False})
                done.append(run)
            continue
        pending = run.get("outcome") is None
        abandoned = run.get("outcome") == "ERROR" and run.get("error") == "abandoned"
        if not (pending or abandoned):
            continue
        report = read_report(Path(run.get("run_dir") or "")) if run.get("run_dir") else None
        if report is None:
            if pending:
                record_abandoned(run)
                done.append(run)
            continue
        res = judge_report(state, run, report, repo, cfg)
        run["report"] = {"path": posix(Path(run["run_dir"]) / REPORT_FILE), "sha256": report_sha256(Path(run["run_dir"]))}
        apply_judgement(state, run, res, finalized_late=True)
        done.append(run)
    return done


# --- status (L3, L4, merge guard priorities) -------------------------------

def carry_files(repo: Repo, lj: dict, head_t: str, base: str) -> Optional[list]:
    """L4: files that count between the PASS head H and target T. Three git
    calls, whatever the number of files; None when git could not answer."""
    h = lj.get("head")
    files = repo.diff_names(h, head_t)
    if files is None:
        return None
    reviewed_l = repo.diff_names(lj.get("merge_base") or h, h)
    if reviewed_l is None:
        return None
    reviewed = set(reviewed_l)
    bref = repo.base_ref(base)
    mb_t = repo.merge_base(head_t, bref) if bref else None
    # a file not reviewed whose content at T equals the base merge-base came from the base:
    # those are exactly the files ABSENT from diff(mb_t, T)
    from_t = None
    if mb_t:
        from_t = repo.diff_names(mb_t, head_t)
        if from_t is None:
            return None
        from_t = set(from_t)
    counted = []
    for f in files:
        if f not in reviewed and from_t is not None and f not in from_t:
            continue
        counted.append(f)
    return counted


def compute_status(main: Path, branch: str, head: Optional[str], repo: Optional[Repo] = None,
                   pr_files: Optional[list] = None, pr_changed_files: Optional[int] = None,
                   local_head: Optional[str] = None, deadline=None) -> dict:
    """Mergeability of `head` on `branch`. Read-only, lock-free (L1). `deadline`
    is a callable that raises when the caller's time is up (the hook); a git
    that cannot answer yields reason `unreadable` (never mergeable)."""
    main = Path(main)
    cfg, _ = load_main_config_status(main)
    base = base_branch(cfg)
    repo = repo or Repo(main)
    out = {"outcome": "OK", "mergeable": False, "reason": None, "head": head, "branch": branch,
           "last_judged": None, "open_blockers": [], "questions": [], "cycle": None, "cycle_open": None,
           "next": None, "since": []}
    try:
        return _compute_status(out, main, branch, head, repo, cfg, base, pr_files, pr_changed_files, local_head,
                               deadline or (lambda: None))
    except GitUnavailable as e:
        out.update(reason="unreadable", next=f"git could not answer ({e}); retry")
        return out


def _compute_status(out, main, branch, head, repo, cfg, base, pr_files, pr_changed_files, local_head, deadline) -> dict:
    state, st = load_state(main, branch)
    if st == "unreadable":
        out.update(reason="unreadable", next="상태 파일이 깨짐: 사람이 `! python <plugin>/hooks/gate.py reset <main> <branch>`")
        return out
    if st == "newer":
        out.update(reason="unreadable", next=f"{MSG_DDARO_OLD}: `claude plugin update ddaro` 후 세션 재시작")
        return out
    if st == "branch_mismatch":
        out.update(reason="unreadable", next="상태 파일의 branch 가 다름 (파일 손상)")
        return out
    out["cycle"] = state.get("cycle")
    deadline()
    if head is None:
        head = repo.rev(f"refs/heads/{branch}") or repo.head()
        out["head"] = head
    lj = last_judged(state)
    if lj:
        out["last_judged"] = {"run": lj.get("run"), "outcome": lj.get("outcome"), "head": lj.get("head")}
        out["questions"] = list(lj.get("questions") or [])
    opens = open_blockers(state)
    out["open_blockers"] = [blocker_public(b) for b in opens]
    out["cycle_open"] = bool(state.get("runs")) and any(True for _ in cycle_runs(state))

    approved = [a for a in state.get("approvals", []) if a.get("cycle") == state.get("cycle") and a.get("head") == head]
    if head and approved:
        out.update(mergeable=True, reason="approved",
                   next=f"human-approved over {len(approved[-1].get('overrides') or [])} open")
        return out
    if pr_files is not None:
        if pr_files and all(is_doc(f, cfg) for f in pr_files) and (pr_changed_files is None or pr_changed_files == len(pr_files)):
            out.update(mergeable=True, reason="docs_only_pr", next="docs-only PR")
            return out
    if opens:
        out.update(reason="open_blockers", next="/ddaro check")
        return out
    # L3: a later verify-only run that failed at head (or inside the carry range)
    if lj and head:
        later = [r for r in cycle_runs(state) if r.get("kind") == "verify" and r.get("run", 0) > lj.get("run", 0)
                 and r.get("outcome") in ("PASS", "BLOCK")]
        relevant = []
        for r in later:
            vh = r.get("head")
            if vh == head or (vh and lj.get("head") and repo.has_commit(vh) and repo.has_commit(head)
                              and repo.is_ancestor(lj["head"], vh) and repo.is_ancestor(vh, head)):
                relevant.append(r)
        if relevant and max(relevant, key=lambda r: r["run"]).get("outcome") == "BLOCK":
            out.update(reason="verify_failed", next="/ddaro check (tests failed at this commit)")
            return out
    if lj is None:
        out.update(reason="no_pass", next="/ddaro check")
        return out
    if lj.get("outcome") == "BLOCK":
        out.update(reason="last_judged_block", next="fix, commit, then /ddaro check")
        return out
    if head and lj.get("head") == head:
        out.update(mergeable=True, reason="head_match", next="/ddaro merge")
        return out
    deadline()
    if head and repo.has_commit(lj.get("head") or "") and repo.has_commit(head) and repo.is_ancestor(lj["head"], head):
        deadline()
        counted = carry_files(repo, lj, head, base)
        if counted is not None:
            out["since"] = [{"file": f, "kind": "doc" if is_doc(f, cfg) else "code"} for f in counted]
            if all(is_doc(f, cfg) for f in counted):
                out.update(mergeable=True, reason="carry_docs_only", next="/ddaro merge")
                return out
    if head and local_head and lj.get("head") == local_head and repo.has_commit(head) and repo.is_ancestor(head, local_head):
        out.update(reason="pr_head_behind_local", next="git push 후 다시 머지")
        return out
    out.update(reason="stale_pass", next="/ddaro check")
    return out


def status_summary(s: dict) -> list:
    lines = [f"[ddaro] gate status {s.get('branch')} @ {(s.get('head') or '?')[:7]}: "
             f"{'mergeable' if s.get('mergeable') else 'not mergeable'} ({s.get('reason')})"]
    lj = s.get("last_judged")
    if lj:
        lines.append(f"  last judged: run {lj['run']} {lj['outcome']} @ {(lj.get('head') or '?')[:7]}")
    if s.get("since"):
        lines.append("  since then: " + ", ".join(f"{x['file']} ({x['kind']})" for x in s["since"][:8]))
    if s.get("open_blockers"):
        lines.append(f"  open blockers ({len(s['open_blockers'])}):")
        for b in s["open_blockers"]:
            lines.append(f"    {b.get('severity')} {b.get('file')}:{b.get('lines') or '?'} {b.get('symbol') or ''}  {b.get('claim')}"
                         + ("  [needs_human]" if b.get("needs_human") else "") + ("  [unverified]" if b.get("unverified") else ""))
    if s.get("questions"):
        lines.append(f"  확인되지 않은 의심 {len(s['questions'])}건 (not blocking):")
        for q in s["questions"]:
            lines.append(f"    {q}")
    if s.get("next"):
        lines.append(f"  next: {s['next']}")
    return lines


# --- check-begin ------------------------------------------------------------

def resolve_main(wt: Path):
    """(main, cfg, cfg_status) for a worktree path (L10)."""
    main = main_root_of(wt)
    if main is None:
        raise GateError(f"{wt} is not inside a git repository")
    cfg, st = load_main_config_status(main)
    if cfg is not None and cfg.get("main_worktree"):
        mw = Path(str(cfg["main_worktree"]))
        # honour main_worktree only when it is this same repository (the hook and
        # `status` resolve <main> from git, so the state must live in one place)
        if mw.is_dir() and main_root_of(mw) == main:
            main = mw.resolve()
    return main, cfg, st


def refused(msg: str, summary_extra: Optional[list] = None, **extra) -> dict:
    d = {"outcome": "REFUSED", "message": msg, "summary": [f"[ddaro] check: REFUSED - {msg}"] + list(summary_extra or [])}
    d.update(extra)
    return d


def make_run_tag(branch: str, head: str, run_no: int) -> tuple:
    """Returns (run_tag, rand): `<branch>-<sha7>-<run>-<rand6>` limited to
    prism's run-tag alphabet `[A-Za-z0-9._-]` and 64 chars (the spec's `@`/`#`
    are outside it), and the 6-hex `rand` that also names the run folder."""
    rand = secrets.token_hex(3)
    tail = f"-{head[:7]}-{run_no}-{rand}"
    b = re.sub(r"[^A-Za-z0-9._-]", "_", branch).strip("._-") or "branch"
    b = re.sub(r"^[^A-Za-z0-9]+", "", b) or "branch"
    return (b[: max(1, 64 - len(tail))] + tail), rand


def gate_snapshot(main: Path, branch: str) -> dict:
    """Bytes (sha256) of every file the tests must not touch: the branch state
    file, its .bak, config.json, verify.json, and the names of everything under
    gates/ (c13: a committed test could otherwise forge a PASS or approval)."""
    snap = {}
    for p in (state_path(main, branch), Path(str(state_path(main, branch)) + ".bak"),
              Path(main) / ".ddaro" / "config.json", Path(main) / ".ddaro" / "verify.json"):
        try:
            snap[posix(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
        except FileNotFoundError:
            snap[posix(p)] = None
        except Exception:
            snap[posix(p)] = "?"
    gd = gates_dir(main)
    try:
        for x in sorted(gd.rglob("*")) if gd.is_dir() else []:
            if x.is_file() and x.suffix == ".json" and ".tmp" not in x.name:
                try:
                    snap["gates/" + x.relative_to(gd).as_posix()] = hashlib.sha256(x.read_bytes()).hexdigest()
                except Exception:
                    snap["gates/" + x.relative_to(gd).as_posix()] = "?"
    except Exception:
        snap["__gates__"] = "?"
    marker = None
    try:
        from _shared import gate_marker_path
        marker = gate_marker_path(main)
    except Exception:
        pass
    if marker is not None:
        snap["__marker__"] = marker.exists()
    return snap


def gate_snapshot_diff(before: dict, after: dict) -> list:
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def cmd_check_begin(wt: Path, full: bool) -> dict:
    t0 = time.monotonic()
    main, cfg, cfg_status = resolve_main(wt)
    if cfg is None:
        return refused(f"<main> config missing or unreadable ({cfg_status}) at {main}")
    repo = Repo(wt)
    top = repo.toplevel()
    if top is None:
        return refused(f"{wt} is not a git worktree")
    repo = Repo(top)
    base = base_branch(cfg)

    # 1. readiness
    branch = repo.branch()
    if not branch:
        return refused("detached HEAD")
    lock = parse_lock(Path(top) / ".ddaro" / "LOCK")
    if lock and lock.get("branch") and str(lock.get("branch")) != branch:
        return refused(f"LOCK branch {lock.get('branch')!r} != checked out {branch!r}")
    dirty = repo.dirty_tracked()
    if dirty:
        return refused("tracked files have uncommitted changes (dirty): " + ", ".join(dirty[:5]))
    prism_path, perr = prism_check()
    if prism_path is None:
        return refused(perr)
    head = repo.head()
    if not head:
        return refused("cannot resolve HEAD")
    bref = repo.base_ref(base)
    if bref is None:
        return refused(f"base branch {base!r} not found (origin/{base} or {base})")
    mb = repo.merge_base(bref, head)
    if not mb:
        return refused(f"no merge-base between {bref} and HEAD")

    try:
        with locked(main, branch):
            state, st = load_state(main, branch)
            if st in ("unreadable", "branch_mismatch"):
                return refused("상태 파일이 깨짐(PASS 확인 불가): 사람이 `! python <plugin>/hooks/gate.py reset <main> <branch>`")
            if st == "newer":
                return refused(f"{MSG_DDARO_OLD}: 상태 파일 schema 가 더 새 것")
            # 2. cycle cleanup: record first, then confirm merges
            finalized = finalize_pending(state, main, repo, cfg)
            merge_note = confirm_merged(state, main, repo, branch, base)
            # 3. run number and range
            lj = last_judged(state)
            opens = open_blockers(state)
            notes = []
            if merge_note.get("closed") or "머지 확인 못 함" in (merge_note.get("note") or ""):
                notes.append(merge_note["note"])
            runs_now = cycle_runs(state)
            prev = max(runs_now, key=lambda r: r.get("run", 0)) if runs_now else None
            scope = None
            rng = None
            verify_only = False
            if lj and lj.get("head") == head and not full:
                later_verify = [r for r in runs_now if r.get("kind") == "verify" and r.get("run", 0) > lj["run"]
                                and r.get("head") == head and r.get("outcome") in ("PASS", "BLOCK")]
                last_v = max(later_verify, key=lambda r: r["run"]) if later_verify else None
                if not opens:
                    if last_v and last_v.get("outcome") == "BLOCK":
                        verify_only = True
                        scope = "verify"
                    else:
                        save_state(main, branch, state)
                        return refused("새 커밋 없음, 이미 판정됨", run=None, head=head, last_judged=lj.get("run"),
                                       finalized=[f["run"] for f in finalized])
                else:
                    scope = "rejudge"
            if scope is None:
                reasons = []
                if full:
                    reasons.append("--full")
                if lj is None:
                    reasons.append("no judged run in this cycle")
                elif not repo.has_commit(lj.get("head") or "") or not repo.is_ancestor(lj["head"], head):
                    reasons.append("last judged head is not an ancestor of HEAD (rebase/reset or missing commit)")
                elif lj.get("merge_base") != mb:
                    reasons.append("base merged since the last judged run")
                if prev is not None and prev.get("outcome") == "ERROR" and prev.get("error") == "abandoned":
                    reasons.append(f"previous run {prev.get('run')} abandoned")
                missing = [b["id"] for b in opens if not repo.has_commit(b.get("head") or "")]
                if missing:
                    reasons.append("blocker commit missing locally: " + ", ".join(missing))
                if reasons:
                    scope = "full"
                    rng = f"{mb}...{head}"
                    notes.append("full: " + "; ".join(reasons))
                else:
                    scope = "recheck"
                    rng = f"{lj['head']}..{head}"
            run_no = int(state.get("next_run") or 1)
            state["next_run"] = run_no + 1
            run_tag, rand = make_run_tag(branch, head, run_no)
            if verify_only:
                notes.append("verify only: tests re-run at the already judged head")
            rdir = runs_dir(main, branch) / f"{run_no}-{rand}"
            rdir.mkdir(parents=True, exist_ok=False)
            run_dir = posix(rdir)
            run = {"run": run_no, "cycle": state["cycle"], "kind": "verify" if verify_only else "review",
                   "scope": scope, "started": now_iso(), "finished": None, "head": head, "merge_base": mb,
                   "range": rng, "run_tag": run_tag, "run_dir": run_dir, "outcome": None,
                   "finalized_late": False, "blockers_passed": [b["id"] for b in opens],
                   "open_blockers": [blocker_public(b) for b in opens], "notes": notes}
            if not verify_only:
                write_json_atomic(rdir / BLOCKERS_FILE, [blocker_for_prism(b) for b in opens], keep_bak=False)
            state["runs"].append(run)
            save_state(main, branch, state)
    except TimeoutError as e:
        return refused(str(e))

    out = {"outcome": "OK", "run": run_no, "run_tag": run_tag, "run_dir": run_dir, "scope": scope,
           "head": head, "merge_base": mb, "range": rng, "open_blockers": [blocker_public(b) for b in opens],
           "finalized": [{"run": f.get("run"), "outcome": f.get("outcome"), "error": f.get("error")} for f in finalized],
           "notes": notes, "verify": None}

    note_lines = [f"  note: {n}" for n in notes]
    # 4. tests before the review (no lock). The gate's own files are snapshotted
    # first: a test that touches them is refused and the state restored (c13).
    changed = repo.diff_names(mb, head) or []
    cmds, block_reason, note = select_verify(main, cfg, changed)
    verify = {"commands": cmds, "results": [], "note": note}
    failed = None
    snap_before = gate_snapshot(main, branch)
    keep_bytes = {}
    for kp in (state_path(main, branch), Path(main) / ".ddaro" / "verify.json", Path(main) / ".ddaro" / "config.json"):
        try:
            keep_bytes[kp] = kp.read_bytes()
        except Exception:
            pass
    if block_reason:
        failed = block_reason
    elif cmds:
        elapsed = time.monotonic() - t0
        budget = max(1, min(verify_budget(), int(VERIFY_BUDGET + 20 - elapsed)))
        results, failed = run_verify(Path(top), cmds, budget=budget)
        verify["results"] = results
    out["verify"] = verify
    tampered = gate_snapshot_diff(snap_before, gate_snapshot(main, branch))
    if tampered:
        try:
            with locked(main, branch):
                for kp, data in keep_bytes.items():
                    try:
                        if not kp.exists() or kp.read_bytes() != data:
                            kp.write_bytes(data)      # put the pre-test bytes back
                    except Exception:
                        pass
        except Exception:
            pass
        why = "테스트가 게이트 상태를 바꿈: " + ", ".join(Path(k).name if not k.startswith("__") else k.strip("_") for k in tampered[:5])
        _record_verify_run(main, branch, run_no, "REFUSED", verify, why)
        return refused(why, run=run_no, head=head, verify=verify, summary_extra=note_lines)
    # tree must be unchanged by the tests
    head2 = repo.head()
    dirty2 = repo.dirty_tracked()
    if head2 != head or dirty2:
        why = "HEAD moved" if head2 != head else ", ".join(dirty2[:5])
        _record_verify_run(main, branch, run_no, "REFUSED", verify, f"테스트가 트리를 바꿈: {why}")
        return refused(f"테스트가 트리를 바꿈: {why}", run=run_no, head=head, verify=verify, summary_extra=note_lines)
    if failed:
        rec_note = _record_verify_run(main, branch, run_no, "BLOCK", verify, failed)
        out.update(outcome="BLOCK", message=f"테스트 실패: {failed}")
        out["summary"] = [f"[ddaro] check {run_no} ({scope} {_short_range(rng, head)}): BLOCK",
                          f"  verify: {failed}"] + note_lines + rec_note + ["  next: fix, commit, then /ddaro check"]
        return out
    if verify_only:
        rec_note = _record_verify_run(main, branch, run_no, "PASS", verify, None)
        out.update(outcome="PASS", message="tests passed at the already judged head")
        out["summary"] = [f"[ddaro] check {run_no} (verify only @ {head[:7]}): PASS",
                          "  verify: " + _verify_line(verify)] + note_lines + rec_note + ["  next: /ddaro merge"]
        return out

    # 5. output
    rec_note = _store_verify(main, branch, run_no, verify)
    args = []
    if scope != "rejudge":
        args += ["--diff", rng]
    args += ["--format", "json", "--lenses=defect", "--no-pr-body", "--no-ideas", "--run-tag", run_tag,
             "--head", head, "--blockers", _q(f"{run_dir}/{BLOCKERS_FILE}"), "--out", _q(run_dir)]
    out["prism_skill_args"] = " ".join(args)
    out["summary"] = [f"[ddaro] check {run_no} ({scope} {_short_range(rng, head)}): tests passed, review next",
                      "  verify: " + _verify_line(verify),
                      f"  open blockers carried: {len(opens)}"] + note_lines + rec_note
    return out


def _q(s: str) -> str:
    return f'"{s}"' if re.search(r"\s", s) else s


def _short_range(rng: Optional[str], head: str) -> str:
    if not rng:
        return f"rejudge @ {head[:7]}"
    m = re.match(r"^([0-9a-f]{40})(\.{2,3})([0-9a-f]{40})$", rng)
    return f"{m.group(1)[:7]}{m.group(2)}{m.group(3)[:7]}" if m else rng


def _verify_line(verify: dict) -> str:
    if verify.get("note"):
        return verify["note"]
    parts = [f"{r['cmd']} -> exit {r.get('exit')} ({r.get('seconds')}s)" for r in verify.get("results") or []]
    return "; ".join(parts) if parts else "(no command)"


def _record_verify_run(main: Path, branch: str, run_no: int, outcome: str, verify: dict, error: Optional[str]) -> list:
    """Record a tests-only outcome. Returns summary lines (empty when recorded;
    a note when the lock stayed busy or the state vanished, c7)."""
    def mutate(run):
        run.update({"kind": "verify", "outcome": outcome, "finished": now_iso(), "verify": verify})
        if error:
            run["error"] = error
    return _update_run(main, branch, run_no, mutate, "verify result")


def _store_verify(main: Path, branch: str, run_no: int, verify: dict) -> list:
    def mutate(run):
        run["verify"] = verify
    return _update_run(main, branch, run_no, mutate, "verify results")


def _update_run(main: Path, branch: str, run_no: int, mutate, what: str) -> list:
    for attempt in range(2):
        try:
            with locked(main, branch) if attempt == 0 else file_lock(lock_path(main, branch), LOCK_TIMEOUT * 4):
                state, st = load_state(main, branch)
                if st != "ok":
                    return [f"  note: {what} of run {run_no} not recorded (state file {st})"]
                run = find_run(state, run_no)
                if run is None:
                    return [f"  note: {what} of run {run_no} not recorded (run missing from the state file)"]
                mutate(run)
                save_state(main, branch, state)
                return []
        except TimeoutError as e:
            if attempt == 1:
                return [f"  note: {what} of run {run_no} not recorded ({e}); the run will be finalized by the next check-begin"]
        except OSError as e:
            return [f"  note: {what} of run {run_no} not recorded ({e})"]
    return []


# --- check-record -----------------------------------------------------------

def run_summary(run: dict, prefix: str = "check") -> list:
    scope = run.get("scope")
    head = run.get("head") or ""
    lines = [f"[ddaro] {prefix} {run.get('run')} ({scope} {_short_range(run.get('range'), head)}): {run.get('outcome')}"
             + (" (finalized late)" if run.get("finalized_late") else "")]
    if run.get("outcome") == "ERROR":
        lines.append(f"  error: {run.get('error')}")
    nb = run.get("new_blockers") or []
    opens = run.get("open_blockers") or []
    if nb:
        lines.append(f"  new blockers ({len(nb)}):")
        for b in opens:
            if b.get("id") in nb:
                lines.append(f"    {b.get('severity')} {b.get('file')}:{b.get('lines') or '?'} {b.get('symbol') or ''}  {b.get('claim')}")
    closed = run.get("closed_blockers") or []
    carried = [b for b in opens if b.get("id") not in nb]
    if closed or carried or run.get("kind") == "review":
        lines.append(f"  open blockers: {len(closed)} closed" + (f" ({', '.join(sorted({c.get('closed_by') or '' for c in closed}))})" if closed else "")
                     + f", {len(carried)} carried open")
        for b in carried:
            lines.append(f"    {b.get('severity')} {b.get('file')}:{b.get('lines') or '?'} {b.get('symbol') or ''}  {b.get('claim')}"
                         + ("  [needs_human]" if b.get("needs_human") else "") + ("  [unverified]" if b.get("unverified") else ""))
    if run.get("grounding"):
        lines.append("  근거 단계 재실행 필요: " + "; ".join(run["grounding"]))
    if run.get("kind") == "review" and run.get("report") is not None:
        lc = (run.get("report") or {}).get("lenses_completed") or []
        lines.append(f"  review: /prism{' --diff' if scope != 'rejudge' else ' (rejudge)'}, defect lenses {len(lc)}/5 completed")
    if run.get("verify"):
        lines.append("  verify: " + _verify_line(run["verify"]))
    if run.get("followups"):
        lines.append(f"  follow-ups ({len(run['followups'])}, not blocking):")
        lines += [f"    {f}" for f in run["followups"]]
    if run.get("questions"):
        lines.append(f"  확인되지 않은 의심 {len(run['questions'])}건 (not blocking):")
        lines += [f"    {q}" for q in run["questions"]]
    oc = run.get("outcome")
    if oc == "PASS":
        lines.append("  next: /ddaro merge")
    elif oc == "BLOCK":
        lines.append("  next: fix, commit, then /ddaro check")
    elif oc == "ERROR":
        lines.append("  next: /ddaro check (run the review again)")
    return lines


def run_public(run: dict) -> dict:
    keys = ("run", "cycle", "kind", "scope", "head", "merge_base", "range", "run_tag", "run_dir", "outcome",
            "finalized_late", "error", "errors", "new_blockers", "open_blockers", "carried_blockers",
            "closed_blockers", "needs_human", "grounding", "questions", "followups", "verify", "report")
    return {k: run.get(k) for k in keys if k in run}


def cmd_check_record(wt: Path, run_no: int) -> dict:
    main, cfg, cfg_status = resolve_main(wt)
    if cfg is None:
        return refused(f"<main> config missing or unreadable ({cfg_status}) at {main}")
    repo = Repo(Repo(wt).toplevel() or wt)
    branch = repo.branch()
    if not branch:
        return refused("detached HEAD")
    try:
        with locked(main, branch):
            state, st = load_state(main, branch)
            if st in ("unreadable", "branch_mismatch"):
                return refused("상태 파일이 깨짐(PASS 확인 불가)")
            if st == "newer":
                return refused(f"{MSG_DDARO_OLD}: 상태 파일 schema 가 더 새 것")
            run = find_run(state, run_no)
            if run is None:
                return _record_in_archive(main, branch, run_no, repo, cfg)
            if run.get("kind") == "verify":
                d = run_public(run)
                d["summary"] = run_summary(run)
                return d
            report = read_report(Path(run.get("run_dir") or ""))
            abandoned = run.get("outcome") == "ERROR" and run.get("error") == "abandoned"
            if run.get("outcome") is not None and not (abandoned and report is not None):
                d = run_public(run)
                d["summary"] = run_summary(run)
                return d
            if report is None:
                has_run_file = (Path(run.get("run_dir") or "") / RUN_FILE).is_file()
                msg = "리포트 없음" if has_run_file else f"리포트 없음: {MSG_OUT_UNKNOWN}"
                return {"outcome": "STALE", "run": run_no, "message": msg,
                        "summary": [f"[ddaro] check {run_no}: STALE - {msg}", "  next: /ddaro check (다음 실행은 full)"]}
            res = judge_report(state, run, report, repo, cfg)
            run["report"] = {"path": posix(Path(run["run_dir"]) / REPORT_FILE), "sha256": report_sha256(Path(run["run_dir"]))}
            apply_judgement(state, run, res, finalized_late=abandoned)
            save_state(main, branch, state)
            d = run_public(run)
            d["summary"] = run_summary(run)
            return d
    except TimeoutError as e:
        return refused(str(e))


def _record_in_archive(main: Path, branch: str, run_no: int, repo: Repo, cfg) -> dict:
    """A run that is only in a closed cycle's archive: judge once there, never
    into the current cycle (L2 '닫힌 주기의 실행')."""
    adir = archive_dir(main, branch)
    unreadable = []
    if adir.is_dir():
        for f in sorted(adir.glob("cycle-*.json")):
            arch = read_json_or_none(f)
            if not isinstance(arch, dict):
                unreadable.append(f.name)
                continue
            run = next((r for r in arch.get("runs", []) if r.get("run") == run_no), None)
            if run is None:
                continue
            pending = run.get("outcome") is None
            abandoned = run.get("outcome") == "ERROR" and run.get("error") == "abandoned"
            if (pending or abandoned) and run.get("kind") == "review":
                report = read_report(Path(run.get("run_dir") or ""))
                if report is not None:
                    pseudo = {"cycle": arch.get("cycle"), "runs": arch.get("runs", []), "blockers": arch.get("blockers", []),
                              "approvals": [], "closes": []}
                    res = judge_report(pseudo, run, report, repo, cfg)
                    run["report"] = {"path": posix(Path(run["run_dir"]) / REPORT_FILE), "sha256": report_sha256(Path(run["run_dir"]))}
                    apply_judgement(pseudo, run, res, finalized_late=True)
                    arch["blockers"] = pseudo["blockers"]
                    write_json_atomic(f, arch, keep_bak=False)
                elif pending:
                    record_abandoned(run)
                    write_json_atomic(f, arch, keep_bak=False)
            return {"outcome": "STALE", "run": run_no, "message": MSG_CYCLE_CLOSED, "archived_outcome": run.get("outcome"),
                    "summary": [f"[ddaro] check {run_no}: STALE - {MSG_CYCLE_CLOSED} (cycle {arch.get('cycle')} archived, recorded there as {run.get('outcome')})"]}
    if unreadable:
        return refused(f"run {run_no} not found in readable archives; unreadable: {', '.join(unreadable)}")
    return refused(f"run {run_no} not found for {branch}")


# --- close / retire / approve / reset --------------------------------------

def cmd_close(main: Path, branch: str, merged: bool, pr: Optional[int]) -> dict:
    cfg, st = load_main_config_status(main)
    if cfg is None:
        return refused(f"<main> config missing or unreadable ({st}) at {main}")
    repo = Repo(main)
    base = base_branch(cfg)
    try:
        with locked(main, branch):
            state, sst = load_state(main, branch)
            if sst in ("unreadable", "branch_mismatch", "newer"):
                return refused(f"state file {sst}")
            finalize_pending(state, main, repo, cfg)
            if merged:
                r = confirm_merged(state, main, repo, branch, base, pr=pr)
                if not r["closed"]:
                    save_state(main, branch, state)
                    return {"outcome": "OK", "closed": False, "message": r["note"], "cycle": state["cycle"],
                            "summary": [f"[ddaro] gate close: not closed ({r['note']})"]}
            else:
                close_cycle(state, main, branch, {"pr": pr, "merged_head": None, "how": "manual"})
            save_state(main, branch, state)
            return {"outcome": "OK", "closed": True, "cycle": state["cycle"],
                    "summary": [f"[ddaro] gate close: cycle -> {state['cycle']}"]}
    except TimeoutError as e:
        return refused(str(e))


def cmd_retire(main: Path, branch: str) -> dict:
    repo = Repo(main)
    if repo.ref_exists(f"refs/heads/{branch}"):
        return {"outcome": "OK", "retired": False, "message": f"branch {branch} still exists; nothing moved",
                "summary": [f"[ddaro] gate retire: {branch} still exists, state kept"]}
    p = state_path(main, branch)
    try:
        with locked(main, branch):
            if not p.exists():
                return {"outcome": "OK", "retired": False, "message": "no state file", "summary": ["[ddaro] gate retire: no state"]}
            dest = archive_dir(main, branch) / f"retired-{_dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(p, dest)
            except OSError as e:
                return refused(f"could not move state file: {e}")
            for extra in (str(p) + ".bak",):
                try:
                    os.unlink(extra)
                except OSError:
                    pass
    except TimeoutError as e:
        return refused(str(e))
    return {"outcome": "OK", "retired": True, "archived_to": posix(dest), "summary": [f"[ddaro] gate retire: state -> {posix(dest)}"]}


def cmd_approve(main: Path, branch: str, head: str, reason: str) -> dict:
    repo = Repo(main)
    sha = repo.rev(head)
    if not sha:
        return refused(f"{head!r} is not a commit in {main}")
    if not reason or not reason.strip():
        return refused("--reason is required")
    try:
        with locked(main, branch):
            state, st = load_state(main, branch)
            if st in ("unreadable", "branch_mismatch", "newer"):
                return refused(f"state file {st}")
            overrides = [b["id"] for b in open_blockers(state)]
            state["approvals"].append({"cycle": state["cycle"], "head": sha, "reason": reason.strip(),
                                       "overrides": overrides, "at": now_iso()})
            save_state(main, branch, state)
    except TimeoutError as e:
        return refused(str(e))
    return {"outcome": "OK", "approved": sha, "overrides": overrides,
            "summary": [f"[ddaro] gate approve: {sha[:7]} on {branch} (human-approved over {len(overrides)} open)"]}


def cmd_reset(main: Path, branch: str, force: bool = False) -> dict:
    p = state_path(main, branch)
    try:
        with locked(main, branch):
            if not p.exists():
                return {"outcome": "OK", "reset": False, "message": "no state file", "summary": ["[ddaro] gate reset: no state file"]}
            _, st = load_state(main, branch)
            if st == "ok" and not force:
                return refused("state file parses fine; reset is for unparseable damage only (pass --force to move it anyway)")
            dest = archive_dir(main, branch) / f"{branch_enc(branch)}.{_dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(p, dest)
            except OSError as e:
                return refused(f"could not move state file: {e}")
    except TimeoutError as e:
        return refused(str(e))
    return {"outcome": "OK", "reset": True, "archived_to": posix(dest), "summary": [f"[ddaro] gate reset: state -> {posix(dest)}"]}


# --- CLI -------------------------------------------------------------------

def _opt(argv: list, name: str, default=None, flag: bool = False):
    if name in argv:
        i = argv.index(name)
        if flag:
            return True
        if i + 1 < len(argv):
            return argv[i + 1]
        raise GateError(f"{name} needs a value")
    return default


def main(argv: list) -> int:
    utf8_stdio()
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    cmd = argv[0]
    try:
        if cmd == "status" and len(argv) >= 2:
            main_p = Path(argv[1]).resolve()
            branch = _opt(argv, "--branch")
            if not branch:
                branch = Repo(main_p).branch()
                if not branch:
                    raise GateError("--branch required (detached HEAD in <main>)")
            s = compute_status(main_p, branch, _opt(argv, "--head"))
            s["summary"] = status_summary(s)
            out = s
        elif cmd == "check-begin" and len(argv) >= 2:
            out = cmd_check_begin(Path(argv[1]).resolve(), _opt(argv, "--full", False, flag=True) is True)
        elif cmd == "check-record" and len(argv) >= 2:
            run_s = _opt(argv, "--run")
            if run_s is None:
                raise GateError("--run <id> required")
            out = cmd_check_record(Path(argv[1]).resolve(), int(run_s))
        elif cmd == "close" and len(argv) >= 3:
            pr = _opt(argv, "--pr")
            out = cmd_close(Path(argv[1]).resolve(), argv[2], _opt(argv, "--merged", False, flag=True) is True,
                            int(pr) if pr else None)
        elif cmd == "retire" and len(argv) >= 3:
            out = cmd_retire(Path(argv[1]).resolve(), argv[2])
        elif cmd == "approve" and len(argv) >= 3:
            head = _opt(argv, "--head")
            if not head:
                raise GateError("--head <sha> required")
            out = cmd_approve(Path(argv[1]).resolve(), argv[2], head, _opt(argv, "--reason", "") or "")
        elif cmd == "reset" and len(argv) >= 3:
            out = cmd_reset(Path(argv[1]).resolve(), argv[2], _opt(argv, "--force", False, flag=True) is True)
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except GateError as e:
        print(f"[ddaro] gate {cmd} failed: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # a script failure: one readable first line, then the trace
        import traceback
        print(f"[ddaro] gate {cmd} failed: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
