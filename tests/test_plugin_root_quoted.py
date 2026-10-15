"""Every shell command that runs a plugin file quotes ${CLAUDE_PLUGIN_ROOT}/<path>.

Unquoted, the expanded path splits on spaces, and under bash a Windows path loses
its backslashes. `claude plugin validate` warns about hooks.json; this test also
covers the command and reference files the model runs line by line.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = sorted((ROOT / "commands").glob("*.md")) + sorted((ROOT / "reference").glob("*.md"))
UNQUOTED = re.compile(r"\b(?:python3?|bash|sh|node) +\$\{CLAUDE_PLUGIN_ROOT\}")


def _hook_commands():
    data = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    for groups in data["hooks"].values():
        for group in groups:
            for hook in group["hooks"]:
                yield hook["command"]


def test_hook_commands_quote_plugin_root():
    bad = [c for c in _hook_commands() if UNQUOTED.search(c)]
    assert not bad, f"unquoted ${{CLAUDE_PLUGIN_ROOT}} in hooks.json: {bad}"


def test_hook_commands_found():
    assert len(list(_hook_commands())) >= 8


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
def test_docs_quote_plugin_root(path):
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if UNQUOTED.search(l)]
    assert not lines, f"{path.name}: unquoted ${{CLAUDE_PLUGIN_ROOT}} in {lines[:2]}"
