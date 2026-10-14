#!/usr/bin/env python3
"""ddaro context-MD writer (0.8.0). The ONLY code that writes
`<worktree>/.ddaro/context/<ts>-<sha7>.md` and `<worktree>/.ddaro/CURRENT.md`.
Slash-command prompts never write these files by hand; they call this script.

    python context_md.py hook                                   # PostToolUse(Bash) hook mode: stdin JSON
    python context_md.py init <root> --topic "<topic>" [--adopted]   # CURRENT.md only (start/adopt)
    python context_md.py write <root>                           # snapshot HEAD now (idempotent)
    python context_md.py enrich <root> <sha7>                   # stdin JSON {section: text}; /ddaro:commit step 8
                                                                # stdout: "enriched <sha7>" | "created+enriched <sha7>"; exit 0 on success, 1 on failure

Hook mode never blocks: exit 0 always, output only when a snapshot was
written (PostToolUse JSON with `additionalContext`). It runs on every Bash
call in every project, so every early-exit path is cheap and silent.

Format truth lives in the constants below. Headings are EXACT (no
suffixes); section lookup is `line.strip() == heading`. Every generated
file starts with FORMAT_MARKER; older/absent markers are read-only.
"""

from __future__ import annotations

import sys

# Fast path. In hook mode this script runs after EVERY Bash call in EVERY
# project where ddaro is enabled, so the common case (the command is not a
# commit) must cost no more than a bare interpreter start: read stdin as bytes
# and leave before importing json/re/subprocess/datetime (~60ms on Windows,
# measured 106ms -> 48ms per Bash call).
_HOOK_STDIN = None
if __name__ == "__main__" and sys.argv[1:2] == ["hook"]:
    try:
        _HOOK_STDIN = sys.stdin.buffer.read()
    except Exception:
        sys.exit(0)
    if b"commit" not in _HOOK_STDIN:
        sys.exit(0)

import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Dict, List, Optional, Tuple  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from _shared import (  # noqa: E402
    base_branch,
    command_git_commit_targets,
    cwd_from_payload,
    find_ddaro_config,
    native_path,
    persistence_enabled,
    read_payload,
    read_stdin_text,
    snapshot_enabled,
    utf8_stdio,
    worktree_root,
)

# --- format truth ---------------------------------------------------------

FORMAT_VERSION = 1
FORMAT_MARKER = f"<!-- ddaro-context v{FORMAT_VERSION} -->"

SNAPSHOT_SECTIONS = ("commit_message", "files_changed", "what_was_done", "next_planned", "review_flags")
CURRENT_SECTIONS = ("journey", "currently", "resume_hint")
HEADINGS = {
    "commit_message": "## Commit message",
    "files_changed": "## Files changed",
    "what_was_done": "## What was done",
    "next_planned": "## Next planned (inferred)",
    "review_flags": "## Review flags raised",
    "journey": "## Journey so far",
    "currently": "## Currently",
    "resume_hint": "## Resume hint",
}
ENRICH_KEYS = ("what_was_done", "next_planned", "review_flags", "currently", "resume_hint")

AUTO_NEXT = "(auto) run /ddaro:commit to enrich, or /ddaro:resume"
AUTO_FLAGS = "(auto) not analyzed"
DEFAULT_WINDOW_SEC = 900

_MARKER_RE = re.compile(r"^<!-- ddaro-context v(\d+) -->\s*$")


# --- git helpers ----------------------------------------------------------

def _git(args: List[str], cwd: Path, timeout: int = 5) -> Optional[str]:
    """stdout (stripped) or None on any failure.

    Bytes mode + explicit UTF-8: git emits UTF-8 (commit messages, and paths
    once `core.quotepath=off` stops it octal-escaping non-ASCII names), while
    `text=True` decodes with the Windows ANSI code page - Korean becomes
    mojibake, or a UnicodeDecodeError is raised inside subprocess's reader
    thread and the snapshot is silently lost."""
    try:
        r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=str(cwd),
                           capture_output=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.decode("utf-8", errors="replace").strip()


def _head_sha7(root: Path) -> Optional[str]:
    return _git(["rev-parse", "--short=7", "HEAD"], root) or None


def _branch(root: Path) -> str:
    return _git(["symbolic-ref", "--short", "HEAD"], root) or "(detached)"


