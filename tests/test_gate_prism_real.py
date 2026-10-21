"""End-to-end against the INSTALLED prism 0.6.0 scripts (no model): the gate's
check-begin hands prism its arguments, `assemble-report.js begin` accepts them,
`parse-findings.js` / `verify-evidence.js --rev` / `assemble-report.js finish`
produce the contract-2 report, and check-record judges it. Skipped when prism
0.6.0 or node is not installed (CI).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

from gate_helpers import DEFECT, GateRepo  # noqa: E402

import _shared  # noqa: E402

REAL_PRISM = None
ip, _err = _shared.prism_install_path()
if ip is not None and (ip / "skills" / "prism" / "assemble-report.js").is_file():
    REAL_PRISM = ip / "skills" / "prism"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(REAL_PRISM is None or NODE is None, reason="prism 0.6.0 + node required")


def node(*args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run([NODE, *map(str, args)], cwd=cwd, capture_output=True, text=True, encoding="utf-8")


def lens_file(run_dir: Path, angle: str, lines: list) -> None:
    body = "\n".join(lines)
    (run_dir / f"pass1.claude.{angle}.txt").write_text(f"<<<PRISM-FINDINGS v1>>>\n{body}\n<<<END>>>\n", encoding="utf-8")
    r = node(REAL_PRISM / "parse-findings.js", run_dir / f"pass1.claude.{angle}.txt", angle)
    assert r.returncode == 0, r.stderr
    (run_dir / f"pass1.claude.{angle}.txt.json").write_text(r.stdout, encoding="utf-8")


def record(cid, status, file, lines, symbol, claim, quote, severity="MED", category="correctness"):
    return {"id": f"PRISM-{cid}", "candidate_id": cid, "unpinned": False, "file": file, "lines": lines, "symbol": symbol,
            "category": category, "severity": severity, "status": status, "missing": None, "degraded": False,
            "claim": claim, "preconditions": [], "execution_path": [f"{symbol}()"],
            "evidence": [f"{file}:{lines} — {quote}"], "suggested_fix": "x", "checklist_ref": None, "chain": None,
            "reproduction": {"status": "NOT_RUN"}, "confidence": {"model_agreement": "1/5", "evidence_strength": "MEDIUM", "label": "HIGH"}}


def prism_run(g: GateRepo, b: dict, lens_findings: dict, candidates: dict, records: list) -> dict:
    """Drive prism's scripts the way SKILL.md's gate run does. Returns the report."""
    run_dir = Path(b["run_dir"])
    repo = g.wt.resolve().as_posix()
    begin = [REAL_PRISM / "assemble-report.js", "begin", "--out", run_dir, "--repo", repo, "--run-tag", b["run_tag"],
             "--head", b["head"], "--blockers", run_dir / "blockers.json", "--lenses", "defect"]
    if b["scope"] != "rejudge":
        begin[9:9] = []
        begin += ["--diff", b["range"]]
    r = node(*begin)
    assert r.returncode == 0, f"begin: {r.stderr}"
    assert (run_dir / "prism-run.json").is_file()
    if b["scope"] != "rejudge":
        for angle in DEFECT:
            lens_file(run_dir, angle, lens_findings.get(angle, []))
        (run_dir / "candidates.json").write_text(json.dumps(candidates), encoding="utf-8")
    (run_dir / "records.json").write_text(json.dumps(records), encoding="utf-8")
    r = node(REAL_PRISM / "verify-evidence.js", run_dir / "records.json", repo, "--rev", b["head"])
    assert r.returncode == 0, f"verify-evidence: {r.stderr}"
    (run_dir / "checked.json").write_text(r.stdout, encoding="utf-8")
    finish = [REAL_PRISM / "assemble-report.js", "finish", "--out", run_dir, "--repo", repo, "--run-tag", b["run_tag"],
              "--head", b["head"], "--blockers", run_dir / "blockers.json"]
    if b["scope"] != "rejudge":
        finish += ["--range", b["range"], "--lenses", ",".join(DEFECT)]
    r = node(*finish)
    assert r.returncode == 0, f"finish: {r.stderr}\n{r.stdout}"
    return json.loads((run_dir / "prism-report.json").read_text(encoding="utf-8"))


def test_real_prism_block_fix_pass(tmp_path):
    g = GateRepo(tmp_path)
    # point the fake install at the real prism so rule 1 reads the real contract file
    (g.cfg_dir / "plugins" / "installed_plugins.json").write_text(json.dumps(
        {"version": 2, "plugins": {"prism@haroom_plugins": {"version": "0.6.0", "installPath": str(REAL_PRISM.parent.parent)}}}), encoding="utf-8")
    g.commit("src/app.js", "function a() {\n  return token;\n}\n", "bad")
    b = g.begin()
    assert b["outcome"] == "OK"
    rep = prism_run(g, b,
                    {"security": ["HIGH | src/app.js:2@a | returns the raw token -> hash it"]},
                    {"security#1": "c1"},
                    [record("c1", "SUPPORTED", "src/app.js", "2", "a", "returns the raw token", "return token;", severity="HIGH", category="security")])
    assert rep["meta"]["report_contract"] == "2" and rep["meta"]["run_tag"] == b["run_tag"]
    assert rep["meta"]["lenses_completed"] == DEFECT and rep["meta"]["candidate_ids"] == ["c1"]
    assert rep["findings"][0]["_evidence_check"]["quote_lines"] == [2]
    r = g.record(b["run"])
    assert r["outcome"] == "BLOCK", r["summary"]
    bid = r["new_blockers"][0]
    # fix it; the blocker goes to prism, the Evidence pass says REJECTED quoting the fixed line
    g.commit("src/app.js", "function a() {\n  return hash(token);\n}\n", "fix")
    b2 = g.begin()
    assert b2["scope"] == "recheck" and [x["id"] for x in g.blockers_file(b2)] == [bid]
    rep2 = prism_run(g, b2, {}, {},
                     [record(f"blocker:{bid}", "REJECTED", "src/app.js", "2", "a", "returns the raw token", "return hash(token);",
                             severity="HIGH", category="security")])
    assert rep2["meta"]["candidate_ids"] == [f"blocker:{bid}"]
    rec = rep2["findings"][0]
    assert rec["status"] == "REJECTED" and rec["_evidence_check"]["quote_found"] is True and rec["_evidence_check"]["quote_lines"] == [2]
    r2 = g.record(b2["run"])
    assert r2["outcome"] == "PASS" and r2["closed_blockers"][0]["closed_by"] == "fixed", r2["summary"]
    assert g.status()["mergeable"] is True
    # a second begin on the same folder is refused by prism itself
    r = node(REAL_PRISM / "assemble-report.js", "begin", "--out", b2["run_dir"], "--repo", g.wt.resolve().as_posix(),
             "--run-tag", b2["run_tag"], "--head", b2["head"], "--diff", b2["range"], "--blockers", Path(b2["run_dir"]) / "blockers.json", "--lenses", "defect")
    assert r.returncode == 1 and "prism-run.json" in r.stderr


def test_real_prism_rejudge_and_lens_fallback(tmp_path):
    g = GateRepo(tmp_path)
    (g.cfg_dir / "plugins" / "installed_plugins.json").write_text(json.dumps(
        {"version": 2, "plugins": {"prism@haroom_plugins": {"version": "0.6.0", "installPath": str(REAL_PRISM.parent.parent)}}}), encoding="utf-8")
    g.commit("src/app.js", "function a() {\n  return token;\n}\n", "bad")
    b = g.begin()
    rep = prism_run(g, b, {"state": ["MED | src/app.js:2@a | leaks token -> hash"]}, {"state#1": "c1"},
                    [record("c1", "SUPPORTED", "src/app.js", "2", "a", "leaks token", "return token;")])
    bid = g.record(b["run"])["new_blockers"][0]
    # same head, blocker open -> rejudge with prism: still SUPPORTED
    b2 = g.begin()
    assert b2["scope"] == "rejudge" and b2["range"] is None
    rep2 = prism_run(g, b2, {}, {}, [record(f"blocker:{bid}", "SUPPORTED", "src/app.js", "2", "a", "leaks token", "return token;")])
    assert rep2["meta"]["scope"] == "rejudge" and rep2["meta"]["range"] is None
    r2 = g.record(b2["run"])
    assert r2["outcome"] == "BLOCK" and r2["errors"] == []
    # a lens that fell back -> 4/5 completed -> ERROR, finding still a blocker
    g.commit("src/app.js", "function a() {\n  return token;\n  more();\n}\n", "more")
    b3 = g.begin()
    run_dir = Path(b3["run_dir"])
    repo = g.wt.resolve().as_posix()
    r = node(REAL_PRISM / "assemble-report.js", "begin", "--out", run_dir, "--repo", repo, "--run-tag", b3["run_tag"],
             "--head", b3["head"], "--diff", b3["range"], "--blockers", run_dir / "blockers.json", "--lenses", "defect")
    assert r.returncode == 0, r.stderr
    for angle in DEFECT[:4]:
        lens_file(run_dir, angle, ["MED | src/app.js:3@a | more() unchecked -> check"] if angle == "correctness" else [])
    (run_dir / "pass1.claude.testability.txt").write_text("[fallback: claude-unavailable]\n", encoding="utf-8")
    rr = node(REAL_PRISM / "parse-findings.js", run_dir / "pass1.claude.testability.txt", "testability")
    (run_dir / "pass1.claude.testability.txt.json").write_text(rr.stdout, encoding="utf-8")
    (run_dir / "candidates.json").write_text(json.dumps({"correctness#1": "c1"}), encoding="utf-8")
    recs = [record("c1", "SUPPORTED", "src/app.js", "3", "a", "more() unchecked", "more();"),
            record(f"blocker:{bid}", "SUPPORTED", "src/app.js", "2", "a", "leaks token", "return token;")]
    (run_dir / "records.json").write_text(json.dumps(recs), encoding="utf-8")
    rr = node(REAL_PRISM / "verify-evidence.js", run_dir / "records.json", repo, "--rev", b3["head"])
    (run_dir / "checked.json").write_text(rr.stdout, encoding="utf-8")
    rr = node(REAL_PRISM / "assemble-report.js", "finish", "--out", run_dir, "--repo", repo, "--run-tag", b3["run_tag"],
              "--head", b3["head"], "--blockers", run_dir / "blockers.json", "--range", b3["range"], "--lenses", ",".join(DEFECT))
    assert rr.returncode == 0, rr.stderr
    rep3 = json.loads((run_dir / "prism-report.json").read_text(encoding="utf-8"))
    assert len(rep3["meta"]["lenses_completed"]) == 4 and rep3["meta"]["degraded_angles"][0]["angle"] == "testability"
    r3 = g.record(b3["run"])
    assert r3["outcome"] == "ERROR" and any("렌즈 미완료" in e for e in r3["errors"])
    assert len(r3["new_blockers"]) == 1 and len(g.status()["open_blockers"]) == 2
