#!/usr/bin/env python3
"""Lesson store for the Diet & Cheat carousel workflow.

Lessons live in two Markdown files with identical block format:
  learnings/shared/lessons.md   — in git, curated by the maintainer
  learnings/local/lessons.md    — gitignored, per machine

Block format (one per lesson):

    ## L-20260917-001
    - date: 2026-09-17
    - identity: OLD | NEW | BOTH
    - status: active | retired
    - trigger: what the user said, verbatim or close
    - pattern: what in the copy / prompt caused it
    - rule: the instruction to inject into the shared contract next time

Usage:
    learn.py add --identity OLD --trigger "..." --pattern "..." --rule "..."
    learn.py list [--identity OLD|NEW] [--all] [--json] [--rules-only]
    learn.py retire L-20260917-001
    learn.py promote            # move active local lessons into shared (maintainer)
    learn.py runs [--last N]    # show recent run log entries
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
SHARED = SKILL_ROOT / "learnings" / "shared" / "lessons.md"
LOCAL = SKILL_ROOT / "learnings" / "local" / "lessons.md"
RUNS = SKILL_ROOT / "learnings" / "local" / "runs.jsonl"
FIELDS = ("date", "identity", "status", "trigger", "pattern", "rule")
IDENTITIES = {"OLD", "NEW", "BOTH"}
STATUSES = {"active", "retired"}
BLOCK_RE = re.compile(r"^## (L-\d{8}-\d{3})\s*$", re.MULTILINE)
FIELD_RE = re.compile(r"^- (\w+):\s*(.*)$")


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def parse_file(path: Path, source: str) -> list[dict]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    lessons = []
    matches = list(BLOCK_RE.finditer(text))
    for i, m in enumerate(matches):
        body = text[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        lesson = {"id": m.group(1), "source": source}
        for line in body.splitlines():
            fm = FIELD_RE.match(line.strip())
            if fm and fm.group(1) in FIELDS:
                lesson[fm.group(1)] = fm.group(2).strip()
        missing = [f for f in FIELDS if f not in lesson]
        if missing:
            print(f"WARN: {source} lesson {lesson['id']} missing {missing}; skipped", file=sys.stderr)
            continue
        lessons.append(lesson)
    return lessons


def load_all() -> list[dict]:
    shared = parse_file(SHARED, "shared")
    local = parse_file(LOCAL, "local")
    merged: dict[str, dict] = {l["id"]: l for l in shared}
    for l in local:
        merged[l["id"]] = l  # local wins on id clash
    return sorted(merged.values(), key=lambda l: l["id"])


def render(lesson: dict) -> str:
    lines = [f"## {lesson['id']}"]
    lines += [f"- {f}: {lesson[f]}" for f in FIELDS]
    return "\n".join(lines) + "\n"


def write_file(path: Path, lessons: list[dict], title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    head = f"# {title}\n\nFormat: see `references/learning.md`. One `## L-...` block per lesson.\n\n"
    path.write_text(head + "\n".join(render(l) for l in lessons), encoding="utf-8")


def next_id(existing: list[dict]) -> str:
    today = dt.date.today().strftime("%Y%m%d")
    prefix = f"L-{today}-"
    nums = [int(l["id"][-3:]) for l in existing if l["id"].startswith(prefix)]
    return f"{prefix}{(max(nums) + 1 if nums else 1):03d}"


def one_line(text: str, name: str) -> str:
    text = " ".join(text.split())
    if not text:
        die(f"--{name} must not be empty")
    return text


def cmd_add(args: argparse.Namespace) -> int:
    identity = args.identity.upper()
    if identity not in IDENTITIES:
        die("--identity must be OLD, NEW, or BOTH")
    all_lessons = load_all()
    lesson = {
        "id": next_id(all_lessons),
        "source": "local",
        "date": dt.date.today().isoformat(),
        "identity": identity,
        "status": "active",
        "trigger": one_line(args.trigger, "trigger"),
        "pattern": one_line(args.pattern, "pattern"),
        "rule": one_line(args.rule, "rule"),
    }
    local = parse_file(LOCAL, "local") + [lesson]
    write_file(LOCAL, local, "Local lessons")
    print(lesson["id"])
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    lessons = load_all()
    if not args.all:
        lessons = [l for l in lessons if l["status"] == "active"]
    if args.identity:
        want = args.identity.upper()
        lessons = [l for l in lessons if l["identity"] in {want, "BOTH"}]
    if args.json:
        print(json.dumps(lessons, ensure_ascii=False, indent=2))
        return 0
    if args.rules_only:
        for l in lessons:
            print(f"- [{l['id']}] {l['rule']}")
        return 0
    if not lessons:
        print("(no lessons)")
        return 0
    for l in lessons:
        print(f"{l['id']}  {l['identity']:<4} {l['status']:<8} ({l['source']})")
        print(f"  trigger: {l['trigger']}")
        print(f"  pattern: {l['pattern']}")
        print(f"  rule:    {l['rule']}")
    return 0


def cmd_retire(args: argparse.Namespace) -> int:
    hit = False
    for path, title in ((LOCAL, "Local lessons"), (SHARED, "Shared lessons")):
        lessons = parse_file(path, "x")
        for l in lessons:
            if l["id"] == args.id:
                l["status"] = "retired"
                hit = True
        if hit:
            write_file(path, lessons, title)
            print(f"retired {args.id} in {path.relative_to(SKILL_ROOT)}")
            return 0
    die(f"lesson {args.id} not found")
    return 2


def cmd_promote(_: argparse.Namespace) -> int:
    local = parse_file(LOCAL, "local")
    active = [l for l in local if l["status"] == "active"]
    if not active:
        print("nothing to promote")
        return 0
    shared = parse_file(SHARED, "shared")
    ids = {l["id"] for l in shared}
    for l in active:
        l["source"] = "shared"
        if l["id"] in ids:
            shared = [l if s["id"] == l["id"] else s for s in shared]
        else:
            shared.append(l)
    shared.sort(key=lambda l: l["id"])
    write_file(SHARED, shared, "Shared lessons")
    remaining = [l for l in local if l["status"] != "active"]
    write_file(LOCAL, remaining, "Local lessons")
    print(f"promoted {len(active)} lesson(s) to {SHARED.relative_to(SKILL_ROOT)}")
    print("next: git add learnings/shared/lessons.md && git commit && git push")
    return 0


def cmd_runs(args: argparse.Namespace) -> int:
    if not RUNS.is_file():
        print("(no runs yet)")
        return 0
    lines = RUNS.read_text(encoding="utf-8").splitlines()
    for line in lines[-args.last:]:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        statuses = ",".join(f"{s['n']}:{s['status']}" for s in e.get("slides", []))
        print(f"{e.get('at')}  {e.get('identity')}  {e.get('topic_slug')}  [{statuses}]")
        print(f"  {e.get('output_dir')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="record a new local lesson")
    a.add_argument("--identity", required=True)
    a.add_argument("--trigger", required=True)
    a.add_argument("--pattern", required=True)
    a.add_argument("--rule", required=True)
    a.set_defaults(fn=cmd_add)

    l = sub.add_parser("list", help="list lessons (active by default)")
    l.add_argument("--identity")
    l.add_argument("--all", action="store_true")
    l.add_argument("--json", action="store_true")
    l.add_argument("--rules-only", action="store_true")
    l.set_defaults(fn=cmd_list)

    r = sub.add_parser("retire", help="mark a lesson retired")
    r.add_argument("id")
    r.set_defaults(fn=cmd_retire)

    p = sub.add_parser("promote", help="move active local lessons into shared")
    p.set_defaults(fn=cmd_promote)

    u = sub.add_parser("runs", help="show recent run log")
    u.add_argument("--last", type=int, default=10)
    u.set_defaults(fn=cmd_runs)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
