"""Tests for hooks/gate.py: state and cycles, run rules, judgement rules, carry-over.

Follows "테스트 계획 (S2)" of docs/design/merge-gate.md. Every test drives the
real script against a throwaway repository (tests/gate_helpers.py); the fake
`gh` answers merge confirmations and reports are written the way prism 0.6.0's
`assemble-report.js finish` writes them (contract 2).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

from gate_helpers import DEFECT, GateRepo, finding, make_report  # noqa: E402

import _shared  # noqa: E402
import gate  # noqa: E402


@pytest.fixture
def g(tmp_path):
    return GateRepo(tmp_path)


def pass_run(g: GateRepo, rel="src/app.js", content="function a() {\n  return 2;\n}\n", msg="c"):
    """Commit, check-begin, PASS report, check-record. Returns (head, begin_out)."""
    head = g.commit(rel, content, msg)
    b = g.begin()
    assert b["outcome"] == "OK", b
    g.write_report(b, [])
    r = g.record(b["run"])
    assert r["outcome"] == "PASS", r
    return head, b


def blocked_run(g: GateRepo, content="function a() {\n  return 3;\n}\n", claim="returns 3", lines="2", sev="MED", quote_lines=(2,)):
    """Commit `content`, record a run with one SUPPORTED finding -> blocker. Returns (head, blocker id, begin_out)."""
    head = g.commit("src/app.js", content, "bad")
    b = g.begin()
    assert b["outcome"] == "OK", b
    g.write_report(b, [finding("c1", "SUPPORTED", sev, lines=lines, claim=claim, quote_lines=list(quote_lines),
                               evidence=[f"src/app.js:{lines} \u2014 {content.splitlines()[int(lines.split('-')[0]) - 1].strip()}"])])
    r = g.record(b["run"])
    assert r["outcome"] == "BLOCK", r
    assert len(r["new_blockers"]) == 1
    return head, r["new_blockers"][0], b


def rejected(bid: str, file="src/app.js", lines="2", quote="return compute();", quote_lines=(2,), claim="returns 3", quote_found=True):
    return finding(f"blocker:{bid}", "REJECTED", "MED", file=file, lines=lines, claim=claim,
                   evidence=[f"{file}:{lines} \u2014 {quote}"], quote_lines=list(quote_lines), quote_found=quote_found)


# ---------------------------------------------------------------------------
# 상태와 주기
# ---------------------------------------------------------------------------

def test_branch_enc_examples():
    assert _shared.branch_enc("d-busan") == "d-busan.f486a3be"
    enc = _shared.branch_enc("Feat/Login-Page")
    assert enc.startswith("%46eat%2F%4Cogin-%50age.") and len(enc.split(".")[-1]) == 8
    assert _shared.branch_enc("d-busan") != _shared.branch_enc("D-busan")  # case only -> different files


def test_full_pass_then_head_match(g):
    head, b = pass_run(g)
    assert b["scope"] == "full"
    assert b["range"].endswith(head) and len(b["range"].split("...")[0]) == 40
    assert b["run_dir"].startswith(("C:/", "/")) and "\\" not in b["run_dir"]
    assert b["prism_skill_args"].startswith("--diff ") and "--no-ideas" in b["prism_skill_args"]
    s = g.status()
    assert s["mergeable"] is True and s["reason"] == "head_match"


def test_merge_confirm_descendant_bumps_cycle_and_archives(g):
    head, _ = pass_run(g)
    g.gh(list=[{"number": 89, "state": "MERGED", "baseRefName": "master", "headRefName": "d-busan", "headRefOid": head}])
    head2 = g.commit("src/app.js", "x\n", "next pr")
    b = g.begin()
    assert b["outcome"] == "OK"
    st = g.state()
    assert st["cycle"] == 2 and st["closes"][0]["pr"] == 89
    assert all(r["cycle"] == 2 for r in st["runs"])
    arch = json.loads((g.main / ".ddaro" / "gates" / "archive" / "d-busan.f486a3be" / "cycle-1.json").read_text(encoding="utf-8"))
    assert [r["run"] for r in arch["runs"]] == [1]
    assert b["scope"] == "full"  # a new cycle has no judged run


def test_merge_confirm_rejects_old_pr_other_base_and_closed_numbers(g):
    base_sha = g.head(g.main)  # a commit from before this cycle's runs
    head, _ = pass_run(g)
    g.gh(list=[{"number": 50, "state": "MERGED", "baseRefName": "master", "headRefName": "d-busan", "headRefOid": base_sha},
               {"number": 51, "state": "MERGED", "baseRefName": "develop", "headRefName": "d-busan", "headRefOid": head}])
    g.commit("src/app.js", "y\n", "c2")
    g.begin()
    assert g.state()["cycle"] == 1
    st = g.state()
    st["closes"].append({"cycle": 0, "pr": 52})
    g.write_state(st)
    g.gh(list=[{"number": 52, "state": "MERGED", "baseRefName": "master", "headRefName": "d-busan", "headRefOid": head}])
    g.commit("src/app.js", "z\n", "c3")
    g.begin()
    assert g.state()["cycle"] == 1


def test_merge_confirm_offline_keeps_cycle(g):
    head, _ = pass_run(g)
    g.gh(fail="connection refused")
    g.commit("src/app.js", "y\n", "c2")
    b = g.begin()
    assert g.state()["cycle"] == 1
    assert any("머지 확인 못 함" in n for n in b["notes"])


def test_close_merged_command_and_manual_close(g):
    head, _ = pass_run(g)
    g.gh(view={"89": {"number": 89, "state": "MERGED", "baseRefName": "master", "headRefName": "d-busan", "headRefOid": head}})
    out = g.gate("close", str(g.main), "d-busan", "--merged", "--pr", "89")
    assert out["closed"] is True and g.state()["cycle"] == 2
    out = g.gate("close", str(g.main), "d-busan", "--merged", "--pr", "90")
    assert out["closed"] is False
    out = g.gate("close", str(g.main), "d-busan")
    assert out["closed"] is True and g.state()["cycle"] == 3


def test_retire_only_when_branch_is_gone(g):
    pass_run(g)
    out = g.gate("retire", str(g.main), "d-busan")
    assert out["retired"] is False
    g.git("worktree", "remove", "--force", str(g.wt), cwd=g.main)
    g.git("branch", "-D", "d-busan", cwd=g.main)
    out = g.gate("retire", str(g.main), "d-busan")
    assert out["retired"] is True
    assert not (g.main / ".ddaro" / "gates" / "d-busan.f486a3be.json").exists()
    assert Path(out["archived_to"]).exists()


def test_missing_baseline_commit_forces_full(g):
    head, _ = pass_run(g)
    st = g.state()
    st["runs"][0]["head"] = "0" * 40
    g.write_state(st)
    g.commit("src/app.js", "y\n", "c2")
    b = g.begin()
    assert b["scope"] == "full" and any("not an ancestor" in n or "missing" in n for n in b["notes"])


def test_lock_held_by_other_process_refuses(g):
    pass_run(g)
    lock = g.main / ".ddaro" / "gates" / "d-busan.f486a3be.lock"
    holder = subprocess.Popen([sys.executable, "-c", f"""
import sys, time; sys.path.insert(0, {str(gate.Path(gate.__file__).parent)!r})
from _shared import file_lock
with file_lock({str(lock)!r}, 1):
    print('held', flush=True); time.sleep(8)
