"""Doc lint (0.8.0): the merge-target branch must never be hardcoded as `main`
again in the skill / command prose, and every subcommand section must run the
schema migration.

Rules (0.8.0 design, D2):
  1. inside fenced code blocks, a line starting with `git` / `gh` (leading
     whitespace, `$`, `!` allowed) must not contain the word `main`
     (`<base>`, `<main_worktree>`, `main_worktree` do not match `\\bmain\\b`
     because `_` and `>` are word/non-word boundaries respectively - we check
     explicitly below).
  2. anywhere (case-insensitive): origin/main, --merged main, main.., ..main,
     -b d-<x> main, main@, "ahead of main".
  3. every `## /ddaro:<x>` section in SKILL.md mentions
     `config_tool.py ensure-schema`.
Exceptions: a line ending in `<!-- base-ref-ok -->` (rules 1-2), a heading
ending in `<!-- ensure-schema-ok -->` (rule 3), and the `## 용어` glossary.
README*.md are not linted.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "ddaro" / "SKILL.md"
DOCS = [SKILL, *sorted((ROOT / "commands").glob("*.md"))]

RULE2 = [re.compile(p, re.IGNORECASE) for p in (
    r"origin/main\b",
    r"--merged\s+main\b",
    r"\bmain\.\.",
    r"\.\.main\b",
    r"-b\s+d-\S+\s+main\b",
    r"\bmain@",
    r"ahead of main\b",
)]
_GIT_LINE = re.compile(r"^\s*[$!]?\s*(git|gh)\b")
_MAIN_WORD = re.compile(r"(?<![\w<>/_-])main(?![\w_>-])")
OK_MARK = "<!-- base-ref-ok -->"
SCHEMA_OK = "<!-- ensure-schema-ok -->"


def _violations(path: Path):
    out = []
    in_fence = False
    in_glossary = False
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.rstrip()
        s = line.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence and s.startswith("## "):
            in_glossary = s == "## 용어"
        if in_glossary or line.endswith(OK_MARK):
            continue
        if in_fence and _GIT_LINE.match(line) and _MAIN_WORD.search(line):
            out.append((n, "rule1", line))
            continue
        for rx in RULE2:
            if rx.search(line):
                out.append((n, "rule2", line))
                break
    return out


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
def test_no_hardcoded_base_ref(path):
    bad = _violations(path)
    assert not bad, "\n".join(f"{path.name}:{n} [{r}] {l}" for n, r, l in bad)


def test_every_subcommand_section_runs_ensure_schema():
    text = SKILL.read_text(encoding="utf-8")
    lines = text.splitlines()
    sections = []  # (heading, body)
    cur_head, cur_body, in_fence = None, [], False
    for ln in lines:
        if ln.strip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and ln.startswith("## "):
            if cur_head is not None:
                sections.append((cur_head, "\n".join(cur_body)))
            cur_head, cur_body = ln, []
        else:
            cur_body.append(ln)
    if cur_head is not None:
        sections.append((cur_head, "\n".join(cur_body)))
    missing = [h for h, body in sections
               if h.startswith("## /ddaro:") and not h.rstrip().endswith(SCHEMA_OK)
               and "config_tool.py ensure-schema" not in body]
    assert not missing, "sections without ensure-schema: " + ", ".join(missing)


def test_lint_catches_samples(tmp_path):
    sample = tmp_path / "x.md"
    sample.write_text(
        "```bash\ngit worktree add ../x -b d-1 main\n```\n"
        "text with origin/main here\n"
        "git -C <main_worktree> merge d-x  <!-- base-ref-ok -->\n"
        "```bash\ngit -C <main_worktree> merge d-<name>\ngit reset --hard origin/<base>\n```\n",
        encoding="utf-8")
    rules = [r for _, r, _ in _violations(sample)]
    assert rules == ["rule1", "rule2"]
