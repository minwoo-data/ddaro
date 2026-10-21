"""Fixtures for the merge-gate tests (gate.py, check-merge-gate.py).

A `GateRepo` is a throwaway repository: a bare `origin`, a main worktree with
`.ddaro/config.json` (`merge_gate` strict by default) and `verify.json`, and a
linked worktree on branch `d-busan` with its own commits. `gh` is a fake on
PATH (`gh.bat` on Windows / `gh` shell script elsewhere, both running
`fake_gh.py`) that answers from a JSON script file named by `FAKE_GH_FILE`, so
every merge-confirmation and PR-view path runs without a network. prism is a
fake install (`$CLAUDE_CONFIG_DIR/plugins/installed_plugins.json` ->
`<fake>/skills/prism/report-contract.json`), and reports are written by
`write_report`, which mirrors what prism 0.6.0's `assemble-report.js finish`
puts in `prism-report.json` for the given run.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
GATE = HOOKS_DIR / "gate.py"
DEFECT = ["correctness", "security", "state", "integration", "testability"]

FAKE_GH_PY = r'''
import json, os, sys
script_path = os.environ.get("FAKE_GH_FILE")
args = sys.argv[1:]
script = {}
if script_path and os.path.isfile(script_path):
    with open(script_path, encoding="utf-8") as fh:
        script = json.load(fh)
if script.get("fail"):
    sys.stderr.write(str(script.get("fail")) + "\n"); sys.exit(1)
if script.get("sleep"):
    import time; time.sleep(float(script["sleep"]))
key = " ".join(args[:2])
if key == "pr list":
    prs = script.get("list", [])
    state = None
    if "--state" in args: state = args[args.index("--state") + 1]
    out = [p for p in prs if state is None or p.get("state", "").lower() == state.lower() or state == "all"]
    if "--head" in args:
        h = args[args.index("--head") + 1]; out = [p for p in out if p.get("headRefName") == h]
    if "--base" in args:
        b = args[args.index("--base") + 1]; out = [p for p in out if p.get("baseRefName") == b]
    print(json.dumps(out)); sys.exit(0)
if key == "pr view":
    sel = args[2] if len(args) > 2 and not args[2].startswith("-") else None
    views = script.get("view", {})
    pr = views.get(str(sel)) if sel is not None else None
    if pr is None:
        for p in script.get("list", []):
            if str(p.get("number")) == str(sel) or p.get("headRefName") == sel or str(p.get("url")) == str(sel):
                pr = p; break
    if pr is None:
        sys.stderr.write("GraphQL: Could not resolve to a PullRequest\n"); sys.exit(1)
    print(json.dumps(pr)); sys.exit(0)
if key == "pr merge":
    print("merged (fake)"); sys.exit(0)
if args[:1] == ["api"]:
    print(json.dumps(script.get("api", {}))); sys.exit(0)
print(json.dumps(script.get("default", {}))); sys.exit(0)
'''


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.decode('utf-8', 'replace')}")
    return r.stdout.decode("utf-8", "replace").strip()


def make_fake_gh(bin_dir: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "fake_gh.py").write_text(FAKE_GH_PY, encoding="utf-8")
    if os.name == "nt":
        (bin_dir / "gh.bat").write_text(f'@"{sys.executable}" "%~dp0fake_gh.py" %*\r\n', encoding="utf-8")
    else:
        sh = bin_dir / "gh"
        sh.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$(dirname "$0")/fake_gh.py" "$@"\n', encoding="utf-8")
        sh.chmod(0o755)


def make_fake_prism(cfg_dir: Path, contract: str | None = "2", installed: bool = True) -> Path:
    """A fake `$CLAUDE_CONFIG_DIR` with prism installed at `<cfg>/cache/prism/0.6.0`."""
    install = cfg_dir / "plugins" / "cache" / "haroom_plugins" / "prism" / "0.6.0"
    (install / "skills" / "prism").mkdir(parents=True, exist_ok=True)
    if contract is not None:
        (install / "skills" / "prism" / "report-contract.json").write_text(
            json.dumps({"report_contract": contract}), encoding="utf-8")
    # a decoy older version in the cache, never read
    decoy = cfg_dir / "plugins" / "cache" / "haroom_plugins" / "prism" / "0.4.2" / "skills" / "prism"
    decoy.mkdir(parents=True, exist_ok=True)
    plugins = {}
    if installed:
        plugins["prism@haroom_plugins"] = {"version": "0.6.0", "installPath": str(install)}
    (cfg_dir / "plugins").mkdir(parents=True, exist_ok=True)
    (cfg_dir / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": plugins}), encoding="utf-8")
    return install


class GateRepo:
    def __init__(self, tmp_path: Path, base: str = "master", branch: str = "d-busan",
                 merge_gate: str = "strict", verify_cmd: str | None = "true", **cfg_extra):
        self.tmp = tmp_path
        self.base = base
        self.branch = branch
        self.origin = tmp_path / "origin.git"
        self.main = tmp_path / "proj"
        self.wt = tmp_path / "proj-d-busan"
        self.cfg_dir = tmp_path / "claude-cfg"
        self.bin = tmp_path / "bin"
        self.gh_script = tmp_path / "gh.json"
        self.gh_script.write_text("{}", encoding="utf-8")
        make_fake_gh(self.bin)
        self.prism_install = make_fake_prism(self.cfg_dir)
        # repository
        _git(tmp_path, "init", "-q", "--bare", str(self.origin))
        self.main.mkdir()
        _git(self.main, "init", "-q", "-b", base)
        _git(self.main, "config", "user.name", "t")
        _git(self.main, "config", "user.email", "t@t")
        (self.main / "src").mkdir()
        (self.main / "src" / "app.js").write_text("function a() {\n  return 1;\n}\n", encoding="utf-8")
        (self.main / "README.md").write_text("# proj\n", encoding="utf-8")
        _git(self.main, "add", "-A")
        _git(self.main, "commit", "-q", "-m", "init")
        _git(self.main, "remote", "add", "origin", str(self.origin))
        _git(self.main, "push", "-q", "-u", "origin", base)
        (self.main / ".ddaro").mkdir()
        self.cfg = {"schema_version": 4, "main_worktree": self.main.resolve().as_posix(), "base_branch": base,
                    "merge_gate": merge_gate, "gate_block_severity": "MED", "gate_verify": "auto",
                    "main_protection": "strict",
                    "planning_patterns": [".planning/**", "STATE.md", "ROADMAP.md", "CHANGELOG.md", "docs/**"]}
        self.cfg.update(cfg_extra)
        self.write_cfg()
        if verify_cmd is not None:
            self.write_verify({"commands": [], "default": verify_cmd})
        # worktree on the branch
        _git(self.main, "worktree", "add", "-q", "-b", branch, str(self.wt), base)
        (self.wt / ".ddaro").mkdir()
        (self.wt / ".ddaro" / "LOCK").write_text(json.dumps({"branch": branch, "main_worktree": self.main.as_posix()}), encoding="utf-8")
        self.write_exclude()

    # --- setup helpers
    def write_exclude(self):
        for root in (self.main, self.wt):
            gd = _git(root, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude")
            Path(gd).parent.mkdir(parents=True, exist_ok=True)
            Path(gd).write_text(".ddaro/\n", encoding="utf-8")

    def write_cfg(self, **changes):
        self.cfg.update(changes)
        (self.main / ".ddaro" / "config.json").write_text(json.dumps(self.cfg, indent=1), encoding="utf-8")

    def write_verify(self, spec: dict | None):
        p = self.main / ".ddaro" / "verify.json"
        if spec is None:
            if p.exists():
                p.unlink()
        else:
            p.write_text(json.dumps(spec), encoding="utf-8")

    def gh(self, **script):
        self.gh_script.write_text(json.dumps(script), encoding="utf-8")

    def env(self, **extra) -> dict:
        env = dict(os.environ)
        env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "")
        env["FAKE_GH_FILE"] = str(self.gh_script)
        env["CLAUDE_CONFIG_DIR"] = str(self.cfg_dir)
        for k in ("ALLOW_MAIN_DIRECT",):
            env.pop(k, None)
        env.update(extra)
        return env

    # --- git helpers
    def commit(self, rel: str, content: str, msg: str = "c", cwd: Path | None = None) -> str:
        root = cwd or self.wt
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", msg)
        return _git(root, "rev-parse", "HEAD")

    def rm_commit(self, rel: str, msg: str = "rm") -> str:
        _git(self.wt, "rm", "-q", rel)
        _git(self.wt, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", msg)
        return self.head()

    def amend(self, rel: str, content: str) -> str:
        (self.wt / rel).write_text(content, encoding="utf-8")
        _git(self.wt, "add", "-A")
        _git(self.wt, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--amend", "--no-edit")
        return self.head()

    def head(self, cwd: Path | None = None) -> str:
        return _git(cwd or self.wt, "rev-parse", "HEAD")

    def git(self, *args: str, cwd: Path | None = None) -> str:
        return _git(cwd or self.wt, *args)

    def push(self):
        _git(self.wt, "push", "-q", "-u", "origin", self.branch)

    def base_commit(self, rel: str, content: str, msg: str = "base") -> str:
        sha = self.commit(rel, content, msg, cwd=self.main)
        _git(self.main, "push", "-q", "origin", self.base)
        return sha

    # --- gate
    def gate(self, *args: str, env: dict | None = None) -> dict:
        r = subprocess.run([sys.executable, str(GATE), *args], capture_output=True, text=True,
                           encoding="utf-8", env=env or self.env())
        assert r.returncode == 0, f"gate exit {r.returncode}: {r.stderr}\n{r.stdout}"
        try:
            return json.loads(r.stdout)
        except json.JSONDecodeError:
            raise AssertionError(f"gate output not JSON: {r.stdout!r} / {r.stderr!r}")

    def gate_raw(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(GATE), *args], capture_output=True, text=True,
                              encoding="utf-8", env=env or self.env())

    def begin(self, *extra: str) -> dict:
        return self.gate("check-begin", str(self.wt), *extra)

    def record(self, run: int) -> dict:
        return self.gate("check-record", str(self.wt), "--run", str(run))

    def status(self, head: str | None = None, branch: str | None = None) -> dict:
        args = ["status", str(self.main), "--branch", branch or self.branch]
        if head:
            args += ["--head", head]
        return self.gate(*args)

    def state(self) -> dict:
        sys.path.insert(0, str(HOOKS_DIR))
        import _shared  # noqa
        p = self.main / ".ddaro" / "gates" / f"{_shared.branch_enc(self.branch)}.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def write_state(self, state: dict) -> None:
        sys.path.insert(0, str(HOOKS_DIR))
        import _shared  # noqa
        p = self.main / ".ddaro" / "gates" / f"{_shared.branch_enc(self.branch)}.json"
        p.write_text(json.dumps(state, indent=1), encoding="utf-8")

    def run_dir(self, begin_out: dict) -> Path:
        return Path(begin_out["run_dir"])

    def blockers_file(self, begin_out: dict) -> list:
        return json.loads((self.run_dir(begin_out) / "blockers.json").read_text(encoding="utf-8"))

    # --- reports
    def write_run_file(self, begin_out: dict) -> None:
        d = self.run_dir(begin_out)
        (d / "prism-run.json").write_text(json.dumps({"kind": "prism-run", "run_tag": begin_out["run_tag"],
                                                      "head": begin_out["head"], "report_contract": "2"}), encoding="utf-8")

    def write_report(self, begin_out: dict, findings: list, *, lenses_completed=None, meta_over: dict | None = None,
                     raw: str | None = None, path: Path | None = None) -> Path:
        d = self.run_dir(begin_out)
        self.write_run_file(begin_out)
        p = path or (d / "prism-report.json")
        if raw is not None:
            p.write_text(raw, encoding="utf-8")
            return p
        p.write_text(json.dumps(make_report(begin_out, findings, lenses_completed=lenses_completed, meta_over=meta_over),
                                indent=1, ensure_ascii=False), encoding="utf-8")
        return p


def make_report(begin_out: dict, findings: list, *, lenses_completed=None, meta_over: dict | None = None) -> dict:
    """A contract-2 report for the run `begin_out` describes."""
    scope = "rejudge" if begin_out["scope"] == "rejudge" else "diff"
    blocker_ids = [f"blocker:{b['id']}" for b in begin_out.get("open_blockers") or []]
    cand_ids = sorted({f["candidate_id"] for f in findings if not f["candidate_id"].startswith("blocker:")} | set(blocker_ids))
    rng = begin_out.get("range")
    meta = {
        "target": f"diff {rng}" if scope == "diff" else f"rejudge {len(blocker_ids)} blocker(s)",
        "mode": "default", "lenses": "defect", "engines": ["claude"], "checklist": None,
        "timestamp": "2026-10-20T00:00:00.000Z",
        "counts": {"records": len(findings),
                   "supported": sum(f["status"] == "SUPPORTED" for f in findings),
                   "reproduced": sum(f["status"] == "REPRODUCED" for f in findings),
                   "suspected": sum(f["status"] == "SUSPECTED" for f in findings),
                   "rejected": sum(f["status"] == "REJECTED" for f in findings)},
        "ideas": {"ran": False, "reason": "--no-ideas", "outcome": "skipped"},
        "report_contract": "2", "record_version": "2.1", "run_tag": begin_out["run_tag"], "head": begin_out["head"],
        "base": rng.split(".")[0] if rng else None, "range": rng, "scope": scope, "lens_set": "defect",
        "lenses_requested": [] if scope == "rejudge" else list(DEFECT),
        "lenses_completed": [] if scope == "rejudge" else (list(DEFECT) if lenses_completed is None else list(lenses_completed)),
        "degraded_angles": [], "candidate_ids": cand_ids, "tree_changed": False, "unmapped_findings": [],
    }
    if meta_over:
        meta.update(meta_over)
    for i, f in enumerate(findings, 1):
        f.setdefault("id", f"PRISM-{i:03d}")
        f.setdefault("_evidence_check", {"checked": True, "quote_found": f["status"] in ("SUPPORTED", "REPRODUCED", "REJECTED"),
                                         "quote_lines": [], "rev": begin_out["head"]})
        f["_evidence_check"].setdefault("rev", begin_out["head"])
        f.setdefault("grounding_failed", False)
    return {"meta": meta, "findings": findings, "ideas": []}


def finding(cid: str, status: str = "SUPPORTED", severity: str = "MED", file: str = "src/app.js", lines: str = "2",
            symbol: str = "a", category: str = "correctness", claim: str = "returns a constant",
            evidence=None, quote_lines=None, quote_found=None, grounding_failed: bool = False, missing=None) -> dict:
    ev = evidence if evidence is not None else [f"{file}:{lines} — return 1;"]
    rec = {"candidate_id": cid, "status": status, "severity": severity, "file": file, "lines": lines, "symbol": symbol,
           "category": category, "claim": claim, "evidence": ev, "missing": missing, "grounding_failed": grounding_failed}
    if quote_lines is not None or quote_found is not None:
        rec["_evidence_check"] = {"checked": True,
                                  "quote_found": bool(quote_found) if quote_found is not None else bool(quote_lines),
                                  "quote_lines": list(quote_lines or [])}
    return rec