"""], stdout=subprocess.PIPE, text=True)
    assert holder.stdout.readline().strip() == "held"
    try:
        g.commit("src/app.js", "y\n", "c2")
        out = g.begin()
        assert out["outcome"] == "REFUSED" and "locked by pid" in out["message"]
    finally:
        holder.kill()
        holder.wait()
    out = g.begin()
    assert out["outcome"] == "OK"  # released after the holder died


def test_no_lock_held_during_verify(g):
    """The verify command itself acquires the branch lock: it must succeed."""
    lock = g.main / ".ddaro" / "gates" / "d-busan.f486a3be.lock"
    probe = g.tmp / "probe.py"
    probe.write_text(f"""
import sys; sys.path.insert(0, {str(gate.Path(gate.__file__).parent)!r})
from _shared import file_lock
with file_lock({str(lock)!r}, 1): pass
""", encoding="utf-8")
    g.write_verify({"commands": [], "default": f'"{sys.executable}" "{probe.as_posix()}"'})
    g.commit("src/app.js", "y\n", "c1")
    b = g.begin()
    assert b["outcome"] == "OK", b


def test_unknown_fields_preserved_and_newer_schema_refused(g):
    pass_run(g)
    st = g.state()
    st["future_top"] = {"x": 1}
    st["runs"][0]["future_run"] = "keep me"
    g.write_state(st)
    g.commit("src/app.js", "y\n", "c2")
    b = g.begin()
    g.write_report(b, [])
    g.record(b["run"])
    st2 = g.state()
    assert st2["future_top"] == {"x": 1} and st2["runs"][0]["future_run"] == "keep me"
    st2["schema"] = 99
    g.write_state(st2)
    s = g.status()
    assert s["mergeable"] is False and "ddaro를 업데이트하라" in s["next"]
    g.commit("src/app.js", "z\n", "c3")
    assert "ddaro를 업데이트하라" in g.begin()["message"]


def test_unreadable_state_and_reset(g):
    pass_run(g)
    p = g.main / ".ddaro" / "gates" / "d-busan.f486a3be.json"
    p.write_text("{not json", encoding="utf-8")
    s = g.status()
    assert s["reason"] == "unreadable" and "reset" in s["next"]
    out = g.gate("reset", str(g.main), "d-busan")
    assert out["reset"] is True and not p.exists()
    g.commit("src/app.js", "y\n", "c2")
    assert g.begin()["scope"] == "full"
    # a readable file is not reset without --force
    out = g.gate("reset", str(g.main), "d-busan")
    assert out["outcome"] == "REFUSED"


def test_last_judged_is_highest_run_number_late_block(g):
    """run 5 abandoned, run 6 PASS, then run 5's folder gets a BLOCK report."""
    g.commit("src/app.js", "a\n", "c1")
    b5 = g.begin()                      # pending, never recorded
    g.commit("src/app.js", "b\n", "c2")
    b6 = g.begin()                      # records run 5 as abandoned
    assert any(f["run"] == b5["run"] and f["error"] == "abandoned" for f in b6["finalized"])
    assert b6["scope"] == "full"        # previous run abandoned
    g.write_report(b6, [])
    assert g.record(b6["run"])["outcome"] == "PASS"
    assert g.status()["mergeable"] is True
    g.write_report(b5, [finding("c1", "SUPPORTED", "HIGH", claim="late block", quote_lines=[1])])
    r5 = g.record(b5["run"])
    assert r5["outcome"] == "BLOCK" and r5["finalized_late"] is True
    s = g.status()
    assert s["mergeable"] is False and s["reason"] == "open_blockers"
    assert s["last_judged"]["run"] == b6["run"]      # judgement still run 6 (highest number)


def test_late_block_recorded_before_run6_report_carries_into_run6(g):
    g.commit("src/app.js", "a\n", "c1")
    b5 = g.begin()
    g.commit("src/app.js", "b\n", "c2")
    b6 = g.begin()
    assert g.blockers_file(b6) == []
    g.write_report(b5, [finding("c1", "SUPPORTED", "MED", claim="late block", quote_lines=[1])])
    r5 = g.record(b5["run"])
    assert r5["outcome"] == "BLOCK"
    bid = r5["new_blockers"][0]
    g.write_report(b6, [])
    r6 = g.record(b6["run"])
    assert r6["outcome"] == "BLOCK" and bid in r6["carried_blockers"]
    assert bid in [x["id"] for x in r6["open_blockers"]]
    assert g.status()["mergeable"] is False


def test_abandoned_then_report_finalizes_once(g):
    g.commit("src/app.js", "a\n", "c1")
    b5 = g.begin()
    g.commit("src/app.js", "b\n", "c2")
    g.begin()
    assert g.record(b5["run"])["outcome"] == "ERROR"            # abandoned, no report yet
    assert g.state()["runs"][0]["error"] == "abandoned"
    g.write_report(b5, [finding("c1", "SUPPORTED", "MED", claim="late", quote_lines=[1])])
    r = g.record(b5["run"])
    assert r["outcome"] == "BLOCK" and r["finalized_late"] is True
    r2 = g.record(b5["run"])
    assert r2["outcome"] == "BLOCK" and r2["new_blockers"] == r["new_blockers"]
    assert len(g.state()["blockers"]) == 1


def test_late_error_run_keeps_its_high_finding(g):
    g.commit("src/app.js", "a\n", "c1")
    b5 = g.begin()
    g.commit("src/app.js", "b\n", "c2")
    b6 = g.begin()
    g.write_report(b6, [])
    assert g.record(b6["run"])["outcome"] == "PASS"
    g.write_report(b5, [finding("c1", "SUPPORTED", "HIGH", claim="late high", quote_lines=[1])], lenses_completed=DEFECT[:4])
    r5 = g.record(b5["run"])
    assert r5["outcome"] == "ERROR" and r5["finalized_late"] is True
    assert len(r5["new_blockers"]) == 1
    s = g.status()
    assert s["mergeable"] is False and s["reason"] == "open_blockers"
    g.commit("src/app.js", "c\n", "c3")
    b7 = g.begin()
    assert [x["id"] for x in g.blockers_file(b7)] == r5["new_blockers"]


def test_truncated_report_is_abandoned_then_finalized(g):
    g.commit("src/app.js", "a\n", "c1")
    b5 = g.begin()
    g.write_report(b5, [], raw="")
    g.commit("src/app.js", "b\n", "c2")
    b6 = g.begin()
    assert any(f["run"] == b5["run"] and f["error"] == "abandoned" for f in b6["finalized"])
    g.write_report(b5, [], raw='{"meta": {"run_tag": "x"')
    assert g.record(b5["run"])["outcome"] == "ERROR"          # still abandoned (not JSON)
    g.write_report(b5, [])
    r = g.record(b5["run"])
    assert r["outcome"] == "PASS" and r["finalized_late"] is True


def test_run_in_closed_cycle_is_stale_and_only_archive_changes(g):
    head7 = g.commit("src/app.js", "a\n", "c1")
    b7 = g.begin()
    g.gh(list=[{"number": 7, "state": "MERGED", "baseRefName": "master", "headRefName": "d-busan", "headRefOid": head7}])
    g.commit("src/app.js", "b\n", "c2")
    b8 = g.begin()                       # records run 7 abandoned, then bumps the cycle
    assert g.state()["cycle"] == 2
    g.write_report(b7, [finding("c1", "SUPPORTED", "HIGH", claim="late", quote_lines=[1])])
    before = g.state()
    r = g.record(b7["run"])
    assert r["outcome"] == "STALE" and "주기가 이미 닫힘" in r["message"]
    assert r["archived_outcome"] == "BLOCK"
    after = g.state()
    assert after["runs"] == before["runs"] and after["blockers"] == before["blockers"]
    arch = json.loads((g.main / ".ddaro" / "gates" / "archive" / "d-busan.f486a3be" / "cycle-1.json").read_text(encoding="utf-8"))
    assert arch["runs"][0]["outcome"] == "BLOCK" and arch["runs"][0]["finalized_late"] is True
    r2 = g.record(b7["run"])
    assert r2["outcome"] == "STALE" and r2["archived_outcome"] == "BLOCK"
    assert g.status()["open_blockers"] == []


