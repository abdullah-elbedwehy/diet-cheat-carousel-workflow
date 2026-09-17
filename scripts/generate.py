#!/usr/bin/env python3
"""Parallel slide generator for the Diet & Cheat carousel workflow.

Reads a job.json (written by the agent), spawns one `codex exec` worker per
slide concurrently, exports each result to the delivery size with macOS `sips`,
runs mechanical checks only, and writes a manifest + review checklist.

No visual review happens here or in the workers. The user reviews.

Usage:
    generate.py JOB.json [--only 2,4] [--concurrency N] [--dry-run]
                          [--timeout SEC] [--no-export]

Requires: python3 (stdlib only), macOS `sips`, Codex CLI logged in.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
JOB_SCHEMA_VERSION = 1
DEFAULT_TIMEOUT_SEC = 900
DEFAULT_GENERATE_SIZE = "1024x1536"
DEFAULT_DELIVER_SIZE = "1080x1440"
SAVED_LINE = re.compile(r"^\s*SAVED:\s*(.+?)\s*$", re.MULTILINE)
MAX_ATTEMPTS = 2
MIN_FILE_BYTES = 20_000

WORKER_HEADER = """You are a single-image render worker. Use the imagegen skill with the built-in image_gen tool only (no CLI fallback, no OPENAI_API_KEY).

HARD RULES
- Generate exactly ONE image, exactly ONE image_gen call. Do not inspect, critique, validate, compare, or regenerate the result. A human reviews later.
- Portrait orientation, {generate_size} pixels.
- Save the generated file at exactly this path (relative to the working directory): {relative_out}
- After saving, print exactly one line and nothing else after it:
SAVED: <absolute path>
- Do not create any other files. Do not modify the attached reference images.

ATTACHED IMAGES
{ref_lines}

{shared_contract}

SLIDE {n} OF {total} — role: {role}

VISUAL DIRECTION
{visual}

