"""Structure lint for the 0.9.0 per-command instruction files.

Token budget is the point of this layout: every subcommand file must be
self-contained (no "read SKILL.md"), hidden from the model's always-on skill
listing (`disable-model-invocation: true`; the user can still type it and the
model reaches it through `/ddaro <sub>`), and carry the exact same Step 0.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COMMANDS = sorted((ROOT / "commands").glob("*.md"))
SUBS = [p for p in COMMANDS if p.name != "ddaro.md"]
UMBRELLA = ROOT / "commands" / "ddaro.md"
REFS = sorted((ROOT / "reference").glob("*.md"))
STEP0 = re.compile(r"<!-- step0 -->\n(.*?)\n<!-- /step0 -->", re.S)


def _frontmatter(p: Path) -> dict:
    head = p.read_text(encoding="utf-8").split("---", 2)[1]
    out = {}
    for line in head.strip().splitlines():
        key, _, val = line.partition(":")
        out[key.strip()] = val.strip().strip('"')
    return out


def test_every_subcommand_has_a_file():
    names = {p.stem.replace("ddaro-", "") for p in SUBS}
    assert names == {"start", "adopt", "commit", "merge", "clear", "abandon", "status", "list",
                     "resume", "config", "go", "spec", "review", "check"}


@pytest.mark.parametrize("path", SUBS, ids=lambda p: p.name)
def test_subcommand_hidden_from_model_listing(path):
    fm = _frontmatter(path)
    assert fm.get("disable-model-invocation") == "true"
    assert len(fm["description"]) <= 100, "keep the / menu line short"


def test_umbrella_is_the_only_model_entry():
    fm = _frontmatter(UMBRELLA)
    assert "disable-model-invocation" not in fm
    assert len(fm["description"]) <= 220


def test_step0_identical_everywhere():
    blocks = {p.name: STEP0.search(p.read_text(encoding="utf-8")) for p in SUBS}
    missing = [n for n, m in blocks.items() if m is None]
    assert not missing, f"no Step 0 block: {missing}"
    texts = {m.group(1) for m in blocks.values()}
    assert len(texts) == 1, "Step 0 drifted between command files"
    assert 'config_tool.py" ensure-schema' in texts.pop()


@pytest.mark.parametrize("path", COMMANDS + REFS, ids=lambda p: p.name)
def test_no_monolith_reads(path):
    assert "SKILL.md" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", COMMANDS + REFS, ids=lambda p: p.name)
def test_plugin_paths_exist(path):
    text = path.read_text(encoding="utf-8")
    for rel in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./<>-]+)", text):
        rel = rel.rstrip(".")
        if "<" in rel:                      # templated, e.g. commands/ddaro-<stage>.md
            continue
        assert (ROOT / rel).exists(), f"{path.name} points at missing {rel}"


def test_no_skills_dir_left():
    assert not (ROOT / "skills").exists()


# --- 0.10.0 merge gate: the command files must hand the gate's verdict through untouched ---

GATE_CALLERS = [p for p in COMMANDS if "hooks/gate.py" in p.read_text(encoding="utf-8")]


def test_gate_callers_exist():
    names = {p.name for p in GATE_CALLERS}
    assert {"ddaro-check.md", "ddaro-merge.md", "ddaro-clear.md", "ddaro-abandon.md"} <= names


@pytest.mark.parametrize("path", [p for p in GATE_CALLERS if p.name in ("ddaro-check.md", "ddaro-merge.md")], ids=lambda p: p.name)
def test_gate_callers_print_summary_verbatim(path):
    text = path.read_text(encoding="utf-8")
    assert "`summary`" in text and "verbatim" in text


def test_check_flow_uses_skill_tool_for_prism():
    text = (ROOT / "commands" / "ddaro-check.md").read_text(encoding="utf-8")
    assert "Skill tool" in text and "`prism:prism`" in text and "`prism_skill_args`" in text
    assert "check-begin <wt> [--full]" in text and "check-record <wt> --run <run>" in text
    for name in ("ddaro-check.md", "ddaro.md"):
        assert "Skill" in _frontmatter(ROOT / "commands" / name)["allowed-tools"], name


def test_merge_flow_has_gate_steps():
    text = (ROOT / "commands" / "ddaro-merge.md").read_text(encoding="utf-8")
    assert "gate.py\" status <main> --branch <branch>" in text
    assert "--match-head-commit <headRefOid>" in text and "--body-file" in text
    assert "close <main> <branch> --merged --pr <N>" in text


def test_hooks_json_registers_merge_gate_once():
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    cmds = [h["command"] for grp in hooks["hooks"]["PreToolUse"] for h in grp["hooks"]]
    assert sum("check-merge-gate.py" in c for c in cmds) == 1