# ---------------------------------------------------------------------------
# 실행 규칙
# ---------------------------------------------------------------------------

def test_baseline_ignores_verify_block_stale_error_runs(g):
    head1, b1 = pass_run(g)
    g.write_verify({"commands": [], "default": "false"})
    head2 = g.commit("src/app.js", "bad\n", "c2")
    b2 = g.begin()
    assert b2["outcome"] == "BLOCK" and "테스트 실패" in b2["message"]
    g.write_verify({"commands": [], "default": "true"})
    head3 = g.commit("src/app.js", "ok\n", "c3")
    b3 = g.begin()
    assert b3["scope"] == "recheck" and b3["range"] == f"{head1}..{head3}"   # verify BLOCK run is not a baseline


def test_full_on_rebase_base_merge_and_flag(g):
    head1, _ = pass_run(g)
    g.commit("src/app.js", "y\n", "c2")
    assert g.begin()["scope"] == "recheck"
    g.git("commit", "--amend", "-q", "--no-edit", "-m", "amended")
    b = g.begin()
    assert b["scope"] == "full"
    g.write_report(b, [])
    g.record(b["run"])
    g.commit("src/app.js", "z\n", "c3")
    assert g.begin("--full")["scope"] == "full"
    g.base_commit("other.txt", "base change\n")
    g.git("fetch", "-q", "origin")
    g.git("merge", "-q", "--no-edit", "origin/master")
    b = g.begin()
    assert b["scope"] == "full" and any("base merged" in n for n in b["notes"])


def test_same_head_with_open_blockers_is_rejudge(g):
    pass_run(g)
    head, bid, b = blocked_run(g)
    b2 = g.begin()
    assert b2["scope"] == "rejudge" and b2["range"] is None
    assert "--diff" not in b2["prism_skill_args"] and "--blockers" in b2["prism_skill_args"]
    assert [x["id"] for x in g.blockers_file(b2)] == [bid]
    g.write_report(b2, [finding(f"blocker:{bid}", "SUPPORTED", "MED", claim="returns 3", quote_lines=[2])])
    r = g.record(b2["run"])
    assert r["outcome"] == "BLOCK" and r["errors"] == []


def test_same_head_no_blockers_refused_then_verify_only(g):
    head, _ = pass_run(g)
    out = g.begin()
    assert out["outcome"] == "REFUSED" and "새 커밋 없음" in out["message"]
    # tests fail at the judged head -> verify-only run BLOCK -> status verify_failed
    g.write_verify({"commands": [], "default": "false"})
    # a REFUSED begin does not record a verify run, so simulate the failing run via a verify-only path:
    st = g.state()
    st["runs"].append({"run": 50, "cycle": 1, "kind": "verify", "head": head, "outcome": "BLOCK", "scope": "verify"})
    st["next_run"] = 51
    g.write_state(st)
    assert g.status()["reason"] == "verify_failed"
    g.write_verify({"commands": [], "default": "true"})
    out = g.begin()
    assert out["outcome"] == "PASS" and out["scope"] == "verify" and "prism_skill_args" not in out
    assert g.status()["mergeable"] is True and g.status()["reason"] == "head_match"


def test_verify_command_selection(g):
    g.write_verify({"commands": [{"pattern": "**/*.js", "run": "echo js"}, {"pattern": "**/*.py", "run": "echo py"},
                                 {"pattern": "docs/**", "run": "echo js"}], "default": "echo default"})
    g.commit("src/app.js", "a\n", "c1")
    g.commit("lib/x.py", "b\n", "c2")
    g.commit("docs/n.md", "c\n", "c3")
    g.commit("other.txt", "d\n", "c4")
    b = g.begin()
    assert b["verify"]["commands"] == ["echo js", "echo py", "echo default"]
    g.write_verify({"commands": [{"pattern": "**/*.js", "run": "echo js"}]})
    g.commit("other.txt", "e\n", "c5")
    b = g.begin()
    assert b["outcome"] == "BLOCK" and "default" in b["message"]


def test_verify_missing_config_blocks_unless_none(g):
    g.write_verify(None)
    g.commit("src/app.js", "a\n", "c1")
    b = g.begin()
    assert b["outcome"] == "BLOCK" and "테스트 명령 미설정" in b["message"]
    g.write_cfg(gate_verify="none")
    b = g.begin()
    assert b["outcome"] == "OK" and "none" in b["verify"]["note"]


def test_verify_timeout_kills_and_blocks(g):
    g.write_verify({"commands": [], "default": "sleep 30"})
    g.commit("src/app.js", "a\n", "c1")
    t0 = time.monotonic()
    b = g.gate("check-begin", str(g.wt), env=g.env(DDARO_GATE_VERIFY_BUDGET="2"))
    assert b["outcome"] == "BLOCK" and "시간 초과" in b["message"]
    assert time.monotonic() - t0 < 25


@pytest.mark.skipif(os.name != "nt", reason="Git Bash lookup is Windows-only")
def test_bash_path_is_git_bash_not_system32():
    sh, err = gate.bash_path()
    assert err is None and sh.lower().endswith("bash.exe") and "system32" not in sh.lower()


def test_verify_that_changes_tree_is_refused_and_recorded(g):
    head1, _ = pass_run(g)
    g.write_verify({"commands": [], "default": "echo changed >> src/app.js"})
    head2 = g.commit("src/app.js", "y\n", "c2")
    b = g.begin()
    assert b["outcome"] == "REFUSED" and "테스트가 트리를 바꿈" in b["message"]
    run = [r for r in g.state()["runs"] if r["run"] == b["run"]][0]
    assert run["kind"] == "verify" and run["outcome"] == "REFUSED"
    g.git("checkout", "--", "src/app.js")
    g.write_verify({"commands": [], "default": "true"})
    b2 = g.begin()
    assert b2["scope"] == "recheck"     # not abandoned, recheck kept


def test_prism_rule1_refusals(g, tmp_path):
    g.commit("src/app.js", "a\n", "c1")
    ip = g.cfg_dir / "plugins" / "installed_plugins.json"
    # missing installed_plugins.json
    saved = ip.read_text(encoding="utf-8")
    ip.unlink()
    out = g.begin()
    assert out["outcome"] == "REFUSED" and "prism 0.6.0 이상 필요" in out["message"]
    # no prism entry
    ip.write_text(json.dumps({"plugins": {}}), encoding="utf-8")
    assert "prism 0.6.0 이상 필요" in g.begin()["message"]
    ip.write_text(saved, encoding="utf-8")
    # no report-contract.json (0.5.x)
    rc = g.prism_install / "skills" / "prism" / "report-contract.json"
    rc.unlink()
    assert "prism 0.6.0 이상 필요" in g.begin()["message"]
    rc.write_text(json.dumps({"report_contract": "3"}), encoding="utf-8")
    assert "ddaro를 업데이트하라" in g.begin()["message"]
    rc.write_text(json.dumps({"report_contract": "2"}), encoding="utf-8")
    assert g.begin()["outcome"] == "OK"
    assert "0.4.2" not in str(g.state()["runs"][0])   # decoy cache version never consulted