def _ahead(root: Path, base: str) -> str:
    """rev-list count vs local <base>, then origin/<base>, else '?'."""
    for ref in (base, f"origin/{base}"):
        n = _git(["rev-list", "--count", f"{ref}..HEAD"], root)
        if n is not None and n.isdigit():
            return n
    return "?"


def _base_sha7(root: Path, base: str) -> str:
    for ref in (base, f"origin/{base}"):
        s = _git(["rev-parse", "--short=7", ref], root)
        if s:
            return s
    return "?"


def _push_status(root: Path) -> str:
    up = _git(["rev-parse", "--abbrev-ref", "@{u}"], root)
    if not up:
        return "no upstream"
    n = _git(["rev-list", "--count", "@{u}..HEAD"], root)
    if n is None or not n.isdigit():
        return f"{up} ?"
    return f"{up} up to date" if n == "0" else f"{up} {n} ahead (unpushed)"


def _uncommit(root: Path) -> str:
    out = _git(["status", "--porcelain"], root)
    if out is None:
        return "?"
    n = len([ln for ln in out.splitlines() if ln.strip()])
    return "none" if n == 0 else f"{n} files"


def _commit_message(root: Path) -> str:
    return _git(["log", "-1", "--format=%B", "HEAD"], root) or ""


def _committer_ts(root: Path) -> Optional[int]:
    v = _git(["log", "-1", "--format=%ct", "HEAD"], root)
    try:
        return int(v) if v else None
    except ValueError:
        return None


def _numstat(root: Path) -> Tuple[int, int, int, List[Tuple[str, str, str]]]:
    """(files, added, removed, [(path, added, removed)]) for HEAD."""
    out = _git(["diff-tree", "--no-commit-id", "--numstat", "-r", "--root", "HEAD"], root) or ""
    rows = []
    tot_a = tot_r = 0
    for ln in out.splitlines():
        parts = ln.split("\t")
        if len(parts) < 3:
            continue
        a, r, path = parts[0], parts[1], "\t".join(parts[2:])
        rows.append((path, a, r))
        if a.isdigit():
            tot_a += int(a)
        if r.isdigit():
            tot_r += int(r)
    return len(rows), tot_a, tot_r, rows


# --- worktree / config ----------------------------------------------------

def _managed_root(path: Path) -> Optional[Path]:
    """worktree_root(path) if it carries .ddaro/OWNED, else None."""
    root = worktree_root(path)
    if root is None:
        return None
    try:
        if (root / ".ddaro" / "OWNED").is_file():
            return root
    except Exception:
        pass
    return None


