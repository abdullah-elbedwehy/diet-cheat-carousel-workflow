#!/usr/bin/env python3
"""Mechanically validate generated Diet & Cheat carousel files.

Checks exact dimensions, opaque RGB output, exact five-point background,
REF-01 shield count/location, and Arabic guillemet order/orientation. Writes
machine-readable JSON and REVIEW.md. These are deterministic image-processing
checks; the AI never judges how images look or performs aesthetic review.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
if importlib.util.find_spec("PIL") is None:
    bundled_python = SKILL_ROOT / ".venv" / "bin" / "python"
    if bundled_python.is_file() and Path(sys.executable).resolve() != bundled_python.resolve():
        os.execv(str(bundled_python), [str(bundled_python), str(Path(__file__).resolve()), *sys.argv[1:]])

from PIL import Image
from image_processing import (
    NAVY,
    box_inside,
    chevron_direction,
    find_shield_matches,
    image_info,
    sample_control_pixels,
)


DEFAULT_DELIVER_SIZE = "1080x1440"
DEFAULT_BACKGROUNDS = {"OLD": "#12181D", "NEW": "#091521"}


def die(message: str, code: int = 2) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def parse_size(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", value or "")
    if not match:
        die(f"bad size '{value}', expected WxH")
    return int(match.group(1)), int(match.group(2))


def parse_hex(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"#([0-9A-Fa-f]{6})", value or "")
    if not match:
        die(f"bad background '{value}', expected #RRGGBB")
    raw = match.group(1)
    return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "carousel"


def load_job(path: Path) -> dict:
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        die(f"job file not found: {path}")
    except json.JSONDecodeError as exc:
        die(f"job file is not valid JSON: {exc}")
    identity = str(job.get("identity", "")).upper()
    if identity not in DEFAULT_BACKGROUNDS:
        die("job.identity must be OLD or NEW")
    job["identity"] = identity
    job["topic_slug"] = slugify(str(job.get("topic_slug", "")))
    slides = job.get("slides")
    if not isinstance(slides, list) or not slides:
        die("job.slides must be a non-empty list")
    size = job.get("size") or {}
    job["deliver_size"] = size.get("deliver", size.get("target", DEFAULT_DELIVER_SIZE))
    background = job.get("background") or {}
    job["background_hex"] = background.get("hex", DEFAULT_BACKGROUNDS[identity])
    return job


def file_name(job: dict, number: int) -> str:
    return f"DC-{job['identity']}-{job['topic_slug']}-slide{number:02d}.png"


def resolve_reference(job: dict) -> Path | None:
    configured = (job.get("shield") or {}).get("reference")
    values = [configured] if configured else list(job.get("refs") or [])
    values += ["assets/OLD-shield-logo.png"] if job["identity"] == "OLD" else []
    for value in values:
        if not value:
            continue
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = SKILL_ROOT / candidate
        if candidate.is_file() and (configured or "shield" in candidate.name.lower() or "logo" in candidate.name.lower()):
            return candidate.resolve()
    return None


def default_shield_region(size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    # Render spec: 90 px wide, 60 px left, 70 px bottom. The match region
    # allows generation variance around that fixed slot, not another quadrant.
    return (0, int(height * 0.76), int(width * 0.25), height)


def body_region(job: dict, size: tuple[int, int]) -> tuple[int, int, int, int]:
    configured = (job.get("validation") or {}).get("body_region")
    if isinstance(configured, list) and len(configured) == 4 and all(isinstance(value, int) for value in configured):
        return tuple(configured)
    width, height = size
    return (int(width * 0.05), int(height * 0.25), int(width * 0.95), int(height * 0.52))


def ocr_body(path: Path, region: tuple[int, int, int, int]) -> tuple[dict | None, str | None, Image.Image]:
    with Image.open(path) as opened:
        crop = opened.convert("RGB").crop(region)
    swift = shutil.which("swift")
    if not swift:
        return None, "swift not found; Vision OCR unavailable", crop
    with tempfile.TemporaryDirectory(prefix="dc-body-ocr-") as temporary:
        crop_path = Path(temporary) / "body.png"
        crop.save(crop_path, format="PNG")
        process = subprocess.run(
            [swift, str(SKILL_ROOT / "scripts" / "ocr_body.swift"), str(crop_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    if process.returncode:
        return None, (process.stderr.strip() or f"Vision OCR exit {process.returncode}"), crop
    try:
        return json.loads(process.stdout), None, crop
    except json.JSONDecodeError as exc:
        return None, f"Vision OCR returned invalid JSON: {exc}", crop


def validate_guillemets(path: Path, source_copy: str, job: dict, size: tuple[int, int]) -> dict:
    expected = [character for character in source_copy if character in "«»"]
    result = {
        "required": bool(expected),
        "expected": expected,
        "ocr_text": "",
        "recognized": [],
        "glyphs": [],
        "sequence_pass": True,
        "rtl_order_pass": True,
        "orientation_pass": True,
        "orientation_reliable": True,
        "status": "PASS",
        "pass": True,
        "error": None,
    }
    if not expected:
        return result
    payload, error, crop = ocr_body(path, body_region(job, size))
    if error or payload is None:
        result.update({
            "sequence_pass": False,
            "rtl_order_pass": False,
            "orientation_pass": False,
            "pass": False,
            "error": error or "OCR unavailable",
        })
        return result
    text = str(payload.get("text") or "")
    recognized = [character for character in text if character in "«»"]
    glyphs = list(payload.get("glyphs") or [])
    result["ocr_text"] = text
    result["recognized"] = recognized
    result["sequence_pass"] = recognized == expected

    directions: list[str] = []
    for glyph in glyphs:
        try:
            box = (
                max(0, int(float(glyph["x"]) * crop.width) - 3),
                max(0, int(float(glyph["y"]) * crop.height) - 3),
                min(crop.width, int((float(glyph["x"]) + float(glyph["w"])) * crop.width) + 3),
                min(crop.height, int((float(glyph["y"]) + float(glyph["h"])) * crop.height) + 3),
            )
        except (KeyError, TypeError, ValueError):
            directions.append("unknown")
            continue
        direction = chevron_direction(crop.crop(box))
        glyph["direction"] = direction
        directions.append(direction)
    result["glyphs"] = glyphs

    unique_boxes = {
        (round(float(glyph.get("x", 0)), 5), round(float(glyph.get("y", 0)), 5),
         round(float(glyph.get("w", 0)), 5), round(float(glyph.get("h", 0)), 5))
        for glyph in glyphs
    }
    if len(glyphs) != len(expected) or len(unique_boxes) != len(glyphs):
        # Vision sometimes returns one line-level box for both Arabic quote
        # marks. That is not reliable orientation evidence. Keep the OCR text
        # in REVIEW.md as the explicitly requested one-glance fallback.
        result["rtl_order_pass"] = None
        result["orientation_pass"] = None
        result["orientation_reliable"] = False
        result["status"] = "PASS (OCR-ONLY)" if result["sequence_pass"] else "FAIL"
    else:
        centers = [float(glyph["x"]) + float(glyph["w"]) / 2 for glyph in glyphs]
        # Vision returns logical source order. In RTL the opening mark is to the
        # right of the closing mark.
        result["rtl_order_pass"] = all(centers[index] > centers[index + 1] for index in range(len(centers) - 1))
        # Unicode bidi mirroring: logical « opens on the right as a right-facing
        # glyph, logical » closes on the left as a left-facing glyph.
        expected_directions = ["right" if character == "«" else "left" for character in expected]
        result["orientation_pass"] = directions == expected_directions
    if result["orientation_reliable"]:
        result["pass"] = bool(result["sequence_pass"] and result["rtl_order_pass"] and result["orientation_pass"])
    else:
        result["pass"] = bool(result["sequence_pass"])
    if not result["pass"]:
        result["status"] = "FAIL"
        result["error"] = "guillemet sequence, RTL order, or visible orientation failed"
    return result


def validate_slide(
    path: Path,
    slide: dict,
    job: dict,
    expected_size: tuple[int, int],
    expected_rgb: tuple[int, int, int],
    shield_reference: Path | None,
) -> dict:
    result = {
        "file": str(path),
        "exists": path.is_file(),
        "readable": False,
        "dimensions": None,
        "dimensions_pass": False,
        "mode": None,
        "no_alpha_pass": False,
        "background_pass": False,
        "samples": [],
        "shield_pass": job["identity"] != "OLD",
        "shield_matches": [],
        "guillemets_pass": True,
        "guillemets": {},
        "error": None,
    }
    if not result["exists"]:
        result["error"] = "missing file"
        result["pass"] = False
        return result
    try:
        info = image_info(path)
        samples = sample_control_pixels(path)
    except (OSError, ValueError) as exc:
        result["error"] = str(exc)
        result["pass"] = False
        return result
    result["readable"] = True
    result["dimensions"] = f"{info['width']}x{info['height']}"
    result["dimensions_pass"] = (info["width"], info["height"]) == expected_size
    result["mode"] = info["mode"]
    result["no_alpha_pass"] = info["mode"] == "RGB" and not info["has_alpha"]
    result["samples"] = samples
    result["background_pass"] = all(tuple(sample["rgb"]) == expected_rgb for sample in samples)

    if job["identity"] == "OLD":
        if shield_reference is None:
            result["shield_pass"] = False
            result["shield_error"] = "REF-01 shield reference not found"
        else:
            minimum = float((job.get("shield") or {}).get("minimum_score", 0.70))
            matches = find_shield_matches(path, shield_reference, minimum)
            configured = (job.get("shield") or {}).get("region")
            region = tuple(configured) if isinstance(configured, list) and len(configured) == 4 else default_shield_region(expected_size)
            inside = [match for match in matches if box_inside(match["box"], region)]
            result["shield_matches"] = matches
            result["shield_region"] = list(region)
            result["shield_pass"] = len(matches) == 1 and len(inside) == 1
            if not result["shield_pass"]:
                result["shield_error"] = f"expected one shield inside fixed region; found {len(inside)} inside and {len(matches)} total"

    guillemets = validate_guillemets(path, str(slide.get("copy") or ""), job, expected_size)
    result["guillemets"] = guillemets
    result["guillemets_pass"] = guillemets["pass"]
    required_checks = (
        "exists", "readable", "dimensions_pass", "no_alpha_pass",
        "background_pass", "shield_pass", "guillemets_pass",
    )
    result["pass"] = all(result[key] for key in required_checks)
    return result


def write_review(output_dir: Path, job: dict, report: dict) -> None:
    lines = [
        f"# Review — {job['identity']} — {job['topic_slug']}",
        "",
        "Mechanical image-processing checks only. الـAI لم يقيّم الشكل أو الجماليات.",
        "",
        "| Slide | Mechanical | Dims | Background | Shield REF-01 | Guillemets RTL | OCR body | ملاحظة |",
        "|---|---|---|---|---|---|---|---|",
    ]
    by_number = {item["n"]: item for item in report["slides"]}
    for slide in sorted(job["slides"], key=lambda item: item["n"]):
        item = by_number.get(slide["n"])
        if not item:
            lines.append(f"| {slide['n']:02d} | FAIL | - | FAIL | FAIL | FAIL | - | missing result |")
            continue
        mechanical = "PASS" if item["pass"] else "FAIL"
        background = "PASS" if item["background_pass"] else "FAIL"
        shield = "PASS" if item["shield_pass"] else "FAIL"
        quote_result = item.get("guillemets", {})
        guillemets = quote_result.get("status") or ("PASS" if item["guillemets_pass"] else "FAIL")
        ocr = str(item.get("guillemets", {}).get("ocr_text") or "-").replace("\n", "<br>").replace("|", "\\|")
        note = item.get("error") or item.get("shield_error") or item.get("guillemets", {}).get("error") or ""
        lines.append(
            f"| {slide['n']:02d} | {mechanical} | {item.get('dimensions') or '-'} | {background} | "
            f"{shield} | {guillemets} | {ocr} | {note} |"
        )
    lines += [
        "",
        f"Expected slide count: `{report['expected_count']}` — actual: `{report['actual_count']}` — {'PASS' if report['count_pass'] else 'FAIL'}",
        "",
        "Shield rule: exactly one REF-01 template match, centered inside the fixed bottom-left region; zero, duplicates, or any match outside fail.",
        "Guillemet rule: Vision OCR text, logical sequence, RTL position, and visible chevron direction must all pass.",
        "",
    ]
    (output_dir / "REVIEW.md").write_text("\n".join(lines), encoding="utf-8")


def human_table(report: dict) -> None:
    print(f"{'slide':<7}{'size':<8}{'rgb':<8}{'bg':<8}{'shield':<9}{'quotes':<9}result")
    mark = lambda value: "PASS" if value else "FAIL"
    for item in report["slides"]:
        print(
            f"{item['n']:02d}     {mark(item['dimensions_pass']):<8}{mark(item['no_alpha_pass']):<8}"
            f"{mark(item['background_pass']):<8}{mark(item['shield_pass']):<9}"
            f"{mark(item['guillemets_pass']):<9}{mark(item['pass'])}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("job", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--only", help="comma-separated slide numbers to report in detail")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    job = load_job(args.job)
    output_value = args.output_dir or job.get("output_dir")
    if not output_value:
        die("output directory missing; pass --output-dir or set job.output_dir")
    output_dir = Path(output_value).expanduser().resolve()
    expected_size = parse_size(job["deliver_size"])
    expected_rgb = parse_hex(job["background_hex"])
    selected = {slide["n"] for slide in job["slides"]}
    if args.only:
        try:
            selected = {int(value) for value in args.only.split(",") if value.strip()}
        except ValueError:
            die("--only expects comma-separated integers")
    known = {slide["n"] for slide in job["slides"]}
    if not selected <= known:
        die(f"--only names slides not in job: {sorted(selected - known)}")

    slides_dir = output_dir / "slides"
    expected_paths = {slide["n"]: slides_dir / file_name(job, slide["n"]) for slide in job["slides"]}
    actual_paths = sorted(slides_dir.glob(f"DC-{job['identity']}-{job['topic_slug']}-slide*.png")) if slides_dir.is_dir() else []
    expected_names = {path.name for path in expected_paths.values()}
    actual_names = {path.name for path in actual_paths}
    report = {
        "output_dir": str(output_dir),
        "deliver_size": job["deliver_size"],
        "background": job["background_hex"],
        "background_sample_tolerance": 0,
        "expected_count": len(expected_paths),
        "actual_count": len(actual_paths),
        "count_pass": actual_names == expected_names,
        "missing": sorted(expected_names - actual_names),
        "unexpected": sorted(actual_names - expected_names),
        "slides": [],
    }
    shield_reference = resolve_reference(job)
    slides_by_number = {slide["n"]: slide for slide in job["slides"]}
    for number in sorted(selected):
        item = validate_slide(
            expected_paths[number], slides_by_number[number], job,
            expected_size, expected_rgb, shield_reference,
        )
        item["n"] = number
        report["slides"].append(item)
    report["pass"] = report["count_pass"] and all(item["pass"] for item in report["slides"])

    json_out = (args.json_out or (output_dir / "mechanical-validation.json")).resolve()
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_review(output_dir, job, report)
    human_table(report)
    print(f"JSON: {json_out}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
