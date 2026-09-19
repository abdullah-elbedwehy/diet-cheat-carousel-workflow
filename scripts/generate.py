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
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
if importlib.util.find_spec("PIL") is None:
    bundled_python = SKILL_ROOT / ".venv" / "bin" / "python"
    if bundled_python.is_file() and Path(sys.executable).resolve() != bundled_python.resolve():
        os.execv(str(bundled_python), [str(bundled_python), str(Path(__file__).resolve()), *sys.argv[1:]])

from image_processing import flatten_background, image_info

JOB_SCHEMA_VERSION = 2
DEFAULT_TIMEOUT_SEC = 900
DEFAULT_GENERATE_SIZE = "1024x1536"
DEFAULT_DELIVER_SIZE = "1080x1440"
DEFAULT_BACKGROUNDS = {"OLD": "#12181D", "NEW": "#091521"}
DEFAULT_BACKGROUND_TOLERANCE = 12
SAVED_LINE = re.compile(r"^\s*SAVED:\s*(.+?)\s*$", re.MULTILINE)
MAX_ATTEMPTS = 2
MIN_FILE_BYTES = 20_000
DISPATCH_SPREAD_THRESHOLD_SEC = 2.0
EVENT_LOCK = threading.Lock()

WORKER_HEADER = """You are a single-image render worker. Use the imagegen skill with the built-in image_gen tool only (no CLI fallback, no OPENAI_API_KEY).

HARD RULES
- Generate exactly ONE image, exactly ONE image_gen call. Do not inspect, critique, validate, compare, or regenerate the result. A human reviews later.
- Portrait orientation, {generate_size} pixels.
- Save the generated file at exactly this path (relative to the working directory): {relative_out}
- The built-in tool writes its output under $CODEX_HOME/generated_images/<session>/*.png. Copy that file (cp) to the path above.
- After saving, print exactly one line and nothing else after it:
SAVED: <absolute path>
- Do not create any other files. Do not modify the attached reference images.

ATTACHED IMAGES
{ref_lines}

{shared_contract}

SLIDE {n} OF {total} — role: {role}

VISUAL DIRECTION
{visual}

MEANING LOCK
- What this slide must communicate: {intent}
- Named object that must remain: {subject}
{regeneration_constraint}

TEXT TO RENDER VERBATIM (Arabic right-to-left, every character exactly as written, no additions, no corrections, no other text anywhere on the image):
```text
{copy}
```
"""


def log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def write_event(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with EVENT_LOCK, path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


def parse_size(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", text or "")
    if not m:
        die(f"bad size '{text}', expected WxH")
    return int(m.group(1)), int(m.group(2))


def parse_hex(text: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"#([0-9A-Fa-f]{6})", text or "")
    if not match:
        die(f"bad color '{text}', expected #RRGGBB")
    raw = match.group(1)
    return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))


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
    if identity not in DEFAULT_BACKGROUNDS:
        die("job.identity must be OLD or NEW")
    job["identity"] = identity
    job["topic_slug"] = slugify(str(job.get("topic_slug", "")))
    if not isinstance(job.get("shared_contract"), str) or not job["shared_contract"].strip():
        die("job.shared_contract must be a non-empty string")
    render_spec = (SKILL_ROOT / "references" / "render-spec.md").read_text(encoding="utf-8").strip("\n")
    if render_spec not in job["shared_contract"]:
        die("job.shared_contract must contain references/render-spec.md verbatim")
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
        for key in ("role", "intent", "subject", "copy", "visual"):
            if not isinstance(s.get(key), str) or not s[key].strip():
                die(f"slide {n}: '{key}' must be a non-empty string")
        if "\n" in s["visual"].strip():
            die(f"slide {n}: visual must be exactly one line")
        validate_gold_assignment(s)
    slides.sort(key=lambda s: s["n"])
    size = job.setdefault("size", {})
    size.setdefault("generate", DEFAULT_GENERATE_SIZE)
    size.setdefault("deliver", DEFAULT_DELIVER_SIZE)
    parse_size(size["generate"])
    parse_size(size["deliver"])
    background = job.setdefault("background", {})
    background.setdefault("hex", DEFAULT_BACKGROUNDS[identity])
    background.setdefault("tolerance", DEFAULT_BACKGROUND_TOLERANCE)
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(background["hex"])):
        die("job.background.hex must be #RRGGBB")
    if not isinstance(background["tolerance"], int) or background["tolerance"] < 0:
        die("job.background.tolerance must be an integer >= 0")
    refs = job.setdefault("refs", [])
    if not isinstance(refs, list):
        die("job.refs must be a list of paths")
    return job