TEXT TO RENDER VERBATIM (Arabic right-to-left, every character exactly as written, no additions, no corrections, no other text anywhere on the image):
```text
{copy}
```
"""


def log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


def parse_size(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", text or "")
    if not m:
        die(f"bad size '{text}', expected WxH")
    return int(m.group(1)), int(m.group(2))


def slugify(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text or "carousel"


def load_job(path: Path) -> dict:
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        die(f"job file not found: {path}")
    except json.JSONDecodeError as exc:
        die(f"job file is not valid JSON: {exc}")

    if job.get("schema") != JOB_SCHEMA_VERSION:
        die(f"job.schema must be {JOB_SCHEMA_VERSION}")
    identity = str(job.get("identity", "")).upper()
    if identity not in {"OLD", "NEW"}:
        die("job.identity must be OLD or NEW")
    job["identity"] = identity
    job["topic_slug"] = slugify(str(job.get("topic_slug", "")))
    if not isinstance(job.get("shared_contract"), str) or not job["shared_contract"].strip():
        die("job.shared_contract must be a non-empty string")
    slides = job.get("slides")
    if not isinstance(slides, list) or not slides:
        die("job.slides must be a non-empty list")
    seen = set()
    for s in slides:
        n = s.get("n")
        if not isinstance(n, int) or n < 1:
            die("every slide needs an integer n >= 1")
        if n in seen:
            die(f"duplicate slide n={n}")
        seen.add(n)
        for key in ("role", "copy", "visual"):
            if not isinstance(s.get(key), str) or not s[key].strip():
                die(f"slide {n}: '{key}' must be a non-empty string")
    slides.sort(key=lambda s: s["n"])
    size = job.setdefault("size", {})
    size.setdefault("generate", DEFAULT_GENERATE_SIZE)
    size.setdefault("deliver", DEFAULT_DELIVER_SIZE)
    parse_size(size["generate"])
    parse_size(size["deliver"])
    refs = job.setdefault("refs", [])
    if not isinstance(refs, list):
        die("job.refs must be a list of paths")
    return job


def resolve_ref(ref: str) -> Path:
    p = Path(ref)
    if not p.is_absolute():
        p = SKILL_ROOT / p
    if not p.is_file():
        die(f"reference image not found: {p}")
    return p


def default_output_dir(job: dict) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    name = f"DC-{job['identity']}-{job['topic_slug']}-{stamp}"
    return Path.home() / "Downloads" / name


def file_name(job: dict, n: int, suffix: str = "") -> str:
    return f"DC-{job['identity']}-{job['topic_slug']}-slide{n:02d}{suffix}.png"


def build_prompt(job: dict, slide: dict, total: int, relative_out: str, refs: list[Path]) -> str:
    ref_lines = "\n".join(
        f"- Image {i + 1}: {label_for_ref(p)}" for i, p in enumerate(refs)
    ) or "- (none)"
    return WORKER_HEADER.format(
        generate_size=job["size"]["generate"],
        relative_out=relative_out,
        ref_lines=ref_lines,
        shared_contract=job["shared_contract"].strip(),
        n=slide["n"],
        total=total,
        role=slide["role"],
        visual=slide["visual"].strip(),
        copy=slide["copy"].strip("\n"),
    )


def label_for_ref(p: Path) -> str:
    name = p.name.lower()
    if "logo" in name:
        return f"{p.name} — exact production logo. Reproduce it once, faithfully. Do not redraw, recolor, duplicate, or invent a different mark."
    if "example" in name:
        return f"{p.name} — finished slide from this brand. Match its finish, lighting, type hierarchy, margins, and decoration density. Do not copy its content."
    if "identity" in name or "palette" in name or "typography" in name:
        return f"{p.name} — palette / type reference only."
    if "layout" in name:
        return f"{p.name} — approved two-choice comparison layout. Follow its structure."
    return f"{p.name} — style reference."


def sips_dims(path: Path) -> tuple[int, int] | None:
    try:
        out = subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
            capture_output=True, text=True, check=True, timeout=60,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
    w = re.search(r"pixelWidth:\s*(\d+)", out)
    h = re.search(r"pixelHeight:\s*(\d+)", out)
    if not (w and h):
        return None
    return int(w.group(1)), int(h.group(1))


def export_to_delivery(src: Path, dst: Path, deliver: tuple[int, int]) -> tuple[int, int] | None:
    """Centered crop to the delivery aspect ratio, then proportional resize. No other edits."""
    dims = sips_dims(src)
    if not dims:
        return None
    sw, sh = dims
    dw, dh = deliver
    target_ratio = dw / dh
    src_ratio = sw / sh
    if abs(src_ratio - target_ratio) < 1e-3:
        crop_w, crop_h = sw, sh
    elif src_ratio > target_ratio:
        crop_h = sh
        crop_w = int(round(sh * target_ratio))
    else:
        crop_w = sw
        crop_h = int(round(sw / target_ratio))
    dst.parent.mkdir(parents=True, exist_ok=True)
    # sips ignores CLI option order and derives resample factors from the original
    # dimensions, so crop and resize must be two separate invocations.
    steps: list[list[str]] = []
    if (crop_w, crop_h) != (sw, sh):
        steps.append(["sips", "-c", str(crop_h), str(crop_w), str(src), "--out", str(dst)])
        steps.append(["sips", "-z", str(dh), str(dw), str(dst)])
    else:
        steps.append(["sips", "-z", str(dh), str(dw), str(src), "--out", str(dst)])
    for cmd in steps:
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            log(f"export failed for {src.name}: {exc}")
            return None
    return sips_dims(dst)


class Worker:
    def __init__(self, job: dict, slide: dict, total: int, out_dir: Path, refs: list[Path],
                 timeout: int, dry_run: bool):
        self.job = job
        self.slide = slide
        self.n = slide["n"]
        self.total = total
        self.out_dir = out_dir
        self.refs = refs
        self.timeout = timeout
        self.dry_run = dry_run
        self.source_dir = out_dir / "source"
        self.log_dir = out_dir / "logs"
        self.source_name = file_name(job, self.n, "-source")
        self.source_path = self.source_dir / self.source_name
        self.result: dict = {
            "n": self.n,
            "role": slide["role"],
            "status": "pending",
            "attempts": 0,
            "source": None,
            "source_dims": None,
            "final": None,
            "final_dims": None,
            "seconds": 0.0,
            "error": None,
        }

    def prompt(self) -> str:
        return build_prompt(self.job, self.slide, self.total, f"./{self.source_name}", self.refs)

    def command(self) -> list[str]:
        cmd = ["codex", "exec", "--full-auto", "--skip-git-repo-check", "--ephemeral",
               "-C", str(self.source_dir)]
        for ref in self.refs:
            cmd += ["-i", str(ref)]
        cmd += ["--", self.prompt()]
        return cmd

    def run(self) -> None:
        started = time.monotonic()
        self.source_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        (self.log_dir / f"slide{self.n:02d}.prompt.txt").write_text(self.prompt(), encoding="utf-8")
        if self.dry_run:
            self.result["status"] = "dry-run"
            return
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self.result["attempts"] = attempt
            log(f"slide {self.n:02d}: attempt {attempt} start")
            ok, err = self._run_once(attempt)
            if ok:
                self.result["status"] = "generated"
                self.result["error"] = None
                break
            self.result["error"] = err
            log(f"slide {self.n:02d}: attempt {attempt} failed — {err}")
        else:
            self.result["status"] = "failed"
        self.result["seconds"] = round(time.monotonic() - started, 1)

    def _run_once(self, attempt: int) -> tuple[bool, str | None]:
        log_path = self.log_dir / f"slide{self.n:02d}.attempt{attempt}.log"
        try:
            with log_path.open("w", encoding="utf-8") as fh:
                proc = subprocess.run(
                    self.command(), stdout=fh, stderr=subprocess.STDOUT,
                    text=True, timeout=self.timeout, cwd=self.source_dir,
                )
        except subprocess.TimeoutExpired:
            return False, f"timeout after {self.timeout}s"
        except FileNotFoundError:
            return False, "codex CLI not found on PATH"
        output = log_path.read_text(encoding="utf-8", errors="replace")
        saved = self._locate_saved(output)
        if proc.returncode != 0 and not saved:
            return False, f"codex exit {proc.returncode} (see {log_path.name})"
        if not saved:
            return False, f"no image at expected path (see {log_path.name})"
        if saved != self.source_path:
            shutil.move(str(saved), str(self.source_path))
        size = self.source_path.stat().st_size
        if size < MIN_FILE_BYTES:
            return False, f"file too small ({size} bytes)"
        dims = sips_dims(self.source_path)
        if not dims:
            return False, "could not read image dimensions"
        self.result["source"] = str(self.source_path)
        self.result["source_dims"] = f"{dims[0]}x{dims[1]}"
        return True, None

    def _locate_saved(self, output: str) -> Path | None:
        if self.source_path.is_file():
            return self.source_path
        for m in SAVED_LINE.finditer(output):
            p = Path(m.group(1).strip().strip("`'\""))
            if not p.is_absolute():
                p = self.source_dir / p
            if p.is_file():
                return p
        pngs = sorted(self.source_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        expected_prefix = file_name(self.job, self.n, "-source").rsplit("-source", 1)[0]
        for p in pngs:
            if p.name.startswith(expected_prefix) and "-source" in p.name:
                return p
        return None


def archive_previous(out_dir: Path, job: dict, n: int, manifest: dict) -> None:
    """Move an existing final/source for slide n into history/ before regenerating."""
    history = out_dir / "history"
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    moved = False
    for sub, suffix in (("slides", ""), ("source", "-source")):
        p = out_dir / sub / file_name(job, n, suffix)
        if p.is_file():
            history.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(history / file_name(job, n, f"{suffix}-{stamp}")))
            moved = True
    if moved:
        manifest.setdefault("history", []).append({"n": n, "archived_at": stamp})


def write_brief_and_prompts(out_dir: Path, job: dict, refs: list[Path]) -> None:
    lines = [f"# Brief — {job['identity']} — {job['topic_slug']}", "",
             "Supplied copy, verbatim. Locked.", ""]
    for s in job["slides"]:
        lines += [f"## Slide {s['n']:02d} — {s['role']}", "", "```text", s["copy"].strip("\n"), "```", ""]
    (out_dir / "brief.md").write_text("\n".join(lines), encoding="utf-8")

    p = [f"# Prompt set — {job['identity']} — {job['topic_slug']}", "",
         f"Generate size: `{job['size']['generate']}` → deliver `{job['size']['deliver']}`", "",
         "## References attached to every worker", ""]
    p += [f"- `{r.name}`" for r in refs] or ["- (none)"]
    p += ["", "## Shared contract", "", job["shared_contract"].strip(), ""]
    for s in job["slides"]:
        p += [f"## Slide {s['n']:02d} — {s['role']}", "", "### Visual", "", s["visual"].strip(), "",
              "### Copy (verbatim)", "", "```text", s["copy"].strip("\n"), "```", ""]
    (out_dir / "prompts.md").write_text("\n".join(p), encoding="utf-8")


def write_review(out_dir: Path, job: dict, manifest: dict) -> None:
    lines = [f"# Review — {job['identity']} — {job['topic_slug']}", "",
             "الـAI مراجعش الصور. راجع كل سلايد وعلّم اللي فيه مشكلة.", "",
             "لو فيه سلايد محتاج إعادة: قول للـAI `regenerate slide N` + المشكلة بالظبط",
             "(مثال: `slide 3: الكلمة الإنجليزية اتعكست`). المشكلة بتتسجل كدرس وتتطبق في الإعادة.", "",
             "| Slide | Status | Dims | نص صح؟ | لوجو صح؟ | تكوين صح؟ | ملاحظة |",
             "|---|---|---|---|---|---|---|"]
    for r in manifest["slides"]:
        lines.append(f"| {r['n']:02d} | {r['status']} | {r.get('final_dims') or '-'} |  |  |  |  |")
    lines += ["", "## Files", "", f"- Final slides: `slides/`", f"- Raw generations: `source/`",
              f"- Prompts used: `prompts.md`", f"- Worker logs: `logs/`", ""]
    (out_dir / "REVIEW.md").write_text("\n".join(lines), encoding="utf-8")


def append_run_log(job: dict, manifest: dict) -> None:
    runs = SKILL_ROOT / "learnings" / "local" / "runs.jsonl"
    runs.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "at": manifest["finished_at"],
        "identity": job["identity"],
        "topic_slug": job["topic_slug"],
        "output_dir": manifest["output_dir"],
        "slides": [{"n": r["n"], "role": r["role"], "status": r["status"], "attempts": r["attempts"]}
                   for r in manifest["slides"]],
        "lessons_applied": job.get("lessons_applied", []),
        "regenerate_only": manifest.get("only"),
    }
    with runs.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def print_table(manifest: dict) -> None:
    print()
    print(f"Output: {manifest['output_dir']}")
    print()
    print(f"{'slide':<7}{'status':<12}{'source':<12}{'final':<12}{'sec':<8}error")
    for r in manifest["slides"]:
        print(f"{r['n']:02d}     {r['status']:<12}{(r.get('source_dims') or '-'):<12}"
              f"{(r.get('final_dims') or '-'):<12}{r.get('seconds', 0):<8}{r.get('error') or ''}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job", type=Path)
    ap.add_argument("--only", help="comma-separated slide numbers to (re)generate, e.g. 2,4")
    ap.add_argument("--concurrency", type=int, default=0, help="max parallel workers (0 = all)")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SEC, help="seconds per worker attempt")
    ap.add_argument("--dry-run", action="store_true", help="write prompts/logs, run nothing")
    ap.add_argument("--no-export", action="store_true", help="skip sips export to delivery size")
    ap.add_argument("--output-dir", type=Path, help="override output folder (default: ~/Downloads/DC-...)")
    args = ap.parse_args()

    if shutil.which("codex") is None and not args.dry_run:
        die("codex CLI not found on PATH")
    if shutil.which("sips") is None and not args.no_export:
        die("sips not found — this runner needs macOS")

    job = load_job(args.job)
    refs = [resolve_ref(r) for r in job["refs"]]
    total = len(job["slides"])

    out_dir = args.output_dir or (Path(job["output_dir"]) if job.get("output_dir") else default_output_dir(job))
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    job["output_dir"] = str(out_dir)
    (out_dir / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {
        "identity": job["identity"], "topic_slug": job["topic_slug"], "output_dir": str(out_dir),
        "slides": [], "history": [],
    }

    only = None
    if args.only:
        try:
            only = sorted({int(x) for x in args.only.split(",") if x.strip()})
        except ValueError:
            die("--only expects comma-separated integers")
        known = {s["n"] for s in job["slides"]}
        missing = [n for n in only if n not in known]
        if missing:
            die(f"--only names slides not in job: {missing}")
    manifest["only"] = only

    selected = [s for s in job["slides"] if only is None or s["n"] in only]
    for s in selected:
        archive_previous(out_dir, job, s["n"], manifest)

    write_brief_and_prompts(out_dir, job, refs)

    workers = [Worker(job, s, total, out_dir, refs, args.timeout, args.dry_run) for s in selected]
    limit = args.concurrency if args.concurrency > 0 else len(workers)
    gate = threading.Semaphore(limit)
    log(f"dispatching {len(workers)} worker(s), concurrency {limit}, identity {job['identity']}")

    def runner(w: Worker) -> None:
        with gate:
            w.run()

    threads = [threading.Thread(target=runner, args=(w,), daemon=True) for w in workers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    deliver = parse_size(job["size"]["deliver"])
    for w in workers:
        r = w.result
        if r["status"] == "generated" and not args.no_export:
            final = out_dir / "slides" / file_name(job, w.n)
            dims = export_to_delivery(w.source_path, final, deliver)
            if dims:
                r["final"] = str(final)
                r["final_dims"] = f"{dims[0]}x{dims[1]}"
                r["status"] = "delivered" if dims == deliver else "delivered-wrong-dims"
            else:
                r["status"] = "export-failed"
        elif r["status"] == "generated":
            r["final"] = r["source"]
            r["final_dims"] = r["source_dims"]
            r["status"] = "delivered-unexported"

    by_n = {r["n"]: r for r in manifest["slides"]}
    for w in workers:
        by_n[w.n] = w.result
    manifest["slides"] = [by_n[k] for k in sorted(by_n)]
    manifest["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
    manifest["generate_size"] = job["size"]["generate"]
    manifest["deliver_size"] = job["size"]["deliver"]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_review(out_dir, job, manifest)
    if not args.dry_run:
        append_run_log(job, manifest)

    print_table(manifest)
    failed = [r for r in manifest["slides"] if r["status"] in {"failed", "export-failed"}]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