def _lock(root: Path) -> dict:
    try:
        return json.loads((root / ".ddaro" / "LOCK").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _context_dir(root: Path) -> Path:
    return root / ".ddaro" / "context"


def _current_path(root: Path) -> Path:
    return root / ".ddaro" / "CURRENT.md"


def _find_snapshot(root: Path, sha7: str) -> Optional[Path]:
    try:
        matches = sorted(_context_dir(root).glob(f"*-{sha7}.md"))
    except Exception:
        return None
    return matches[-1] if matches else None


# --- parsing --------------------------------------------------------------

def _marker_version(text: str) -> Optional[int]:
    first = text.split("\n", 1)[0] if text else ""
    m = _MARKER_RE.match(first)
    return int(m.group(1)) if m else None


def _parse_sections(text: str) -> Dict[str, List[str]]:
    """Map heading-key -> body lines (exact heading match; body runs until the
    next '## ' line). Unknown h2 headings are skipped."""
    by_heading = {v: k for k, v in HEADINGS.items()}
    out: Dict[str, List[str]] = {}
    key = None
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("## "):
            key = by_heading.get(s)
            if key is not None:
                out[key] = []
            continue
        if key is not None:
            out[key].append(ln.rstrip())
    for k, lines in out.items():
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
    return out


def _journey_lines(text: str) -> List[str]:
    return [ln for ln in _parse_sections(text).get("journey", []) if ln.strip()]


# --- rendering ------------------------------------------------------------

def _now() -> datetime:
    return datetime.now()


def _render_snapshot(branch: str, sha7: str, base: str, ahead: str, msg: str,
                     stat: Tuple[int, int, int, List[Tuple[str, str, str]]],
                     what: str, nxt: str, flags: str, when: datetime) -> str:
    files, add, rem, rows = stat
    lines = [
        FORMAT_MARKER,
        f"# {branch} - Commit {sha7}",
        "",
        f"**Time**: {when.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Branch**: {branch}",
        f"**Ahead of base ({base})**: {ahead} commit(s)",
        "",
        HEADINGS["commit_message"],
        msg.strip() or "(empty)",
        "",
        HEADINGS["files_changed"],
        f"{files} files, +{add} -{rem}",
    ]
    lines += [f"- {p} (+{a} -{r})" for p, a, r in rows]
    lines += [
        "",
        HEADINGS["what_was_done"],
        what.strip(),
        "",
        HEADINGS["next_planned"],
        nxt.strip(),
        "",
        HEADINGS["review_flags"],
        flags.strip(),
        "",
    ]
    return "\n".join(lines)


def _render_current(root: Path, branch: str, base: str, ahead: str, push: str, unc: str,
                    journey: List[str], currently: str, last_goal: str, next_expected: str,
                    when: datetime) -> str:
    lines = [
        FORMAT_MARKER,
        f"# {branch} - Current State",
        "",
        f"**Last updated**: {when.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Branch**: {branch}",
        f"**Total commits**: {ahead} ahead of base ({base})",
        f"**Push status**: {push}",
        f"**Uncommit**: {unc}",
        "",
        HEADINGS["journey"],
    ]
    lines += journey
    lines += [
        "",
        HEADINGS["currently"],
        currently.strip(),
        "",
        HEADINGS["resume_hint"],
        "If this session restarts:",
        f"- cwd: {root.as_posix()}",
        f"- Last goal: {last_goal}",
        f"- Next expected: {next_expected}",
        "",
    ]
    return "\n".join(lines)


def _parse_resume_hint(body: List[str]) -> Tuple[str, str]:
    goal, nxt = "", ""
    for ln in body:
        s = ln.strip()
        if s.startswith("- Last goal:"):
            goal = s[len("- Last goal:"):].strip()
        elif s.startswith("- Next expected:"):
            nxt = s[len("- Next expected:"):].strip()
    return goal, nxt


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- core operations ------------------------------------------------------

def _refresh_current(root: Path, cfg: dict, journey_add: Optional[str],
                     currently: Optional[str], last_goal: Optional[str],
                     next_expected: Optional[str], when: datetime) -> bool:
    """Re-render CURRENT.md: header from git, Journey preserved (+1 line if
    given), the rest from args or existing content. Returns True if the
    Journey block had to be reset (file missing or heading absent)."""
    base = base_branch(cfg)
    branch = _branch(root)
    path = _current_path(root)
    reset = False
    journey: List[str] = []
    old_cur, old_goal, old_next = "", "", ""
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
    except Exception:
        text = ""
    # CURRENT.md is regenerated every commit, so the Journey is preserved from
    # ANY file that has the exact `## Journey so far` heading - marker or not
    # (0.7.0 wrote these by prompt, without a marker). Only a missing file or
    # a file without that heading resets it.
    secs = _parse_sections(text) if text else {}
    if "journey" in secs:
        journey = [ln for ln in secs.get("journey", []) if ln.strip()]
        old_cur = "\n".join(secs.get("currently", [])).strip()
        old_goal, old_next = _parse_resume_hint(secs.get("resume_hint", []))
    else:
        reset = True
    if journey_add is not None:
        journey.append(f"{len(journey) + 1}. {journey_add}")
    lock = _lock(root)
    rendered = _render_current(
        root, branch, base, _ahead(root, base), _push_status(root), _uncommit(root),
        journey,
        currently if currently is not None else (old_cur or "Idle"),
        last_goal if last_goal is not None else (old_goal or str(lock.get("topic") or "")),
        next_expected if next_expected is not None else (old_next or "(auto) see /ddaro:resume"),
        when,
    )
    _write_text(path, rendered)
    return reset


def _write_snapshot(root: Path, cfg: dict, when: datetime) -> Tuple[Optional[Path], str]:
    """Write the HEAD snapshot + refresh CURRENT.md. Returns (path, ahead) or
    (None, "") when nothing was written (no HEAD, or duplicate)."""
    sha7 = _head_sha7(root)
    if not sha7:
        return None, ""
    if _find_snapshot(root, sha7) is not None:
        return None, ""
    base = base_branch(cfg)
    branch = _branch(root)
    ahead = _ahead(root, base)
    msg = _commit_message(root)
    first = (msg.strip().splitlines() or [""])[0]
    text = _render_snapshot(branch, sha7, base, ahead, msg, _numstat(root), first, AUTO_NEXT, AUTO_FLAGS, when)
    path = _context_dir(root) / f"{when.strftime('%Y-%m-%dT%H-%M-%S')}-{sha7}.md"
    _write_text(path, text)
    reset = _refresh_current(root, cfg, f"[{when.strftime('%H:%M')}] Commit {sha7} - {first}",
                             f"(auto) committed {sha7} just now", None, "(auto) see /ddaro:resume", when)
    if reset:
        print(f"[ddaro] CURRENT.md journey reset ({root.name})", file=sys.stderr)
    return path, ahead


def _mark_superseded(root: Path, new_sha7: str) -> None:
    prev = _git(["rev-parse", "--short=7", "HEAD@{1}"], root)
    if not prev or prev == new_sha7:
        return
    old = _find_snapshot(root, prev)
    if old is None:
        return
    try:
        text = old.read_text(encoding="utf-8")
        line = f"**Superseded by**: {new_sha7}"
        if line not in text:
            old.write_text(text.rstrip("\n") + "\n\n" + line + "\n", encoding="utf-8")
    except Exception:
        pass


# --- subcommands ----------------------------------------------------------

def cmd_hook() -> int:
    try:
        if _HOOK_STDIN is not None:  # already read by the fast path at import
            payload = json.loads(_HOOK_STDIN.decode("utf-8-sig", errors="replace"))
        else:
            payload = read_payload()
        if not isinstance(payload, dict) or (payload.get("tool_name") or "") != "Bash":
            return 0
        cmd = str((payload.get("tool_input") or {}).get("command") or "")
        if not cmd:
            return 0
        cwd = cwd_from_payload(payload)
        # Resolve the commit target both ways: relative to the payload cwd as
        # given, and following any `cd <dir>` earlier in the same command. The
        # payload cwd may be the cwd before or after the command ran; the union
        # is right in both cases, and the OWNED / freshness / dedupe checks
        # below discard the wrong candidate.
        targets = command_git_commit_targets(cmd, cwd) + command_git_commit_targets(cmd, cwd, follow_cd=True)
        if not targets:
            return 0
        try:
            window = int(os.environ.get("DDARO_SNAPSHOT_WINDOW_SEC") or DEFAULT_WINDOW_SEC)
        except ValueError:
            window = DEFAULT_WINDOW_SEC
        amend = "--amend" in cmd
        notes: List[str] = []
        seen = set()
        for t in targets:
            root = _managed_root(t)
            if root is None or str(root) in seen:
                continue
            seen.add(str(root))
            cfg = find_ddaro_config(root)
            if not cfg or not snapshot_enabled(cfg):
                continue
            ts = _committer_ts(root)
            if ts is None or (time.time() - ts) > window:
                continue
            path, ahead = _write_snapshot(root, cfg, _now())
            if path is None:
                continue
            if amend:
                _mark_superseded(root, path.name.rsplit("-", 1)[-1][:-3])
            rel = path.relative_to(root).as_posix()
            notes.append(f"[ddaro] snapshot written: {rel} (ahead {ahead})")
        if notes:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                     "additionalContext": "\n".join(notes)}}))
    except Exception:
        pass
    return 0