GOLD_PARTS = {
    "dot", "point", "tip", "handle", "knob", "rung", "step", "band",
    "stripe", "mark", "accent", "segment", "connector", "divider", "rule",
    "نقطة", "طرف", "مقبض", "درجة", "خطوة", "شريط", "علامة", "جزء",
}
WHOLE_OBJECTS = {
    "balloon", "staircase", "stairs", "organ", "brain", "stomach", "heart",
    "door", "tank", "glass", "shaker", "moon", "clock", "puzzle", "chair",
    "suitcase", "بالونة", "سلم", "عضو", "مخ", "معدة", "باب", "خزان",
}


def validate_gold_assignment(slide: dict) -> None:
    """Reject a scene line that assigns gold to a whole object."""
    visual = str(slide.get("visual") or "").lower()
    if not any(token in visual for token in ("gold", "ذهبي", "دهبي")):
        return
    has_part = any(re.search(rf"\b{re.escape(part)}\b", visual) for part in GOLD_PARTS)
    explicit_whole = bool(re.search(r"\b(?:whole|entire|full)\b.{0,30}\bgold\b|\bgold\b.{0,30}\b(?:whole|entire|full)\b", visual))
    named_gold_object = any(
        re.search(rf"\b(?:gold|golden)\s+{re.escape(obj)}\b|\b{re.escape(obj)}\b.{{0,18}}\b(?:is|in)\s+gold\b", visual)
        for obj in WHOLE_OBJECTS
    )
    if explicit_whole or named_gold_object or not has_part:
        die(
            f"slide {slide.get('n')}: gold assignment names a whole object or no small object part; "
            "rewrite the scene before generation"
        )


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
        intent=slide["intent"].strip(),
        subject=slide["subject"].strip(),
        regeneration_constraint=regeneration_constraint(slide),
        copy=slide["copy"].strip("\n"),
    )


