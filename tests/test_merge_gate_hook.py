"""Integration tests for hooks/check-merge-gate.py (merge-gate.md "머지 가드",
"사람 전용과 약화", "해석과 실패", "회귀").

The hook runs as a real subprocess against a GateRepo (fake `gh` on PATH,
real git). Exit 0 = allow, 2 = block; warn mode prints an additionalContext
JSON on stdout and exits 0.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

from gate_helpers import GateRepo, finding  # noqa: E402

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "check-merge-gate.py"
ALLOW, BLOCK = 0, 2


@pytest.fixture
def g(tmp_path):
    return GateRepo(tmp_path)


def hook(g: GateRepo, tool: str, cwd=None, env=None, **tool_input) -> subprocess.CompletedProcess:
    cwd = cwd if cwd is not None else g.wt
    payload = {"tool_name": tool, "cwd": Path(cwd).as_posix() if isinstance(cwd, Path) else str(cwd), "tool_input": tool_input}
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                          encoding="utf-8", env=env or g.env())


def bash(g: GateRepo, command: str, cwd=None, env=None):
    return hook(g, "Bash", cwd=cwd, env=env, command=command)


def passed_pr(g: GateRepo, number: int = 89, files=("src/app.js",), head: str | None = None) -> str:
    """A PASS at HEAD and a fake open PR whose head is that commit."""
    h = head or g.commit("src/app.js", "function a() {\n  return 2;\n}\n", "c1")
    b = g.begin()
    g.write_report(b, [])
    assert g.record(b["run"])["outcome"] == "PASS"
    g.set_pr(number, h, files)
    return h


def _set_pr(self: GateRepo, number, head, files=("src/app.js",), state="OPEN", auto=None, head_branch=None):
    pr = {"number": number, "state": state, "baseRefName": self.base, "headRefName": head_branch or self.branch,
          "headRefOid": head, "files": [{"path": f} for f in files], "changedFiles": len(files),
          "autoMergeRequest": auto, "url": f"https://github.com/o/r/pull/{number}"}
    self.gh(list=[pr], view={str(number): pr})


GateRepo.set_pr = _set_pr


# --- fast path / off / regression -------------------------------------------

def test_fast_path_ignores_unrelated_commands(g):
    t0 = time.monotonic()
    r = bash(g, "ls -la && echo hello")
    assert r.returncode == ALLOW and r.stdout == "" and r.stderr == ""
    assert time.monotonic() - t0 < 5


def test_off_changes_nothing(g):
    g.write_cfg(merge_gate="off")
    g.set_pr(89, g.head())
    for cmd in ("gh pr merge 89 --merge", "git push origin master", "gh api repos/o/r -X PATCH -f x=1",
                f"python gate.py approve {g.main.as_posix()} d-busan --head HEAD --reason x",
                f"rm {g.main.as_posix()}/.ddaro/config.json"):
        r = bash(g, cmd)
        assert r.returncode == ALLOW and r.stdout == "", cmd
    r = hook(g, "Edit", file_path=(g.main / ".ddaro" / "verify.json").as_posix(), old_string="a", new_string="b")
    assert r.returncode == ALLOW


def test_non_matching_tools_ignored(g):
    r = hook(g, "Read", file_path=(g.main / ".ddaro" / "config.json").as_posix())
    assert r.returncode == ALLOW


# --- gh pr merge ---------------------------------------------------------------

def test_merge_needs_match_head_commit_keeps_method(g):
    h = passed_pr(g)
    r = bash(g, "gh pr merge 89 --merge --delete-branch=false")
    assert r.returncode == BLOCK
    assert "needs --match-head-commit" in r.stderr
    assert f"gh pr merge 89 --merge --delete-branch=false --match-head-commit {h}" in r.stderr
    r = bash(g, f"gh pr merge 89 --squash --match-head-commit {'0' * 40}")
    assert r.returncode == BLOCK and "--squash" in r.stderr


def test_merge_with_pass_allowed(g):
    h = passed_pr(g)
    r = bash(g, f"gh pr merge 89 --squash --delete-branch=false --match-head-commit {h}")
    assert r.returncode == ALLOW and r.stdout == "" and r.stderr == ""


def test_merge_without_pass_blocked_with_since(g):
    h = passed_pr(g)
    h2 = g.commit("src/app.js", "function a() {\n  return 9;\n}\n", "ui tweak")
    g.set_pr(89, h2)
    r = bash(g, f"gh pr merge 89 --squash --match-head-commit {h2}")
    assert r.returncode == BLOCK
    assert f"d-busan has no PASS for {h2[:7]}" in r.stderr and "src/app.js (code)" in r.stderr and "/ddaro check" in r.stderr


def test_merge_docs_only_pr_allowed_without_pass(g):
    h = g.commit("docs/x.md", "d\n", "docs")
    g.set_pr(90, h, files=("docs/x.md",))
    r = bash(g, f"gh pr merge 90 --squash --match-head-commit {h}")
    assert r.returncode == ALLOW


def test_merge_after_branch_changing_command_blocked_read_ok(g):
    h = passed_pr(g)
    r = bash(g, f"git push origin d-busan && gh pr merge 89 --squash --match-head-commit {h}")
    assert r.returncode == BLOCK and "머지는 따로 실행" in r.stderr
    r = bash(g, f"gh pr view 89 --json state && gh pr merge 89 --squash --match-head-commit {h}")
    assert r.returncode == ALLOW


def test_merge_auto_blocked(g):
    passed_pr(g)
    r = bash(g, "gh pr merge 89 --auto --squash")
    assert r.returncode == BLOCK and "--auto" in r.stderr


@pytest.mark.parametrize("tmpl", [
    "if true; then gh pr merge 89 --squash; fi",
    "timeout 60 gh pr merge 89 --squash",
    "(gh pr merge 89 --squash)",
    "gh.exe pr merge 89 --squash",
    "cd {main} && gh pr view 89 --json state && gh pr merge 89 --merge --delete-branch=false",
])
def test_merge_detected_in_shell_shapes(g, tmpl):
    passed_pr(g)
    cmd = tmpl.format(main=g.main.as_posix())
    cwd = g.tmp if "cd " in cmd else g.wt
    r = bash(g, cmd, cwd=cwd)
    assert r.returncode == BLOCK and "match-head-commit" in r.stderr, cmd


def test_merge_other_repo_ignored(g):
    passed_pr(g)
    r = bash(g, "gh pr merge 5 -R someone/elsewhere --squash")
    assert r.returncode == ALLOW


def test_merge_head_not_local_blocked(g):
    passed_pr(g)
    g.set_pr(89, "f" * 40)
    r = bash(g, f"gh pr merge 89 --squash --match-head-commit {'f' * 40}")
    assert r.returncode == BLOCK and "git fetch origin d-busan master" in r.stderr


def test_merge_pr_head_behind_local(g):
    h1 = g.commit("src/app.js", "a\n", "c1")
    h2 = passed_pr(g, head=None)          # PASS at h2 (new commit), PR still points at h1
    g.set_pr(89, h1)
    r = bash(g, f"gh pr merge 89 --squash --match-head-commit {h1}")
    assert r.returncode == BLOCK and "git push" in r.stderr


def test_merge_shows_questions_when_pass_has_suspected(g):
    h = g.commit("src/app.js", "a\n", "c1")
    b = g.begin()
    g.write_report(b, [finding("c1", "SUSPECTED", "HIGH", claim="maybe racy", missing="UNCLEAR", quote_found=False)])
    assert g.record(b["run"])["outcome"] == "PASS"
    g.set_pr(89, h)
    r = bash(g, f"gh pr merge 89 --squash --match-head-commit {h}")
    assert r.returncode == ALLOW
    out = json.loads(r.stdout)
    assert "확인되지 않은 의심 1건" in out["hookSpecificOutput"]["additionalContext"]
    assert "permissionDecision" not in r.stdout


def test_merge_gh_failure_blocks(g):
    passed_pr(g)
    g.gh(fail="HTTP 500")
    r = bash(g, "gh pr merge 89 --squash --match-head-commit abc")
    assert r.returncode == BLOCK and "could not read the PR" in r.stderr


def test_merge_gh_timeout_blocks(g):
    passed_pr(g)
    g.gh(sleep=15)
    t0 = time.monotonic()
    r = bash(g, "gh pr merge 89 --squash --match-head-commit abc")
    assert r.returncode == BLOCK and "could not read the PR" in r.stderr and "[timeout]" in r.stderr
    assert time.monotonic() - t0 < 20


def test_heredoc_body_mentioning_merge_is_blocked_with_body_file_hint(g):
    passed_pr(g)
    r = bash(g, 'gh pr create --base master --title t --body "$(cat <<EOF\nthen gh pr merge 89\nEOF\n)"')
    assert r.returncode == BLOCK and "--body-file" in r.stderr


# --- gh api / aliases ---------------------------------------------------------

@pytest.mark.parametrize("cmd,blocked", [
    ("gh api repos/o/r/pulls/89 -X PATCH -f title=x", True),
    ("gh api repos/o/r/pulls/89 -XPATCH", True),
    ("gh api --method=PUT repos/o/r/contents/x", True),
    ("gh api repos/o/r/pulls/89 -f state=closed", True),
    ("gh api repos/o/r/pulls --input body.json", True),
    ("gh api graphql -f query='mutation { mergePullRequest(input: {}) { clientMutationId } }'", True),
    ("gh api graphql -f query='query { viewer { login } }'", False),
    ("gh api repos/o/r/pulls/89", False),
    ("gh api repos/o/r/pulls -X GET -f state=open", False),
    ("gh alias set pm 'pr merge'", True),
    ("gh alias import aliases.yml", True),
    ("git -c alias.p=push p origin d-busan", True),
    ("git config alias.p push", True),
    ("git config --global user.name x", False),
])
def test_gh_api_and_alias_rules(g, cmd, blocked):
    r = bash(g, cmd)
    assert (r.returncode == BLOCK) is blocked, (cmd, r.stderr)


# --- git push (L13) ------------------------------------------------------------

@pytest.mark.parametrize("cmd", [
    "git push origin master",
    "git push origin HEAD:master",
    "git push origin d-busan:refs/heads/master",
    "git push origin +master",
    "git push --all origin",
    "git push --mirror origin",
    "git push origin --delete master",
    "git -c push.default=upstream push origin",
    "git -c remote.origin.push=refs/heads/*:refs/heads/* push",
])
def test_push_to_base_blocked(g, cmd):
    r = bash(g, cmd)
    assert r.returncode == BLOCK, (cmd, r.stderr)
    assert "push to the base branch refused" in r.stderr


def test_push_to_work_branch_allowed(g):
    for cmd in ("git push origin d-busan", "git push origin HEAD", "git push -u origin d-busan", "git push"):
        r = bash(g, cmd)
        assert r.returncode == ALLOW, (cmd, r.stderr)


def test_push_implied_target_from_base_branch_blocked(g):
    r = bash(g, "git push", cwd=g.main)            # main worktree is on master
    assert r.returncode == BLOCK
    r = bash(g, "git push origin HEAD", cwd=g.main)
    assert r.returncode == BLOCK


def test_push_matching_and_upstream_blocked(g):
    g.git("config", "push.default", "matching")
    assert bash(g, "git push origin").returncode == BLOCK
    g.git("config", "push.default", "upstream")
    g.git("branch", "--set-upstream-to=origin/master")
    assert bash(g, "git push").returncode == BLOCK


def test_push_dash_C_accumulates(g):
    cmd = f"git -C {g.wt.name} -C ../{g.main.name} push origin master"
    r = bash(g, cmd, cwd=g.tmp)
    assert r.returncode == BLOCK
    cmd = f"git -C {g.wt.name} -C ../{g.main.name} push origin d-busan"
    assert bash(g, cmd, cwd=g.tmp).returncode == ALLOW


def test_push_auto_merge_protection(g):
    h = g.commit("src/app.js", "a\n", "c1")
    g.set_pr(89, h, auto={"enabledAt": "now"})
    r = bash(g, "git push origin d-busan")
    assert r.returncode == BLOCK and "auto-merge on" in r.stderr
    # PASS at head -> allowed
    b = g.begin()
    g.write_report(b, [])
    g.record(b["run"])
    assert bash(g, "git push origin d-busan").returncode == ALLOW
    # auto-merge lookup failure: allowed with a warning
    g.commit("src/app.js", "b\n", "c2")
    g.gh(fail="no network")
    r = bash(g, "git push origin d-busan")
    assert r.returncode == ALLOW and "auto-merge state" in r.stdout


# --- human-only, weakening, writes (L11) --------------------------------------

def test_human_only_gate_commands_blocked_even_from_outside(g):
    main = g.main.as_posix()
    for cmd in (f"python gate.py approve {main} d-busan --head HEAD --reason x",
                f"python /x/hooks/gate.py reset {main} d-busan",
                f"python gate.py close {main} d-busan"):
        r = bash(g, cmd, cwd=g.tmp)
        assert r.returncode == BLOCK and "person's command" in r.stderr, cmd
    assert bash(g, f"python gate.py close {main} d-busan --merged --pr 89", cwd=g.tmp).returncode == ALLOW
    assert bash(g, f"python gate.py status {main} --branch d-busan", cwd=g.tmp).returncode == ALLOW


def test_config_tool_weakening_blocked_strengthening_allowed(g):
    main = g.main.as_posix()
    for cmd in (f"python config_tool.py set {main} merge_gate off",
                f"python config_tool.py set {main} merge_gate warn",
                f"python config_tool.py set {main} gate_block_severity HIGH",
                f"python config_tool.py set {main} gate_verify none",
                f"python config_tool.py set {main} base_branch develop",
                f"python config_tool.py init {main}"):
        r = bash(g, cmd)
        assert r.returncode == BLOCK, (cmd, r.stderr)
    assert bash(g, f"python config_tool.py set {main} gate_block_severity CRIT").returncode == BLOCK
    g.write_cfg(gate_block_severity="HIGH")
    assert bash(g, f"python config_tool.py set {main} gate_block_severity MED").returncode == ALLOW
    assert bash(g, f"python config_tool.py set {main} language korean").returncode == ALLOW
    assert bash(g, f"python config_tool.py set {main} merge_gate strict").returncode == ALLOW
    # unresolvable <main> argument: judged by cwd's main
    assert bash(g, 'python config_tool.py set "$MAIN" merge_gate off').returncode == BLOCK


def test_edit_weakening_config_blocked_other_keys_allowed(g):
    cfgp = (g.main / ".ddaro" / "config.json").as_posix()
    r = hook(g, "Edit", file_path=cfgp, old_string='"merge_gate": "strict"', new_string='"merge_gate": "off"')
    assert r.returncode == BLOCK and "weakens the gate" in r.stderr
    r = hook(g, "Edit", file_path=cfgp, old_string='"main_protection": "strict"', new_string='"main_protection": "warn"')
    assert r.returncode == ALLOW
    new = dict(g.cfg, merge_gate="warn")
    r = hook(g, "Write", file_path=cfgp, content=json.dumps(new))
    assert r.returncode == BLOCK
    new = dict(g.cfg, planning_patterns=g.cfg["planning_patterns"] + ["**/*.js"])
    assert hook(g, "Write", file_path=cfgp, content=json.dumps(new)).returncode == BLOCK
    new = dict(g.cfg, planning_patterns=g.cfg["planning_patterns"][:-1])
    assert hook(g, "Write", file_path=cfgp, content=json.dumps(new)).returncode == ALLOW


def test_config_outside_main_blocked(g):
    other = (g.wt / ".ddaro" / "config.json").as_posix()
    assert hook(g, "Write", file_path=other, content='{"merge_gate": "off"}').returncode == BLOCK
    assert bash(g, f"cat > {other} <<'EOF'\n{{}}\nEOF").returncode == BLOCK
    assert bash(g, "echo '{}' > .ddaro/config.json", cwd=g.wt).returncode == BLOCK


@pytest.mark.parametrize("tmpl", [
    "sed -i 's/strict/off/' {main}/.ddaro/config.json",
    "rm {main}/.ddaro/verify.json",
    "echo '{{}}' > {main}/.ddaro/verify.json",
    "rm -rf {main}/.ddaro",
    "mv {main}/.ddaro/config.json /tmp/x",
    "cp /tmp/x {main}/.ddaro/config.json",
    "tee {main}/.ddaro/gates/x.json < /dev/null",
    "truncate -s 0 {main}/.ddaro/gates/d.json",
    "python -c \"open('{main}/.ddaro/config.json','w').write('x')\"",
    "git clean -xdf",
])
def test_shell_writes_to_protected_paths_blocked(g, tmpl):
    cmd = tmpl.format(main=g.main.as_posix())
    r = bash(g, cmd, cwd=g.main)
    assert r.returncode == BLOCK, (cmd, r.stderr)


def test_shell_reads_allowed(g):
    main = g.main.as_posix()
    for cmd in (f"cat {main}/.ddaro/config.json", f"jq -r .merge_gate {main}/.ddaro/config.json",
                f"cp {main}/.ddaro/config.json /tmp/backup.json", "git clean -df", "git status"):
        assert bash(g, cmd, cwd=g.main).returncode == ALLOW, cmd


def test_run_folder_report_files_protected_other_files_free(g):
    g.commit("src/app.js", "a\n", "c1")
    b = g.begin()
    rd = b["run_dir"]
    for cmd in (f"rm {rd}/prism-report.json", f"mv {rd}/prism-run.json {rd}/x", f"echo x > {rd}/prism-run.json"):
        assert bash(g, cmd).returncode == BLOCK, cmd
    assert hook(g, "Write", file_path=f"{rd}/prism-report.json", content="{}").returncode == BLOCK
    assert hook(g, "Edit", file_path=f"{rd}/prism-run.json", old_string="a", new_string="b").returncode == BLOCK
    assert hook(g, "Write", file_path=f"{rd}/pass1.claude.security.txt", content="x").returncode == ALLOW
    assert bash(g, f"cat {rd}/prism-report.json").returncode == ALLOW


def test_gates_dir_edit_blocked(g):
    r = hook(g, "Edit", file_path=(g.main / ".ddaro" / "gates" / "d-busan.f486a3be.json").as_posix(), old_string="a", new_string="b")
    assert r.returncode == BLOCK
    r = hook(g, "Write", file_path=(g.main / ".ddaro" / "verify.json").as_posix(), content="{}")
    assert r.returncode == BLOCK


def test_nearer_config_off_does_not_override_main_strict(g):
    (g.wt / ".ddaro" / "config.json").write_text(json.dumps({"merge_gate": "off"}), encoding="utf-8")
    passed_pr(g)
    r = bash(g, "gh pr merge 89 --squash", cwd=g.wt)
    assert r.returncode == BLOCK


def test_unparseable_main_config_counts_as_strict(g):
    g.set_pr(89, g.head())
    (g.main / ".ddaro" / "config.json").write_text("{not json", encoding="utf-8")
    assert bash(g, "gh pr merge 89 --squash").returncode == BLOCK


def test_marker_keeps_gate_after_config_deleted(g):
    g.set_pr(89, g.head())
    marker = g.git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=g.main)
    Path(marker, "ddaro-gate").write_text("merge_gate=strict\n", encoding="utf-8")
    (g.main / ".ddaro" / "config.json").unlink()
    assert bash(g, "gh pr merge 89 --squash").returncode == BLOCK


def test_warn_mode_only_adds_context(g):
    g.write_cfg(merge_gate="warn")
    passed_pr(g)
    r = bash(g, "gh pr merge 89 --squash")
    assert r.returncode == ALLOW
    out = json.loads(r.stdout)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "[warn]" in ctx and "match-head-commit" in ctx and "permissionDecision" not in r.stdout
    r = bash(g, "git push origin master")
    assert r.returncode == ALLOW and "[warn]" in r.stdout


def test_fallback_regexes_and_import_failure_simulation(g, tmp_path):
    spec = importlib.util.spec_from_file_location("cmg", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    payload = {"tool_name": "Bash", "cwd": g.wt.as_posix(), "tool_input": {"command": "gh pr merge 89"}}
    assert mod._fallback(payload) == BLOCK
    payload["tool_input"]["command"] = "git push origin master"
    assert mod._fallback(payload) == BLOCK
    payload["tool_input"]["command"] = "ls"
    assert mod._fallback(payload) == ALLOW
    g.write_cfg(merge_gate="off")
    payload["tool_input"]["command"] = "gh pr merge 89"
    assert mod._fallback(payload) == ALLOW
    # a broken import (gate.py unreadable) after identification -> block
    g.write_cfg(merge_gate="strict")
    passed_pr(g)
    broken = tmp_path / "hooks_copy"
    broken.mkdir()
    for f in HOOK.parent.glob("*.py"):
        (broken / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    (broken / "gate.py").write_text("raise ImportError('simulated')\n", encoding="utf-8")
    payload = {"tool_name": "Bash", "cwd": g.wt.as_posix(), "tool_input": {"command": "gh pr merge 89 --squash"}}
    r = subprocess.run([sys.executable, str(broken / "check-merge-gate.py")], input=json.dumps(payload),
                       capture_output=True, text=True, encoding="utf-8", env=g.env())
    assert r.returncode == BLOCK and "guard failed" in r.stderr


def test_hook_registered_in_hooks_json():
    hooks = json.loads((HOOK.parent / "hooks.json").read_text(encoding="utf-8"))
    entries = [h for grp in hooks["hooks"]["PreToolUse"] for h in grp["hooks"] if "check-merge-gate.py" in h["command"]]
    assert len(entries) == 1 and entries[0].get("timeout") == 30
    grp = [grp for grp in hooks["hooks"]["PreToolUse"] if any("check-merge-gate.py" in h["command"] for h in grp["hooks"])][0]
    assert grp["matcher"] == "Bash|Edit|Write|NotebookEdit"


# ---------------------------------------------------------------------------
# prism review fixes (PR #22, 2026-10-20)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cmd", [
    "git push origin 'refs/heads/*:refs/heads/*'",
    "git push origin 'refs/heads/*'",
    "git push origin 'refs/heads/ma*'",
    "git push origin --delete 'refs/heads/*'",
    "git send-pack origin HEAD:refs/heads/master",
    "git-push origin HEAD:master",
    "/usr/lib/git-core/git-push origin master",
])
def test_push_wildcards_sendpack_dashed_binaries_blocked(g, cmd):
    r = bash(g, cmd)
    assert r.returncode == BLOCK, (cmd, r.stderr)


def test_preexisting_git_alias_examined(g):
    g.git("config", "alias.pm", "push origin HEAD:master")
    g.git("config", "alias.sp", "!git push origin HEAD:master")
    g.git("config", "alias.st", "status")
    assert bash(g, "git pm").returncode == BLOCK
    assert bash(g, "git sp").returncode == BLOCK and "shell command" in bash(g, "git sp").stderr
    assert bash(g, "git st").returncode == ALLOW
    assert bash(g, "git lfs ls-files").returncode == ALLOW


def test_gh_alias_examined(g):
    passed_pr(g)
    g.gh(default={}, list=[], view={}, aliases={"mg": "pr merge --squash", "sh": "!gh pr merge"})
    g.gh_script.write_text(json.dumps({"aliases": {"mg": "pr merge --squash", "sh": "!gh pr merge"},
                                       "list": [], "view": {"89": {"number": 89, "state": "OPEN", "baseRefName": "master",
                                                                     "headRefName": "d-busan", "headRefOid": g.head(),
                                                                     "files": [{"path": "src/app.js"}], "changedFiles": 1}}}), encoding="utf-8")
    r = bash(g, "gh mg 89")
    assert r.returncode == BLOCK and "match-head-commit" in r.stderr
    r = bash(g, "gh sh 89")
    assert r.returncode == BLOCK and "shell command" in r.stderr


@pytest.mark.parametrize("cmd,blocked", [
    ("gh api graphql -F query=@merge.graphql", True),
    ("gh api graphql --input body.json", True),
    ("gh api graphql -f query=@q.graphql", True),
    ("gh api -iX PUT repos/o/r/pulls/5/merge", True),
    ("gh api -siX PATCH repos/o/r/pulls/5", True),
    ("gh api -XPUT repos/o/r/pulls/5/merge", True),
    ("gh api graphql -f query='query { viewer { login } }'", False),
    ("gh api -i repos/o/r/pulls/5", False),
])
def test_gh_api_file_bodies_and_grouped_flags(g, cmd, blocked):
    r = bash(g, cmd)
    assert (r.returncode == BLOCK) is blocked, (cmd, r.stderr)


def test_two_step_config_corruption_blocked(g):
    cfgp = (g.main / ".ddaro" / "config.json").as_posix()
    r = hook(g, "Write", file_path=cfgp, content="{bad json")
    assert r.returncode == BLOCK and "stop parsing" in r.stderr
    (g.main / ".ddaro" / "config.json").write_text("{bad json", encoding="utf-8")   # as if it had landed
    r = hook(g, "Write", file_path=cfgp, content=json.dumps({"merge_gate": "off", "base_branch": "master"}))
    assert r.returncode == BLOCK
    r = hook(g, "Write", file_path=cfgp, content=json.dumps({"merge_gate": "strict", "base_branch": "master"}))
    assert r.returncode == ALLOW


@pytest.mark.skipif(os.name != "nt" and sys.platform != "darwin", reason="case-insensitive filesystems")
def test_protected_paths_case_insensitive(g):
    up = (g.main / ".DDARO" / "gates" / "x.json").as_posix()
    assert hook(g, "Write", file_path=up, content="{}").returncode == BLOCK
    assert bash(g, "echo '{}' > .DDARO/gates/x.json", cwd=g.main).returncode == BLOCK
    assert bash(g, "python -c \"open('.DDARO/verify.json','w')\"", cwd=g.main).returncode == BLOCK


@pytest.mark.parametrize("tmpl", [
    "rm -rf {main}/.ddaro/*",
    "cp /tmp/x {main}/.ddaro/gat[e]s/d.json",
    "echo '{{}}' > {main}/.ddaro/g?tes/x.json",
    "tee {main}/.ddaro/gat{{e,e}}s/x.json < /dev/null",
    "rm {main}/.git/ddaro-gate",
    "cp -t {main}/.ddaro/gates /tmp/x",
    "python.exe -c \"open('{main}/.ddaro/config.json','w').write('x')\"",
    "python3.11 -c \"open('{main}/.ddaro/gates/x.json','w')\"",
    "python -c \"from pathlib import Path; Path('{main}/.ddaro/gates/x.json').write_text('x')\"",
    "dd if=/tmp/f of={main}/.ddaro/gates/x.json",
    "echo '[alias] p = !git push' >> {main}/.git/config",
])
def test_more_protected_write_shapes_blocked(g, tmpl):
    cmd = tmpl.format(main=g.main.as_posix())
    r = bash(g, cmd, cwd=g.main)
    assert r.returncode == BLOCK, (cmd, r.stderr)


def test_stash_all_in_main_blocked_and_marker_init_rules(g):
    assert bash(g, "git stash --all", cwd=g.main).returncode == BLOCK
    assert bash(g, "git stash -u", cwd=g.main).returncode == ALLOW        # .ddaro is gitignored in the fixture
    assert bash(g, "git stash", cwd=g.main).returncode == ALLOW
    assert bash(g, "git stash --all", cwd=g.wt).returncode == ALLOW      # not <main>
    marker = Path(g.git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=g.main), "ddaro-gate")
    marker.write_text("merge_gate=strict\n", encoding="utf-8")
    (g.main / ".ddaro" / "config.json").unlink()
    main = g.main.as_posix()
    assert bash(g, f"python config_tool.py init {main} merge_gate=off").returncode == BLOCK
    assert bash(g, f"python config_tool.py init {main} merge_gate=strict").returncode == ALLOW
    # a config that says off while the marker exists was not written by config_tool: strict
    g.write_cfg(merge_gate="off")
    g.set_pr(89, g.head())
    assert bash(g, "gh pr merge 89 --squash").returncode == BLOCK


def test_variable_main_argument_resolved_and_outside_cwd(g):
    main = g.main.as_posix()
    cmd = f"cd {g.tmp.as_posix()} && M={main} && python gate.py approve $M d-busan --head HEAD --reason x"
    r = bash(g, cmd, cwd=g.wt)
    assert r.returncode == BLOCK and "person's command" in r.stderr
    cmd = f"export M={main}; python config_tool.py set $M merge_gate off"
    assert bash(g, cmd, cwd=g.tmp).returncode == BLOCK


def test_cd_to_unresolvable_target_keeps_gate(g):
    passed_pr(g)
    r = bash(g, "cd $WT/sub && gh pr merge 89 --squash", cwd=g.wt)
    assert r.returncode == BLOCK and "match-head-commit" in r.stderr
    r = bash(g, "cd does-not-exist && gh pr merge 89 --squash", cwd=g.wt)
    assert r.returncode == BLOCK


def test_merge_value_flags_before_selector_allowed(g):
    h = passed_pr(g)
    r = bash(g, f'gh pr merge --subject "Fix x" 89 --squash --match-head-commit {h}')
    assert r.returncode == ALLOW, r.stderr


def test_multi_refspec_auto_merge_pairs(g):
    g.git("branch", "other")
    g.commit("src/app.js", "a\n", "c1")
    pr = {"number": 7, "state": "OPEN", "baseRefName": "master", "headRefName": "other", "headRefOid": g.git("rev-parse", "other"),
          "autoMergeRequest": {"enabledAt": "now"}, "files": [], "changedFiles": 0}
    g.gh(list=[pr], view={"7": pr})
    r = bash(g, "git push origin other d-busan")
    assert r.returncode == BLOCK and "on other has auto-merge" in r.stderr


def test_broken_shared_module_fails_closed(g, tmp_path):
    passed_pr(g)
    broken = tmp_path / "hooks_copy"
    broken.mkdir()
    for f in HOOK.parent.glob("*.py"):
        (broken / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    (broken / "_shared.py").write_text("raise ImportError('simulated')\n", encoding="utf-8")
    for cmd in ("gh pr merge 89 --squash", "git push origin master"):
        payload = {"tool_name": "Bash", "cwd": g.wt.as_posix(), "tool_input": {"command": cmd}}
        r = subprocess.run([sys.executable, str(broken / "check-merge-gate.py")], input=json.dumps(payload),
                           capture_output=True, text=True, encoding="utf-8", env=g.env())
        assert r.returncode == BLOCK and "[ddaro] merge_gate" in r.stderr, cmd


def test_fallback_warn_mode_adds_context(g, capsys):
    spec = importlib.util.spec_from_file_location("cmg2", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    g.write_cfg(merge_gate="warn")
    payload = {"tool_name": "Bash", "cwd": g.wt.as_posix(), "tool_input": {"command": "gh pr merge 89"}}
    assert mod._fallback(payload) == ALLOW
    out = capsys.readouterr().out
    assert "additionalContext" in out and "could not parse" in out


def test_non_gated_repo_git_commands_exit_quietly(tmp_path, g):
    other = tmp_path / "plain"
    other.mkdir()
    subprocess.run(["git", "init", "-q", str(other)], check=True)
    payload = {"tool_name": "Bash", "cwd": other.as_posix(), "tool_input": {"command": "git status && gh pr list"}}
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                       encoding="utf-8", env=g.env())
    assert r.returncode == ALLOW and r.stdout == "" and r.stderr == ""


def test_marker_write_tool_blocked(g):
    marker = Path(g.git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=g.main), "ddaro-gate")
    assert hook(g, "Write", file_path=marker.as_posix(), content="").returncode == BLOCK
    assert hook(g, "Edit", file_path=(g.main / ".git" / "config").as_posix(), old_string="a", new_string="[alias]").returncode == BLOCK


def test_relative_paths_from_outside_cwd_still_gated(g):
    rel = g.main.name
    assert bash(g, f"echo '{{}}' > {rel}/.ddaro/gates/x.json", cwd=g.tmp).returncode == BLOCK
    assert bash(g, f"python gate.py approve {rel} d-busan --head HEAD --reason x", cwd=g.tmp).returncode == BLOCK
    assert bash(g, f"rm -rf {rel}/.ddar[o]", cwd=g.tmp).returncode == BLOCK
    assert bash(g, f"rm {rel}/.git/ddaro-gat[e]", cwd=g.tmp).returncode == BLOCK


def test_env_config_redirect_blocked(g):
    for cmd in ("GIT_CONFIG_PARAMETERS=\"'alias.p=push origin HEAD:master'\" git p",
                "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0=push git p origin HEAD:master",
                "git --config-env=alias.p=P p origin HEAD:master",
                "GH_CONFIG_DIR=/tmp/ghc gh mg 89",
                "git frobnicate"):
        r = bash(g, cmd)
        assert r.returncode == BLOCK, (cmd, r.stderr)
    assert bash(g, "gh api -t graphql -X PUT repos/o/r/pulls/5/merge -f query='query{viewer{login}}'").returncode == BLOCK
    assert bash(g, "echo x >> ~/.gitconfig").returncode == BLOCK
    assert bash(g, "git stash -u", cwd=g.main).returncode == ALLOW        # .ddaro is ignored in the fixture