def test_refused_on_dirty_detached_and_lock_mismatch(g):
    g.commit("src/app.js", "a\n", "c1")
    (g.wt / "src" / "app.js").write_text("dirty\n", encoding="utf-8")
    assert "dirty" in g.begin()["message"]
    g.git("checkout", "--", "src/app.js")
    (g.wt / ".ddaro" / "LOCK").write_text("branch=d-seoul\n", encoding="utf-8")
    assert "LOCK" in g.begin()["message"]
    (g.wt / ".ddaro" / "LOCK").write_text("branch=d-busan\n", encoding="utf-8")
    assert g.begin()["outcome"] == "OK"
    g.git("checkout", "-q", "--detach")
    assert "detached" in g.begin()["message"]


def test_run_dir_and_range_formats(g):
    head = g.commit("src/app.js", "a\n", "c1")
    b = g.begin()
    assert "\\" not in b["run_dir"] and Path(b["run_dir"]).is_dir()
    base, sep, h = b["range"].partition("...")
    assert len(base) == 40 and h == head and "HEAD" not in b["range"]
    assert "@" not in b["run_tag"] and "#" not in b["run_tag"] and len(b["run_tag"]) <= 64


# ---------------------------------------------------------------------------
# 판정 규칙
# ---------------------------------------------------------------------------

def test_report_after_head_moved_is_judged_at_run_head(g):
    head1 = g.commit("src/app.js", "a\n", "c1")
    b = g.begin()
    g.commit("src/app.js", "b\n", "c2")           # HEAD moves after the review finished
    g.write_report(b, [])
    r = g.record(b["run"])
    assert r["outcome"] == "PASS" and r["head"] == head1
    s = g.status()
    assert s["mergeable"] is False and s["reason"] == "stale_pass"     # the new commit is code


def test_tree_changed_is_error_but_findings_become_blockers(g):
    g.commit("src/app.js", "a\n", "c1")
    b = g.begin()
    g.write_report(b, [finding("c1", "SUPPORTED", "MED", claim="x", quote_lines=[1])], meta_over={"tree_changed": True})
    r = g.record(b["run"])
    assert r["outcome"] == "ERROR" and any("리뷰 중 트리가 바뀜" in e for e in r["errors"])
    assert len(r["new_blockers"]) == 1 and g.status()["reason"] == "open_blockers"


def test_scope_mismatch_errors(g):
    g.commit("src/app.js", "a\n", "c1")
    b = g.begin()
    g.write_report(b, [], meta_over={"scope": "rejudge", "range": None})
    assert g.record(b["run"])["outcome"] == "ERROR"
    pass_run(g)
    head, bid, _ = blocked_run(g)
    b2 = g.begin()
    assert b2["scope"] == "rejudge"
    g.write_report(b2, [finding(f"blocker:{bid}", "SUPPORTED", "MED", claim="returns 3", quote_lines=[2])],
                   meta_over={"scope": "diff", "range": f"{head}..{head}"})
    r = g.record(b2["run"])
    assert r["outcome"] == "ERROR" and any("scope" in e for e in r["errors"])


def test_meta_mismatch_run_tag_head_range(g):
    for over, field in (({"run_tag": "other"}, "run_tag"), ({"head": "0" * 40}, "head"), ({"range": "x"}, "range")):
        g.commit("src/app.js", f"{field}\n", f"c-{field}")
        b = g.begin()
        g.write_report(b, [], meta_over=over)
        r = g.record(b["run"])
        assert r["outcome"] == "ERROR" and any(field in e for e in r["errors"]), (field, r["errors"])


def test_candidate_without_record_is_error(g):
    g.commit("src/app.js", "a\n", "c1")
    b = g.begin()
    rep = make_report(b, [finding("c1", "SUPPORTED", "LOW", claim="minor", quote_lines=[1])])
    rep["meta"]["candidate_ids"] = ["c1", "c2"]
    g.write_run_file(b)
    (g.run_dir(b) / "prism-report.json").write_text(json.dumps(rep), encoding="utf-8")
    r = g.record(b["run"])
    assert r["outcome"] == "ERROR" and any("후보 레코드 누락: c2" in e for e in r["errors"])


def test_close_fixed_quote_on_changed_line(g):
    pass_run(g)
    head, bid, _ = blocked_run(g)
    g.commit("src/app.js", "function a() {\n  return compute();\n}\n", "fix")
    b = g.begin()
    g.write_report(b, [rejected(bid)])
    r = g.record(b["run"])
    assert r["outcome"] == "PASS" and r["closed_blockers"][0]["closed_by"] == "fixed"


def test_comment_only_change_does_not_close(g):
    pass_run(g)
    head, bid, _ = blocked_run(g)
    # a comment line added above the quoted line, quoted line unchanged
    g.commit("src/app.js", "function a() {\n  // fixed below\n  return 3;\n}\n", "comment")
    b = g.begin()
    g.write_report(b, [rejected(bid, lines="3", quote="return 3;", quote_lines=[3])])
    r = g.record(b["run"])
    assert r["outcome"] == "BLOCK" and bid in [x["id"] for x in r["open_blockers"]]
    assert bid in r["needs_human"]


def test_trailing_comment_only_does_not_close_real_change_does(g):
    pass_run(g)
    head, bid, _ = blocked_run(g)
    g.commit("src/app.js", "function a() {\n  return 3; // fixed\n}\n", "trailing comment")
    b = g.begin()
    g.write_report(b, [rejected(bid, quote="return 3; // fixed", quote_lines=[2])])
    r = g.record(b["run"])
    assert r["outcome"] == "BLOCK" and bid in r["needs_human"]
    # now a real code change on the same line
    g.commit("src/app.js", "function a() {\n  return safe(3); // fixed\n}\n", "real fix")
    b2 = g.begin()
    g.write_report(b2, [rejected(bid, quote="return safe(3);", quote_lines=[2])])
    r2 = g.record(b2["run"])
    assert r2["outcome"] == "PASS" and r2["closed_blockers"][0]["closed_by"] == "fixed"


def test_grounding_failure_keeps_blocker_head_then_rejudge_closes(g):
    pass_run(g)
    h1, bid, _ = blocked_run(g)
    h2 = g.commit("src/app.js", "function a() {\n  return compute();\n}\n", "fix")
    b = g.begin()
    rec = finding(f"blocker:{bid}", "SUSPECTED", "MED", claim="returns 3", missing="EVIDENCE_PASS_FAILED",
                  grounding_failed=True, quote_found=False)
    g.write_report(b, [rec])
    r = g.record(b["run"])
    assert r["outcome"] == "BLOCK" and r["grounding"]
    blk = [x for x in g.state()["blockers"] if x["id"] == bid][0]
    assert blk["head"] == h1 and blk["open"] is True
    b2 = g.begin()
    assert b2["scope"] == "rejudge"
    g.write_report(b2, [rejected(bid)])
    r2 = g.record(b2["run"])
    assert r2["outcome"] == "PASS" and r2["closed_blockers"][0]["closed_by"] == "fixed" and not r2["needs_human"]


def test_rejected_quoting_comment_brace_or_short_string_stays_open(g):
    pass_run(g)
    h1, bid, _ = blocked_run(g)
    g.commit("src/app.js", "function a() {\n  return 3;\n  // note\n}\nfunction b() {\n  x();\n});\n", "noise")
    b = g.begin()
    cases = [rejected(bid, lines="3", quote="// note", quote_lines=[3]),
             rejected(bid, lines="7", quote="});", quote_lines=[7]),
             rejected(bid, lines="6", quote="x();", quote_lines=[6])]       # 4 chars < 8: quote_lines would be empty
    cases[2]["_evidence_check"]["quote_lines"] = []
    for i, rec in enumerate(cases):
        if i:
            b = g.begin()
            assert b["scope"] == "rejudge"
        g.write_report(b, [rec])
        r = g.record(b["run"])
        assert r["outcome"] == "BLOCK" and bid in [x["id"] for x in r["open_blockers"]], (i, r["summary"])