def regeneration_constraint(slide: dict) -> str:
    regeneration = slide.get("regeneration")
    if not isinstance(regeneration, dict):
        return "- First generation: preserve the stated intent and named object."
    reason = str(regeneration.get("reason") or "").strip()
    failure_class = str(regeneration.get("failure_class") or "").strip()
    return (
        f"- Regeneration failure class: {failure_class}; reason: {reason}. "
        "Change only what that reason requires. Preserve the intent and named object unless failure_class is object."
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


def export_to_delivery(
    src: Path,
    dst: Path,
    deliver: tuple[int, int],
    background_rgb: tuple[int, int, int] = (18, 24, 29),
    background_tolerance: int = DEFAULT_BACKGROUND_TOLERANCE,
) -> tuple[tuple[int, int], dict]:
    """Export exact pixels, flatten near-background colors, then hard-verify.

    The former crop path resized the crop in place. On affected `sips` builds
    that left the crop at its source dimensions (for example 1122x1402). Each
    stage now has a distinct input/output file. Any dimension mismatch raises a
    hard failure; this function never rounds, accepts a near match, or retries a
    resize silently.
    """
    dims = sips_dims(src)
    if not dims:
        raise RuntimeError(f"could not read source dimensions: {src}")
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
    with tempfile.TemporaryDirectory(prefix="dc-export-", dir=dst.parent) as temporary:
        temporary_dir = Path(temporary)
        cropped = temporary_dir / "01-cropped.png"
        resized = temporary_dir / "02-resized.png"
        flattened = temporary_dir / "03-flattened.png"
        crop_input = src
        if (crop_w, crop_h) != (sw, sh):
            subprocess.run(
                ["sips", "-c", str(crop_h), str(crop_w), str(src), "--out", str(cropped)],
                capture_output=True, text=True, check=True, timeout=120,
            )
            crop_input = cropped
        subprocess.run(
            ["sips", "-z", str(dh), str(dw), str(crop_input), "--out", str(resized)],
            capture_output=True, text=True, check=True, timeout=120,
        )
        resized_dims = sips_dims(resized)
        if resized_dims != deliver:
            raise RuntimeError(
                f"hard export failure for {src.name}: sips produced {resized_dims}, expected {deliver}"
            )
        flatten_stats = flatten_background(
            resized, flattened, target=background_rgb, tolerance=background_tolerance
        )
        final_info = image_info(flattened)
        final_dims = (final_info["width"], final_info["height"])
        if final_dims != deliver:
            raise RuntimeError(
                f"hard export failure for {src.name}: post-process produced {final_dims}, expected {deliver}"
            )
        if final_info["mode"] != "RGB" or final_info["has_alpha"]:
            raise RuntimeError(f"hard export failure for {src.name}: final PNG is not opaque RGB")
        shutil.move(str(flattened), str(dst))
    actual = sips_dims(dst)
    if actual != deliver:
        raise RuntimeError(
            f"hard export failure for {src.name}: delivered file reads {actual}, expected {deliver}"
        )
    return actual, flatten_stats


class Worker:
    def __init__(self, job: dict, slide: dict, total: int, out_dir: Path, refs: list[Path],
                 timeout: int, dry_run: bool, run_id: str, generation_round: int = 1):
        self.job = job
        self.slide = slide
        self.n = slide["n"]
        self.total = total
        self.out_dir = out_dir
        self.refs = refs
        self.timeout = timeout
        self.dry_run = dry_run
        self.run_id = run_id
        self.generation_round = generation_round
        self.source_dir = out_dir / "source"
        self.log_dir = out_dir / "logs"
        self.event_path = self.log_dir / "batch-events.jsonl"
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
            "started_at": None,
            "completed_at": None,
            "generation_round": generation_round,
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
        self.result["started_at"] = iso_now()
        write_event(self.event_path, {
            "run_id": self.run_id,
            "event": "worker-started",
            "at": self.result["started_at"],
            "slide": self.n,
        })
        self.source_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        try:
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
        finally:
            self.result["seconds"] = round(time.monotonic() - started, 3)
            self.result["completed_at"] = iso_now()
            write_event(self.event_path, {
                "run_id": self.run_id,
                "event": "worker-completed",
                "at": self.result["completed_at"],
                "slide": self.n,
                "status": self.result["status"],
                "seconds": self.result["seconds"],
            })

    def _run_once(self, attempt: int) -> tuple[bool, str | None]:
        log_path = self.log_dir / f"slide{self.n:02d}.round{self.generation_round}.attempt{attempt}.log"
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


def quarantine_failed_attempt(out_dir: Path, job: dict, n: int, generation_round: int) -> None:
    """Retain mechanically failed whole rasters before the one automatic retry."""
    failed_dir = out_dir / "logs" / "failed-attempt-artifacts"
    for subdir, suffix, label in (("slides", "", "final"), ("source", "-source", "source")):
        path = out_dir / subdir / file_name(job, n, suffix)
        if path.is_file():
            failed_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(failed_dir / f"slide{n:02d}.round{generation_round}.{label}.png"))


def enforce_regeneration_lock(prior_job: dict | None, job: dict, selected: list[dict], only: list[int] | None) -> None:
    """Keep intent and subject stable unless the recorded failure is the object."""
    if not only or not prior_job:
        return
    prior_by_number = {slide.get("n"): slide for slide in prior_job.get("slides", []) if isinstance(slide, dict)}
    for slide in selected:
        prior = prior_by_number.get(slide["n"])
        if not prior:
            continue
        regeneration = slide.get("regeneration")
        if not isinstance(regeneration, dict) or not str(regeneration.get("reason") or "").strip():
            die(f"slide {slide['n']}: regeneration requires regeneration.reason")
        failure_class = str(regeneration.get("failure_class") or "").strip()
        if slide["intent"] != prior.get("intent"):
            die(f"slide {slide['n']}: regeneration may not change intent")
        if slide["subject"] != prior.get("subject") and failure_class != "object":
            die(
                f"slide {slide['n']}: named object changed from {prior.get('subject')!r} to {slide['subject']!r}; "
                "set failure_class=object only when the object itself failed"
            )