def _resolve_root(arg: str) -> Optional[Path]:
    root = _managed_root(Path(native_path(arg)))
    if root is None:
        print(f"[ddaro] not a ddaro-managed worktree (no .ddaro/OWNED): {arg}", file=sys.stderr)
    return root


def cmd_init(argv: List[str]) -> int:
    if not argv:
        print("usage: context_md.py init <root> --topic <topic> [--adopted]", file=sys.stderr)
        return 2
    root = _resolve_root(argv[0])
    if root is None:
        return 1
    topic, adopted = "", False
    i = 1
    while i < len(argv):
        if argv[i] == "--topic" and i + 1 < len(argv):
            topic = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--adopted":
            adopted = True
        i += 1
    cfg = find_ddaro_config(root) or {}
    if not persistence_enabled(cfg):
        return 0
    path = _current_path(root)
    if path.is_file():
        return 0
    when = _now()
    base = base_branch(cfg)
    branch = _branch(root)
    if adopted:
        first = f"[{when.strftime('%H:%M')}] Adopted from external worktree, branch {branch}"
    else:
        first = f"[{when.strftime('%H:%M')}] Worktree created, branch {branch} from {base}@{_base_sha7(root, base)}"
    rendered = _render_current(root, branch, base, _ahead(root, base), _push_status(root), _uncommit(root),
                               [f"1. {first}"], "Idle (just created)", topic or str(_lock(root).get("topic") or ""),
                               "(auto) see /ddaro:resume", when)
    _write_text(path, rendered)
    return 0