def test_line_shift_and_rename_follow(g):
    pass_run(g)
    h1, bid, _ = blocked_run(g)
    # insert lines above, change elsewhere; evidence agent re-reports SUPPORTED at the shifted line
    g.commit("src/app.js", "// header\n// header2\nfunction a() {\n  return 3;\n}\nfunction z() { return 0; }\n", "shift")
    b = g.begin()
    g.write_report(b, [finding(f"blocker:{bid}", "SUPPORTED", "MED", lines="4", claim="returns 3", quote_lines=[4])])
    r = g.record(b["run"])
    assert r["outcome"] == "BLOCK"
    blk = [x for x in g.state()["blockers"] if x["id"] == bid][0]
    assert blk["lines"] == "4" and blk["head"] == g.head()
    # rename + fix
    g.git("mv", "src/app.js", "src/main.js")
    (g.wt / "src" / "main.js").write_text("// header\n// header2\nfunction a() {\n  return compute();\n}\nfunction z() { return 0; }\n", encoding="utf-8")
    g.git("add", "-A")
    g.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "rename")
    b2 = g.begin()
    g.write_report(b2, [rejected(bid, file="src/main.js", lines="4", quote_lines=[4])])
    r2 = g.record(b2["run"])
    assert r2["outcome"] == "PASS" and r2["closed_blockers"][0]["closed_by"] == "fixed"


def test_delete_file_closes_when_symbol_gone(g):
    pass_run(g)
    h1, bid, _ = blocked_run(g)
    g.rm_commit("src/app.js")
    g.commit("src/other.js", "function q() {\n  return 9;\n}\n", "other")
    b = g.begin()
    g.write_report(b, [rejected(bid, file="src/other.js", lines="2", quote="return 9;", quote_lines=[])])
    r = g.record(b["run"])
    assert r["outcome"] == "PASS" and r["closed_blockers"][0]["closed_by"] == "removed"


def test_delete_file_but_symbol_elsewhere_stays_open(g):
    pass_run(g)
    h1, bid, _ = blocked_run(g)
    g.rm_commit("src/app.js")
    g.commit("src/other.js", "function a() {\n  return 3;\n}\n", "moved")
    b = g.begin()
    g.write_report(b, [rejected(bid, file="src/other.js", lines="2", quote="return 3;", quote_lines=[])])
    r = g.record(b["run"])
    assert r["outcome"] == "BLOCK"


def test_blocker_record_missing_in_diff_run_is_not_error_but_block(g):
    pass_run(g)
    h1, bid, _ = blocked_run(g)
    g.commit("src/app.js", "function a() {\n  return compute();\n}\n", "fix")
    b = g.begin()
    g.write_report(b, [])
    r = g.record(b["run"])
    assert r["outcome"] == "BLOCK" and r["errors"] == [] and bid in [x["id"] for x in r["open_blockers"]]


def test_python_indent_change_counts_as_changed_line(g):
    pass_run(g)
    g.commit("lib/x.py", "def f():\n    if a:\n        return 1\n", "py")
    b = g.begin()
    g.write_report(b, [finding("c1", "SUPPORTED", "MED", file="lib/x.py", lines="3", symbol="f", claim="wrong indent",
                               evidence=["lib/x.py:3 \u2014 return 1"], quote_lines=[3])])
    r = g.record(b["run"])
    bid = r["new_blockers"][0]
    g.commit("lib/x.py", "def f():\n    if a:\n        pass\n    return 1\n", "dedent")
    b2 = g.begin()
    g.write_report(b2, [rejected(bid, file="lib/x.py", lines="4", quote="    return 1", quote_lines=[4])])
    r2 = g.record(b2["run"])
    assert r2["outcome"] == "PASS" and r2["closed_blockers"][0]["closed_by"] == "fixed"


def test_blocker_grounding_failure_no_duplicate_item(g):
    pass_run(g)
    h1, bid, _ = blocked_run(g)
    g.commit("src/app.js", "function a() {\n  return 4;\n}\n", "c")
    b = g.begin()
    g.write_report(b, [finding(f"blocker:{bid}", "SUSPECTED", "MED", claim="returns 3", missing="EVIDENCE_PASS_FAILED",
                               grounding_failed=True, quote_found=False)])
    r = g.record(b["run"])
    assert r["outcome"] == "BLOCK" and r["new_blockers"] == [] and len(r["open_blockers"]) == 1


def test_error_run_supported_blocker_record_makes_no_new_item(g):
    pass_run(g)
    h1, bid, _ = blocked_run(g)
    g.commit("src/app.js", "function a() {\n  return 4;\n}\n", "c")
    b = g.begin()
    g.write_report(b, [finding(f"blocker:{bid}", "SUPPORTED", "MED", claim="returns 3", quote_lines=[2])], lenses_completed=DEFECT[:4])
    r = g.record(b["run"])
    assert r["outcome"] == "ERROR" and r["new_blockers"] == [] and len(g.state()["blockers"]) == 1


def test_merge_key_includes_claim_text(g):
    pass_run(g)
    h1, bid, _ = blocked_run(g)
    g.commit("src/app.js", "function a() {\n  return 3;\n  leak();\n}\n", "c")
    b = g.begin()
    g.write_report(b, [finding(f"blocker:{bid}", "SUPPORTED", "MED", claim="returns 3", quote_lines=[2]),
                       finding("c1", "SUPPORTED", "MED", lines="3", claim="leaks a handle", quote_lines=[3]),
                       finding("c2", "SUPPORTED", "MED", lines="2", claim="returns  3", quote_lines=[2])])   # same claim modulo whitespace
    r = g.record(b["run"])
    assert len(r["new_blockers"]) == 1 and len(r["open_blockers"]) == 2
    new_id = r["new_blockers"][0]
    # fix A only -> A closed, new one stays
    g.commit("src/app.js", "function a() {\n  return compute();\n  leak();\n}\n", "fix a")
    b2 = g.begin()
    g.write_report(b2, [rejected(bid), finding(f"blocker:{new_id}", "SUPPORTED", "MED", lines="3", claim="leaks a handle", quote_lines=[3])])
    r2 = g.record(b2["run"])
    assert r2["outcome"] == "BLOCK" and [c["id"] for c in r2["closed_blockers"]] == [bid]
    assert [x["id"] for x in r2["open_blockers"]] == [new_id]


def test_korean_and_same_prefix_english_claims_are_distinct(g):
    g.commit("src/app.js", "function a() {\n  return 3;\n}\n", "c")
    b = g.begin()
    g.write_report(b, [finding("c1", "SUPPORTED", "MED", claim="반환값이 상수다", quote_lines=[2]),
                       finding("c2", "SUPPORTED", "MED", claim="널 검사가 없다", quote_lines=[2]),
                       finding("c3", "SUPPORTED", "MED", claim="one two three four five six seven eight nine", quote_lines=[2]),
                       finding("c4", "SUPPORTED", "MED", claim="one two three four five six seven eight ten", quote_lines=[2])])
    r = g.record(b["run"])
    assert len(r["new_blockers"]) == 4


def test_grounding_failed_field_not_missing_text(g):
    g.commit("src/app.js", "function a() {\n  return 3;\n}\n", "c")
    b = g.begin()
    g.write_report(b, [finding("c1", "SUSPECTED", "MED", claim="model suspicion", missing="FILE_NOT_FOUND", grounding_failed=False, quote_found=False),
                       finding("c2", "SUSPECTED", "MED", claim="downgraded", missing="EVIDENCE_QUOTE_MISMATCH", grounding_failed=True, quote_found=False)])
    r = g.record(b["run"])
    assert r["outcome"] == "BLOCK" and len(r["new_blockers"]) == 1
    assert [x for x in r["open_blockers"] if x["unverified"]][0]["claim"] == "downgraded"
    assert any("model suspicion" in q for q in r["questions"])