def write_brief_and_prompts(out_dir: Path, job: dict, refs: list[Path]) -> None:
    lines = [f"# Brief — {job['identity']} — {job['topic_slug']}", "",
             "Supplied copy, verbatim. Locked.", ""]
    for s in job["slides"]:
        lines += [
            f"## Slide {s['n']:02d} — {s['role']}", "",
            f"Intent: {s['intent']}", "", f"Named object: {s['subject']}", "",
            "```text", s["copy"].strip("\n"), "```", "",
        ]
    (out_dir / "brief.md").write_text("\n".join(lines), encoding="utf-8")

    p = [f"# Prompt set — {job['identity']} — {job['topic_slug']}", "",
         f"Generate size: `{job['size']['generate']}` → deliver `{job['size']['deliver']}`", "",
         "## References attached to every worker", ""]
    p += [f"- `{r.name}`" for r in refs] or ["- (none)"]
    p += ["", "## Shared contract", "", job["shared_contract"].strip(), ""]
    for s in job["slides"]:
        p += [f"## Slide {s['n']:02d} — {s['role']}", "", "### Intent", "", s["intent"].strip(), "",
              "### Named object", "", s["subject"].strip(), "", "### Visual", "", s["visual"].strip(), "",
              "### Copy (verbatim)", "", "```text", s["copy"].strip("\n"), "```", ""]
    (out_dir / "prompts.md").write_text("\n".join(p), encoding="utf-8")
    log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    total = len(job["slides"])
    for s in job["slides"]:
        exact = build_prompt(job, s, total, f"./{file_name(job, s['n'], '-source')}", refs)
        (log_dir / f"slide{s['n']:02d}.prompt.txt").write_text(exact, encoding="utf-8")


def build_dispatch(run_id: str, workers: list[Worker], concurrency_argument: int,
                   concurrency_limit: int, dry_run: bool) -> dict:
    starts = [dt.datetime.fromisoformat(w.result["started_at"]) for w in workers]
    completions = [dt.datetime.fromisoformat(w.result["completed_at"]) for w in workers]
    start_spread = (max(starts) - min(starts)).total_seconds() if starts else 0.0
    completion_spread = (max(completions) - min(completions)).total_seconds() if completions else 0.0
    all_started_before_first_completed = bool(starts and completions and max(starts) < min(completions))
    full_parallel_expected = concurrency_limit >= len(workers)
    simultaneous = bool(
        not dry_run
        and full_parallel_expected
        and start_spread <= DISPATCH_SPREAD_THRESHOLD_SEC
        and all_started_before_first_completed
    )
    if dry_run:
        guard_pass = True
        reason = "dry-run: no image workers were dispatched"
    elif not full_parallel_expected:
        guard_pass = True
        reason = "user-requested concurrency limit is below worker count; simultaneous dispatch not expected"
    elif simultaneous:
        guard_pass = True
        reason = "all workers started inside the threshold before any worker completed"
    else:
        guard_pass = False
        reason = "full-parallel run exceeded the start-spread threshold or completed before all workers started"
    return {
        "run_id": run_id,
        "worker_count": len(workers),
        "concurrency_argument": concurrency_argument if concurrency_argument > 0 else None,
        "concurrency_explicit": concurrency_argument > 0,
        "concurrency_limit": concurrency_limit,
        "start_spread_threshold_seconds": DISPATCH_SPREAD_THRESHOLD_SEC,
        "start_spread_seconds": round(start_spread, 6),
        "completion_spread_seconds": round(completion_spread, 6),
        "all_started_before_first_completed": all_started_before_first_completed,
        "simultaneous_dispatch": simultaneous,
        "guard_pass": guard_pass,
        "guard_reason": reason,
        "workers": [
            {
                "slide": w.n,
                "started_at": w.result["started_at"],
                "completed_at": w.result["completed_at"],
                "seconds": w.result["seconds"],
                "status": w.result["status"],
            }
            for w in sorted(workers, key=lambda item: item.n)
        ],
    }


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


