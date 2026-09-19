#!/usr/bin/env python3
"""Verify that a carousel run used the canonical dispatcher and proved its timing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REQUIRED_FILES = ("job.json", "prompts.md", "manifest.json", "REVIEW.md")
REQUIRED_DIRS = ("logs", "source")
SUCCESS_STATUSES = {"generated", "delivered", "delivered-unexported", "validated"}


def verify_output(output_dir: Path, dry_run: bool = False) -> dict:
    output_dir = output_dir.expanduser().resolve()
    errors: list[str] = []
    for name in REQUIRED_FILES:
        if not (output_dir / name).is_file():
            errors.append(f"missing required artifact: {name}")
    for name in REQUIRED_DIRS:
        if not (output_dir / name).is_dir():
            errors.append(f"missing required directory: {name}/")

    manifest: dict = {}
    manifest_path = output_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"manifest.json is invalid JSON: {exc}")

    dispatch = manifest.get("dispatch") if isinstance(manifest, dict) else None
    if not isinstance(dispatch, dict):
        errors.append("manifest.json has no dispatch object")
        dispatch = {}

    workers = dispatch.get("workers")
    if not isinstance(workers, list) or not workers:
        errors.append("dispatch.workers is missing or empty")
        workers = []
    worker_count = dispatch.get("worker_count")
    if worker_count != len(workers):
        errors.append(f"dispatch.worker_count={worker_count!r} does not match {len(workers)} worker records")

    for worker in workers:
        number = worker.get("slide")
        if not isinstance(number, int):
            errors.append("dispatch worker has no integer slide number")
            continue
        if not worker.get("started_at") or not worker.get("completed_at"):
            errors.append(f"slide {number:02d}: missing start or completion timestamp")
        if not (output_dir / "logs" / f"slide{number:02d}.prompt.txt").is_file():
            errors.append(f"slide {number:02d}: missing exact prompt file")

    if not dry_run:
        if dispatch.get("concurrency_limit") is None:
            errors.append("dispatch.concurrency_limit is missing")
        full_parallel = (
            isinstance(dispatch.get("concurrency_limit"), int)
            and isinstance(worker_count, int)
            and dispatch["concurrency_limit"] >= worker_count
        )
        if full_parallel:
            spread = dispatch.get("start_spread_seconds")
            threshold = dispatch.get("start_spread_threshold_seconds")
            if not isinstance(spread, (int, float)) or not isinstance(threshold, (int, float)):
                errors.append("dispatch start spread or threshold is missing")
            elif spread > threshold:
                errors.append(f"dispatch start spread {spread:.6f}s exceeds {threshold:.6f}s threshold")
            if not dispatch.get("all_started_before_first_completed"):
                errors.append("a worker completed before all workers started")
            if not dispatch.get("simultaneous_dispatch"):
                errors.append("dispatch does not qualify as simultaneous")
        if not dispatch.get("guard_pass"):
            errors.append(f"dispatch guard failed: {dispatch.get('guard_reason') or 'no reason recorded'}")

        for index, retry in enumerate(manifest.get("retry_dispatches", []), start=1):
            if not isinstance(retry, dict) or not retry.get("guard_pass"):
                errors.append(f"retry dispatch {index} failed its timing guard")

        results = {item.get("n"): item for item in manifest.get("slides", []) if isinstance(item, dict)}
        for worker in workers:
            number = worker.get("slide")
            if not isinstance(number, int):
                continue
            result = results.get(number)
            if not result:
                errors.append(f"slide {number:02d}: missing manifest result")
                continue
            if result.get("status") in SUCCESS_STATUSES:
                source = result.get("source")
                if not source or not Path(source).is_file():
                    errors.append(f"slide {number:02d}: successful result has no source raster")
            if result.get("status") == "validated":
                final = result.get("final")
                if not final or not Path(final).is_file():
                    errors.append(f"slide {number:02d}: validated result has no delivered raster")

        validation = manifest.get("validation")
        if validation is not None and not validation.get("pass"):
            errors.append("mechanical validation report failed")

    report = {
        "output_dir": str(output_dir),
        "mode": "dry-run" if dry_run else "generation",
        "pass": not errors,
        "errors": errors,
        "dispatch": dispatch,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run-verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = verify_output(args.output_dir, args.dry_run)
    if report["pass"]:
        dispatch = report["dispatch"]
        print(
            "RUN PROOF PASS: "
            f"workers={dispatch.get('worker_count')} "
            f"concurrency={dispatch.get('concurrency_limit')} "
            f"start_spread={dispatch.get('start_spread_seconds')}s "
            f"simultaneous={dispatch.get('simultaneous_dispatch')}"
        )
        return 0
    print("RUN PROOF FAIL:", file=sys.stderr)
    for error in report["errors"]:
        print(f"- {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