def test_suspected_crit_blocks_suspected_high_is_question(g):
    g.commit("src/app.js", "function a() {\n  return 3;\n}\n", "c")
    b = g.begin()
    g.write_report(b, [finding("c1", "SUSPECTED", "HIGH", claim="maybe", missing="UNCLEAR", quote_found=False)])
    r = g.record(b["run"])
    assert r["outcome"] == "PASS" and len(r["questions"]) == 1
    s = g.status()
    assert s["mergeable"] is True and len(s["questions"]) == 1 and any("확인되지 않은 의심 1건" in l for l in s["summary"])
    g.commit("src/app.js", "function a() {\n  return 4;\n}\n", "c2")
    b2 = g.begin()
    g.write_report(b2, [finding("c1", "SUSPECTED", "CRIT", claim="maybe fatal", missing="UNCLEAR", quote_found=False)])
    r2 = g.record(b2["run"])
    assert r2["outcome"] == "BLOCK" and r2["open_blockers"][0]["unverified"] is True


def test_unmapped_lens_incomplete_and_format_errors(g):
    g.commit("src/app.js", "a\n", "c1")
    b = g.begin()
    g.write_report(b, [], meta_over={"unmapped_findings": ["security#2"]})
    assert g.record(b["run"])["outcome"] == "ERROR"
    for bad in (finding("c1", "Supported", "HIGH", quote_lines=[1]),
                finding("c1", "CONFIRMED", "HIGH", quote_lines=[1]),
                finding("c1", "SUPPORTED", "MEDIUM", quote_lines=[1]),
                {**finding("c1", "SUPPORTED", "MED", quote_lines=[1]), "file": None}):
        g.commit("src/app.js", f"{bad['status']}{bad['severity']}{bad.get('file')}\n", "c")
        b = g.begin()
        g.write_report(b, [bad, finding("c2", "SUPPORTED", "MED", claim="valid one", quote_lines=[1])])
        r = g.record(b["run"])
        assert r["outcome"] == "ERROR" and any("레코드 형식 오류" in e for e in r["errors"]), r["errors"]
        assert "valid one" in json.dumps(r["open_blockers"], ensure_ascii=False)


def test_lens_incomplete_is_error(g):
    g.commit("src/app.js", "a\n", "c1")
    b = g.begin()
    g.write_report(b, [], lenses_completed=DEFECT[:4])
    r = g.record(b["run"])
    assert r["outcome"] == "ERROR" and any("렌즈 미완료" in e for e in r["errors"])


def test_report_contract_missing_or_newer_is_error(g):
    g.commit("src/app.js", "a\n", "c1")
    b = g.begin()
    g.write_report(b, [], meta_over={"report_contract": None})
    r = g.record(b["run"])
    assert r["outcome"] == "ERROR" and any("prism 0.6.0 이상 필요" in e for e in r["errors"])
    g.commit("src/app.js", "b\n", "c2")
    b = g.begin()
    g.write_report(b, [], meta_over={"report_contract": "3"})
    r = g.record(b["run"])
    assert any("ddaro를 업데이트하라" in e for e in r["errors"])


def test_no_report_is_stale_with_out_hint_when_no_run_file(g):
    g.commit("src/app.js", "a\n", "c1")
    b = g.begin()
    r = g.record(b["run"])
    assert r["outcome"] == "STALE" and "`--out`을 모름" in r["message"]
    g.write_run_file(b)
    r = g.record(b["run"])
    assert r["outcome"] == "STALE" and "--out" not in r["message"]
    assert g.state()["runs"][0]["outcome"] is None      # not recorded


def test_ideas_in_report_are_ignored(g):
    g.commit("src/app.js", "a\n", "c1")
    b = g.begin()
    rep = make_report(b, [])
    rep["meta"]["ideas"] = {"ran": True, "outcome": "completed"}
    rep["ideas"] = [{"id": "IDEA-1", "text": "x"}]
    g.write_run_file(b)
    (g.run_dir(b) / "prism-report.json").write_text(json.dumps(rep), encoding="utf-8")
    assert g.record(b["run"])["outcome"] == "PASS"


def test_unverified_promotion_then_needs_human(g):
    pass_run(g)
    h1 = g.commit("src/app.js", "function a() {\n  return 3;\n}\n", "bad")
    b = g.begin()
    g.write_report(b, [finding("c1", "SUSPECTED", "MED", claim="returns 3", missing="EVIDENCE_QUOTE_MISMATCH", grounding_failed=True, quote_found=False)])
    r = g.record(b["run"])
    bid = r["new_blockers"][0]
    assert r["open_blockers"][0]["unverified"] is True
    h2 = g.commit("src/app.js", "function a() {\n  return 3;\n  other();\n}\n", "more")
    b2 = g.begin()
    g.write_report(b2, [finding(f"blocker:{bid}", "SUSPECTED", "MED", claim="returns 3", missing="EVIDENCE_PASS_FAILED", grounding_failed=True, quote_found=False),
                        finding("c1", "SUPPORTED", "MED", lines="2", claim="returns 3", quote_lines=[2])])
    r2 = g.record(b2["run"])
    assert r2["outcome"] == "BLOCK" and r2["new_blockers"] == []
    blk = [x for x in g.state()["blockers"] if x["id"] == bid][0]
    assert blk["unverified"] is False and blk["head"] == h2
    b3 = g.begin()
    assert b3["scope"] == "rejudge"
    g.write_report(b3, [rejected(bid, quote="return 3;", quote_lines=[2])])
    r3 = g.record(b3["run"])
    assert r3["outcome"] == "BLOCK" and bid in r3["needs_human"]


def test_unverified_closes_without_code_change(g):
    g.commit("src/app.js", "function a() {\n  return 3;\n}\n", "bad")
    b = g.begin()
    g.write_report(b, [finding("c1", "SUSPECTED", "MED", claim="maybe", missing="EVIDENCE_QUOTE_MISMATCH", grounding_failed=True, quote_found=False)])
    bid = g.record(b["run"])["new_blockers"][0]
    b2 = g.begin()
    g.write_report(b2, [finding(f"blocker:{bid}", "SUPPORTED", "LOW", claim="maybe", quote_lines=[2])])
    r2 = g.record(b2["run"])
    assert r2["outcome"] == "PASS" and r2["closed_blockers"][0]["closed_by"] == "unverified_below_threshold"


def test_rejudge_requires_exactly_one_record_per_blocker(g):
    pass_run(g)
    h, bid, _ = blocked_run(g)
    b = g.begin()
    g.write_report(b, [])
    assert g.record(b["run"])["outcome"] == "ERROR"
    b = g.begin()
    g.write_report(b, [finding(f"blocker:{bid}", "SUPPORTED", "MED", claim="returns 3", quote_lines=[2]),
                       finding("c9", "SUPPORTED", "MED", claim="stray", quote_lines=[2])])
    r = g.record(b["run"])
    assert r["outcome"] == "ERROR" and any("예상 밖" in e for e in r["errors"])


# ---------------------------------------------------------------------------
# 이월 (L4) and approvals
# ---------------------------------------------------------------------------