def prepend_dispatch_summary(out_dir: Path, dispatches: list[dict]) -> None:
    path = out_dir / "REVIEW.md"
    if not path.is_file() or not dispatches:
        return
    summaries = []
    for index, dispatch in enumerate(dispatches, start=1):
        summaries.append(
            f"round {index}: workers={dispatch['worker_count']}, concurrency={dispatch['concurrency_limit']}, "
            f"start spread={dispatch['start_spread_seconds']:.6f}s, "
            f"simultaneous={'YES' if dispatch['simultaneous_dispatch'] else 'NO'}"
        )
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    insert_at = 2 if lines and lines[0].startswith("# ") else 0
    lines[insert_at:insert_at] = ["Dispatch: " + "; ".join(summaries) + ".", ""]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def run_validation(job_path: Path, out_dir: Path, selected: list[int] | None = None) -> tuple[int, dict]:
    json_path = out_dir / "mechanical-validation.json"
    command = [
        sys.executable, str(SKILL_ROOT / "scripts" / "validate.py"), str(job_path),
        "--output-dir", str(out_dir), "--json-out", str(json_path),
    ]
    if selected:
        command += ["--only", ",".join(str(number) for number in selected)]
    process = subprocess.run(command)
    try:
        report = json.loads(json_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        die(f"validation did not write readable JSON: {exc}")
    return process.returncode, report


def mechanical_failure_reason(check: dict | None) -> str:
    if not check:
        return "no validation result"
    reasons = []
    for key, label in (
        ("exists", "missing file"),
        ("readable", "unreadable image"),
        ("dimensions_pass", "wrong dimensions"),
        ("no_alpha_pass", "alpha/non-RGB output"),
        ("background_pass", "background control pixels"),
        ("shield_pass", "shield absent, duplicated, or outside fixed region"),
        ("guillemets_pass", "Arabic guillemets"),
    ):
        if not check.get(key):
            reasons.append(label)
    return "; ".join(reasons) or "mechanical check failed"


def print_table(manifest: dict) -> None:
    print()
    print(f"Output: {manifest['output_dir']}")
    print()
    print(f"{'slide':<7}{'status':<24}{'source':<12}{'final':<12}{'sec':<8}error")
    for r in manifest["slides"]:
        print(f"{r['n']:02d}     {r['status']:<24}{(r.get('source_dims') or '-'):<12}"
              f"{(r.get('final_dims') or '-'):<12}{r.get('seconds', 0):<8}{r.get('error') or ''}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job", type=Path)
    ap.add_argument("--only", help="comma-separated slide numbers to (re)generate, e.g. 2,4")
    ap.add_argument("--concurrency", type=int, default=0, help="max parallel workers (0 = all)")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SEC, help="seconds per worker attempt")
    ap.add_argument("--mechanical-retries", type=int, default=1, help="whole-slide retry batches after validation failure")
    ap.add_argument("--dry-run", action="store_true", help="write prompts/logs, run nothing")
    ap.add_argument("--no-export", action="store_true", help="skip sips export to delivery size")
    ap.add_argument("--no-validate", action="store_true", help="skip mechanical validation and automatic retry")
    ap.add_argument("--output-dir", type=Path, help="override output folder (default: ~/Downloads/DC-...)")
    args = ap.parse_args()

    if args.no_export and not args.no_validate:
        die("--no-export requires --no-validate")
    if args.mechanical_retries < 0:
        die("--mechanical-retries must be >= 0")

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

    prior_job_path = out_dir / "job.json"
    try:
        prior_job = json.loads(prior_job_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        prior_job = None

    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {
        "identity": job["identity"], "topic_slug": job["topic_slug"], "output_dir": str(out_dir),
        "slides": [], "history": [],
    }
    manifest["output_dir"] = str(out_dir)

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
    enforce_regeneration_lock(prior_job, job, selected, only)
    prior_job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    for s in selected:
        archive_previous(out_dir, job, s["n"], manifest)

    write_brief_and_prompts(out_dir, job, refs)

    manifest["started_at"] = iso_now()
    deliver = parse_size(job["size"]["deliver"])
    background_rgb = parse_hex(job["background"]["hex"])
    results_by_number = {result["n"]: result for result in manifest["slides"]}
    dispatches: list[dict] = []
    validation_report: dict | None = None
    validation_code = 0
    pending = selected

    for generation_round in range(1, args.mechanical_retries + 2):
        if generation_round > 1:
            for slide in pending:
                quarantine_failed_attempt(out_dir, job, slide["n"], generation_round - 1)
        run_id = (
            f"{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')}-"
            f"r{generation_round}-{uuid.uuid4().hex[:8]}"
        )
        workers = [
            Worker(job, slide, total, out_dir, refs, args.timeout, args.dry_run, run_id, generation_round)
            for slide in pending
        ]
        limit = min(args.concurrency, len(workers)) if args.concurrency > 0 else len(workers)
        gate = threading.Semaphore(max(1, limit))
        log(
            f"dispatching {len(workers)} worker(s), concurrency {limit}, "
            f"identity {job['identity']}, round {generation_round}"
        )

        def runner(worker: Worker) -> None:
            with gate:
                worker.run()

        threads = [threading.Thread(target=runner, args=(worker,), daemon=True) for worker in workers]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        for worker in workers:
            result = worker.result
            if result["status"] == "generated" and not args.no_export:
                final = out_dir / "slides" / file_name(job, worker.n)
                try:
                    dimensions, flatten_stats = export_to_delivery(
                        worker.source_path,
                        final,
                        deliver,
                        background_rgb,
                        job["background"]["tolerance"],
                    )
                except (RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
                    result["status"] = "export-failed"
                    result["error"] = str(exc)
                else:
                    result["final"] = str(final)
                    result["final_dims"] = f"{dimensions[0]}x{dimensions[1]}"
                    result["flatten"] = flatten_stats
                    result["status"] = "delivered"
            elif result["status"] == "generated":
                result["final"] = result["source"]
                result["final_dims"] = result["source_dims"]
                result["status"] = "delivered-unexported"
            results_by_number[worker.n] = result

        dispatches.append(build_dispatch(run_id, workers, args.concurrency, limit, args.dry_run))
        if args.dry_run or args.no_validate:
            pending = []
            break

        validation_code, validation_report = run_validation(
            prior_job_path, out_dir, [slide["n"] for slide in pending]
        )
        report_by_number = {item["n"]: item for item in validation_report.get("slides", [])}
        failed_numbers: list[int] = []
        for slide in pending:
            result = results_by_number[slide["n"]]
            check = report_by_number.get(slide["n"])
            result["mechanical"] = check
            if check and check.get("pass"):
                result["status"] = "validated"
                result["error"] = None
            else:
                result["status"] = "mechanical-failed"
                result["error"] = mechanical_failure_reason(check)
                failed_numbers.append(slide["n"])
                manifest.setdefault("mechanical_failures", []).append({
                    "slide": slide["n"],
                    "round": generation_round,
                    "reason": result["error"],
                })
                log(f"slide {slide['n']:02d}: mechanical failure — {result['error']}")
        if not failed_numbers or generation_round > args.mechanical_retries:
            pending = []
            break
        pending = [slide for slide in selected if slide["n"] in failed_numbers]
        log(
            f"automatic whole-slide retry round {generation_round + 1}: "
            f"slides {','.join(str(slide['n']) for slide in pending)}"
        )

    by_n = results_by_number
    manifest["slides"] = [by_n[k] for k in sorted(by_n)]
    manifest["finished_at"] = iso_now()
    manifest["generate_size"] = job["size"]["generate"]
    manifest["deliver_size"] = job["size"]["deliver"]
    previous_dispatch = manifest.get("dispatch")
    if previous_dispatch:
        manifest.setdefault("dispatch_history", []).append(previous_dispatch)
    manifest["dispatch"] = dispatches[0]
    manifest["retry_dispatches"] = dispatches[1:]
    manifest["validation"] = validation_report
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.dry_run or args.no_validate:
        write_review(out_dir, job, manifest)
    prepend_dispatch_summary(out_dir, dispatches)
    if not args.dry_run:
        append_run_log(job, manifest)

    verify_cmd = [sys.executable, str(SKILL_ROOT / "scripts" / "verify_run.py"), str(out_dir)]
    if args.dry_run:
        verify_cmd.append("--dry-run")
    verification = subprocess.run(verify_cmd, capture_output=True, text=True)
    (out_dir / "logs" / "run-verification.log").write_text(
        verification.stdout + verification.stderr, encoding="utf-8"
    )
    if verification.stdout.strip():
        print(verification.stdout.strip())
    if verification.returncode:
        print(verification.stderr.strip(), file=sys.stderr)

    print_table(manifest)
    failed = [
        result for result in manifest["slides"]
        if result["status"] in {"failed", "export-failed", "mechanical-failed"}
    ]
    dispatch_failed = any(not dispatch["guard_pass"] for dispatch in dispatches)
    return 1 if failed or dispatch_failed or verification.returncode or validation_code else 0


if __name__ == "__main__":
    sys.exit(main())