def cmd_write(argv: List[str]) -> int:
    if not argv:
        print("usage: context_md.py write <root>", file=sys.stderr)
        return 2
    root = _resolve_root(argv[0])
    if root is None:
        return 1
    cfg = find_ddaro_config(root) or {}
    if not persistence_enabled(cfg):
        return 0
    path, _ = _write_snapshot(root, cfg, _now())
    if path is not None:
        print(path.relative_to(root).as_posix())
    return 0


def cmd_enrich(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: context_md.py enrich <root> <sha7>  (stdin: JSON {section: text})", file=sys.stderr)
        return 2
    root = _resolve_root(argv[0])
    if root is None:
        return 1
    sha7 = argv[1][:7]
    cfg = find_ddaro_config(root) or {}
    if not persistence_enabled(cfg):
        print("[ddaro] context_persistence is false; nothing written", file=sys.stderr)
        return 0
    try:
        raw = read_stdin_text()  # UTF-8 regardless of locale (Korean summaries via heredoc)
        data = json.loads(raw) if raw.strip() else {}
        if not isinstance(data, dict):
            raise ValueError("JSON root must be an object")
    except Exception as e:
        print(f"[ddaro] enrich: bad JSON on stdin: {e}", file=sys.stderr)
        return 1
    for k in list(data):
        if k not in ENRICH_KEYS:
            print(f"[ddaro] enrich: unknown key '{k}' ignored", file=sys.stderr)
            data.pop(k)

    created = False
    snap = _find_snapshot(root, sha7)
    if snap is None:
        if _head_sha7(root) != sha7:
            print(f"[ddaro] enrich: no snapshot for {sha7} and HEAD differs; run `write` on the right commit", file=sys.stderr)
            return 1
        snap, _ = _write_snapshot(root, cfg, _now())
        if snap is None:
            print(f"[ddaro] enrich: could not create snapshot for {sha7}", file=sys.stderr)
            return 1
        created = True

    try:
        text = snap.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[ddaro] enrich: cannot read {snap}: {e}", file=sys.stderr)
        return 1
    if _marker_version(text) != FORMAT_VERSION:
        print(f"[ddaro] enrich: {snap.name} has no/old format marker; read-only", file=sys.stderr)
        return 1

    # Replace snapshot sections in place (exact heading match).
    lines = text.splitlines()
    for key in ("what_was_done", "next_planned", "review_flags"):
        if key not in data:
            continue
        val = str(data[key]).strip()
        heading = HEADINGS[key]
        try:
            start = next(i for i, ln in enumerate(lines) if ln.strip() == heading)
        except StopIteration:
            continue
        end = start + 1
        while end < len(lines) and not lines[end].strip().startswith("## "):
            end += 1
        body = val.splitlines() or [""]
        lines[start + 1:end] = body + [""]
    _write_text(snap, "\n".join(lines).rstrip("\n") + "\n")

    hint = data.get("resume_hint")
    goal = nxt = None
    if isinstance(hint, dict):
        goal = str(hint.get("last_goal")) if hint.get("last_goal") is not None else None
        nxt = str(hint.get("next_expected")) if hint.get("next_expected") is not None else None
    cur = str(data["currently"]) if "currently" in data else None
    _refresh_current(root, cfg, None, cur, goal, nxt, _now())
    # Success is always exit 0 so the prompt's "non-zero == failed" rule holds;
    # the stdout line tells which path was taken.
    print(f"{'created+enriched' if created else 'enriched'} {sha7}")
    return 0


def main(argv: List[str]) -> int:
    utf8_stdio()
    if not argv:
        print("usage: context_md.py hook | init <root> --topic <t> [--adopted] | write <root> | enrich <root> <sha7>",
              file=sys.stderr)
        return 2
    sub, rest = argv[0], argv[1:]
    if sub == "hook":
        return cmd_hook()
    if sub == "init":
        return cmd_init(rest)
    if sub == "write":
        return cmd_write(rest)
    if sub == "enrich":
        return cmd_enrich(rest)
    print(f"unknown subcommand: {sub}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