def test_carry_docs_only_and_code(g):
    head, _ = pass_run(g)
    g.commit("docs/x.md", "d\n", "docs")
    g.commit("CHANGELOG.md", "c\n", "cl")
    assert g.status()["reason"] == "carry_docs_only"
    g.commit("docs/x.py", "code\n", "py in docs")      # extension not allowed
    assert g.status()["reason"] == "stale_pass"


def test_carry_revert_delete_move_count(g):
    head, _ = pass_run(g)
    base_content = (g.main / "src" / "app.js").read_text(encoding="utf-8")
    g.commit("src/app.js", base_content, "revert to base")       # reviewed file back to base content: counts
    assert g.status()["reason"] == "stale_pass"
    pass_run(g, content="function a() {\n  return 5;\n}\n")
    g.rm_commit("README.md")
    assert g.status()["reason"] == "stale_pass"
    pass_run(g, content="function a() {\n  return 6;\n}\n")
    (g.wt / "docs").mkdir(exist_ok=True)
    g.git("mv", "src/app.js", "docs/app.md")
    g.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "mv")
    assert g.status()["reason"] == "stale_pass"


def test_carry_ignores_files_merged_from_base(g):
    head, _ = pass_run(g)
    g.base_commit("other.txt", "from base\n")
    g.git("fetch", "-q", "origin")
    g.git("merge", "-q", "--no-edit", "origin/master")
    s = g.status()
    assert s["mergeable"] is True and s["reason"] == "carry_docs_only"


def test_verify_failure_at_target_blocks_carry(g):
    head, _ = pass_run(g)
    h2 = g.commit("docs/x.md", "d\n", "docs")
    st = g.state()
    st["runs"].append({"run": 50, "cycle": 1, "kind": "verify", "head": h2, "outcome": "BLOCK", "scope": "verify"})
    g.write_state(st)
    assert g.status(head=h2)["reason"] == "verify_failed"


def test_approve_is_per_commit_and_records_overrides(g):
    pass_run(g)
    h, bid, _ = blocked_run(g)
    out = g.gate("approve", str(g.main), "d-busan", "--head", h[:7], "--reason", "false positive")
    assert out["approved"] == h and out["overrides"] == [bid]
    s = g.status(head=h)
    assert s["mergeable"] is True and s["reason"] == "approved" and "human-approved over 1 open" in s["next"]
    h2 = g.commit("src/app.js", "function a() {\n  return 7;\n}\n", "after")
    assert g.status(head=h2)["mergeable"] is False


def test_docs_only_pr_from_github_files(g):
    g.commit("docs/x.md", "d\n", "docs")
    s = gate.compute_status(g.main, "d-busan", g.head(), pr_files=["docs/x.md"], pr_changed_files=1)
    assert s["mergeable"] is True and s["reason"] == "docs_only_pr"
    s = gate.compute_status(g.main, "d-busan", g.head(), pr_files=["docs/x.md", "src/a.js"], pr_changed_files=2)
    assert s["mergeable"] is False and s["reason"] == "no_pass"
    s = gate.compute_status(g.main, "d-busan", g.head(), pr_files=["docs/x.md"], pr_changed_files=2)
    assert s["mergeable"] is False


def test_pr_head_behind_local(g):
    h1 = g.commit("src/app.js", "a\n", "c1")
    h2, _ = pass_run(g, content="b\n")
    s = gate.compute_status(g.main, "d-busan", h1, local_head=h2)
    assert s["reason"] == "pr_head_behind_local" and "git push" in s["next"]


# ---------------------------------------------------------------------------
# PR #89 replay (S2 pass condition 1)
# ---------------------------------------------------------------------------

def test_pr89_replay(g):
    """a2733b5 (review fixes) -> c25e232 (re-review) -> 7c1fc0c (one UI line): the
    last commit has no PASS -> not mergeable; a docs-only last commit carries."""
    c1 = g.commit("src/App.jsx", "export const A = 1;\n", "fixes after prism")
    b = g.begin()
    g.write_report(b, [finding("c1", "SUPPORTED", "MED", file="src/App.jsx", lines="1", symbol="A", claim="FAB menu stays open",
                               evidence=["src/App.jsx:1 \u2014 export const A = 1;"], quote_lines=[1])])
    r = g.record(b["run"])
    assert r["outcome"] == "BLOCK"
    bid = r["new_blockers"][0]
    c2 = g.commit("src/App.jsx", "export const A = closeMenu(1);\n", "re-review follow-up")
    b2 = g.begin()
    g.write_report(b2, [rejected(bid, file="src/App.jsx", lines="1", quote="export const A = closeMenu(1);", quote_lines=[1], claim="FAB menu stays open")])
    assert g.record(b2["run"])["outcome"] == "PASS"
    assert g.status(head=c2)["mergeable"] is True
    c3 = g.commit("src/App.jsx", "export const A = closeMenu(2);\n", "UI tweak")
    s = g.status(head=c3)
    assert s["mergeable"] is False and s["reason"] == "stale_pass"
    assert any("src/App.jsx (code)" in l for l in s["summary"])
    # the docs-only variant carries the PASS
    g.git("reset", "-q", "--hard", c2)
    c3d = g.commit("docs/notes.md", "note\n", "docs")
    assert g.status(head=c3d)["reason"] == "carry_docs_only"


def test_blockers_survive_amend_rebase_full_and_reset(g):
    pass_run(g)
    h, bid, _ = blocked_run(g)
    g.amend("src/app.js", "function a() {\n  return 3;\n}\n// amended\n")
    b = g.begin()
    assert b["scope"] == "full" and [x["id"] for x in g.blockers_file(b)] == [bid]
    g.write_report(b, [finding(f"blocker:{bid}", "SUPPORTED", "MED", claim="returns 3", quote_lines=[2])])
    assert g.record(b["run"])["outcome"] == "BLOCK"
    b = g.begin("--full")
    assert [x["id"] for x in g.blockers_file(b)] == [bid]
    # reset to the old PASS commit: still blocked
    first_pass = g.state()["runs"][0]["head"]
    g.git("reset", "-q", "--hard", first_pass)
    s = g.status()
    assert s["mergeable"] is False and s["reason"] == "open_blockers"


# ---------------------------------------------------------------------------
# prism review fixes (PR #22, 2026-10-20)
# ---------------------------------------------------------------------------

def test_verify_that_forges_gate_state_is_refused(g):
    """c13: a committed test writes an approval into the state file -> REFUSED, state restored."""
    pass_run(g)
    h = g.commit("src/app.js", "function a() {\n  return 3;\n}\n", "bad")
    st_path = g.main / ".ddaro" / "gates" / "d-busan.f486a3be.json"
    forge = g.tmp / "forge.py"
    forge.write_text(f"""
import json
p = {str(st_path)!r}
d = json.load(open(p, encoding='utf-8'))
d['approvals'].append({{'cycle': d['cycle'], 'head': {h!r}, 'reason': 'forged', 'overrides': [], 'at': 't'}})
json.dump(d, open(p, 'w', encoding='utf-8'))
""", encoding="utf-8")
    g.write_verify({"commands": [], "default": f'"{sys.executable}" "{forge.as_posix()}"'})
    b = g.begin()
    assert b["outcome"] == "REFUSED" and "게이트 상태를 바꿈" in b["message"]
    s = g.status(head=h)
    assert s["mergeable"] is False and s["reason"] != "approved"
    assert g.state()["approvals"] == []


def test_claude_dir_is_never_a_document(g):
    """c15: `.claude/**/*.md` carries executable config; never docs-only."""
    g.write_cfg(planning_patterns=None)
    cfg = g.cfg
    cfg.pop("planning_patterns", None)
    g.write_cfg()
    head, _ = pass_run(g)
    h2 = g.commit(".claude/commands/deploy.md", "---\nallowed-tools: Bash\n---\n!rm -rf /\n", "cmd")
    assert g.status(head=h2)["reason"] == "stale_pass"
    s = gate.compute_status(g.main, "d-busan", h2, pr_files=[".claude/commands/deploy.md"], pr_changed_files=1)
    assert s["reason"] != "docs_only_pr"
    assert gate.is_doc("CHANGELOG.md", {}) and not gate.is_doc(".github/workflows/x.md", {})


def test_planning_patterns_string_falls_back_to_default(g):
    """c25: a raw JSON string must not be iterated character by character."""
    cfg = dict(g.cfg, planning_patterns='["docs/**"]')
    assert gate.is_doc("NOTES.md", cfg) is False
    assert gate.is_doc("CHANGELOG.md", cfg) is True
    assert gate.planning_patterns(cfg) == gate.DEFAULT_PLANNING_PATTERNS


def test_non_ascii_path_blocker_closes(g):
    """c18: git C-quotes non-ASCII paths; the index keys must still match."""
    pass_run(g)
    g.commit("문서/코드.js", "function a() {\n  return 3;\n}\n", "kr")
    b = g.begin()
    g.write_report(b, [finding("c1", "SUPPORTED", "MED", file="문서/코드.js", lines="2", claim="returns 3",
                               evidence=["문서/코드.js:2 \u2014 return 3;"], quote_lines=[2])])
    bid = g.record(b["run"])["new_blockers"][0]
    g.commit("문서/코드.js", "function a() {\n  return compute();\n}\n", "fix")
    b2 = g.begin()
    g.write_report(b2, [rejected(bid, file="문서/코드.js")])
    r2 = g.record(b2["run"])
    assert r2["outcome"] == "PASS" and r2["closed_blockers"][0]["closed_by"] == "fixed"
    quoted = '"a/' + chr(92) + '354' + chr(92) + '225' + chr(92) + '234.py"'
    assert gate.unquote_git_path(quoted) == 'a/' + bytes([0o354, 0o225, 0o234]).decode('utf-8') + '.py'


def test_resolve_main_ignores_foreign_main_worktree(g, tmp_path):
    """c19: a main_worktree outside this repository is not where the state goes."""
    other = tmp_path / "elsewhere"
    other.mkdir()
    g.write_cfg(main_worktree=other.as_posix())
    head, _ = pass_run(g)
    assert g.status()["mergeable"] is True
    assert not (other / ".ddaro").exists()


def test_shift_lines_insertion_inside_range(g):
    """c22: an insertion inside the blocker's range extends it."""
    content = "".join(f"line {i}\n" for i in range(1, 15))
    h1 = g.commit("src/big.js", content, "big")
    lines = content.splitlines()
    lines[12:12] = ["ins a", "ins b", "ins c"]          # after old line 12
    h2 = g.commit("src/big.js", "\n".join(lines) + "\n", "insert")
    repo = gate.Repo(g.wt)
    blk = {"file": "src/big.js", "lines": "10-14", "head": h1}
    assert gate.shift_lines(repo, blk, h2, h1) == ("10-17", False)
    lines2 = content.splitlines()
    lines2[8:8] = ["top"]
    h3 = g.commit("src/big.js", "\n".join(lines2) + "\n", "insert above")
    assert gate.shift_lines(repo, blk, h3, h1) == ("11-15", False)


def test_reset_and_retire_refuse_while_locked(g):
    pass_run(g)
    lock = g.main / ".ddaro" / "gates" / "d-busan.f486a3be.lock"
    holder = subprocess.Popen([sys.executable, "-c", f"""
import sys, time; sys.path.insert(0, {str(gate.Path(gate.__file__).parent)!r})
from _shared import file_lock
with file_lock({str(lock)!r}, 1):
    print('held', flush=True); time.sleep(8)
"""], stdout=subprocess.PIPE, text=True)
    assert holder.stdout.readline().strip() == "held"
    try:
        out = g.gate("reset", str(g.main), "d-busan", "--force")
        assert out["outcome"] == "REFUSED" and "locked by pid" in out["message"]
        assert (g.main / ".ddaro" / "gates" / "d-busan.f486a3be.json").exists()
        assert "pid ?" not in out["message"]        # c32: the holder's pid is readable
    finally:
        holder.kill()
        holder.wait()


def test_pending_verify_run_is_finalized(g):
    """c31: a verify-kind run left with outcome None is closed by the next check-begin."""
    head, _ = pass_run(g)
    st = g.state()
    st["runs"].append({"run": 40, "cycle": 1, "kind": "verify", "head": head, "outcome": None, "scope": "verify"})
    st["next_run"] = 41
    g.write_state(st)
    g.commit("src/app.js", "y\n", "c2")
    b = g.begin()
    assert any(f["run"] == 40 and "abandoned" in (f["error"] or "") for f in b["finalized"])
    assert b["scope"] == "recheck"


def test_block_and_verify_only_summaries_carry_notes(g):
    """c44: `note:` lines appear on every summary, not only the OK one."""
    g.gh(fail="offline")
    g.write_verify({"commands": [], "default": "false"})
    g.commit("src/app.js", "a\n", "c1")
    b = g.begin()
    assert b["outcome"] == "BLOCK" and any("머지 확인 못 함" in l for l in b["summary"])


def test_corrupt_archive_is_moved_aside(g):
    head, _ = pass_run(g)
    adir = g.main / ".ddaro" / "gates" / "archive" / "d-busan.f486a3be"
    adir.mkdir(parents=True)
    (adir / "cycle-1.json").write_text("{garbage", encoding="utf-8")
    g.gh(view={"89": {"number": 89, "state": "MERGED", "baseRefName": "master", "headRefName": "d-busan", "headRefOid": head}})
    out = g.gate("close", str(g.main), "d-busan", "--merged", "--pr", "89")
    assert out["closed"] is True
    assert list(adir.glob("cycle-1.corrupt-*.json")) and json.loads((adir / "cycle-1.json").read_text(encoding="utf-8"))["runs"]
    assert "unreadable archive" in g.state()["closes"][0].get("note", "")


def test_status_git_unavailable_is_unreadable_not_mergeable(g):
    head, _ = pass_run(g)
    g.commit("docs/x.md", "d\n", "docs")
    s = gate.compute_status(g.main, "d-busan", g.head(), repo=gate.Repo(g.main, timeout=0.0001))
    assert s["mergeable"] is False and s["reason"] == "unreadable"


def test_merge_confirm_notes_fetch_failure(g):
    head, _ = pass_run(g)
    g.gh(list=[{"number": 7, "state": "MERGED", "baseRefName": "master", "headRefName": "d-busan", "headRefOid": "e" * 40}])
    g.git("remote", "remove", "origin", cwd=g.main)
    g.git("remote", "add", "origin", (g.tmp / "nowhere.git").as_posix(), cwd=g.main)
    g.commit("src/app.js", "y\n", "c2")
    out = g.gate("close", str(g.main), "d-busan", "--merged", "--pr", "7")
    assert out["closed"] is False and "not local after fetch" in out["message"]


def test_make_run_tag_contract():
    tag, rand = gate.make_run_tag("Feat/Login page", "0" * 40, 3)
    assert isinstance(tag, str) and tag.endswith(f"-{rand}") and len(rand) == 6
    assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", tag)


def test_is_doc_prefix_handling():
    assert gate.is_doc(".planning/x.md", {}) and gate.is_doc("./.planning/x.md", {})
    assert gate.is_doc(".claude/x.md", {"planning_patterns": ["**/*.md"]}) is False
    assert gate.is_doc("docs/x.md", {"planning_patterns": ["**/*.md"]}) is True
