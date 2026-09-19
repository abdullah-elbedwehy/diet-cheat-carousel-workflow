from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_run", ROOT / "scripts" / "verify_run.py")
assert SPEC and SPEC.loader
VERIFY_RUN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY_RUN)


class DispatchProofTests(unittest.TestCase):
    def make_run(self, spread: float = 0.25) -> Path:
        root = Path(tempfile.mkdtemp(prefix="dc-dispatch-test-"))
        (root / "logs").mkdir()
        (root / "source").mkdir()
        for name in ("job.json", "prompts.md", "REVIEW.md"):
            (root / name).write_text("{}", encoding="utf-8")
        source = root / "source" / "slide01.png"
        source.write_bytes(b"source")
        (root / "logs" / "slide01.prompt.txt").write_text("prompt", encoding="utf-8")
        manifest = {
            "slides": [{"n": 1, "status": "delivered-unexported", "source": str(source)}],
            "dispatch": {
                "worker_count": 1,
                "concurrency_limit": 1,
                "start_spread_threshold_seconds": 2.0,
                "start_spread_seconds": spread,
                "all_started_before_first_completed": True,
                "simultaneous_dispatch": spread <= 2.0,
                "guard_pass": spread <= 2.0,
                "guard_reason": "test fixture",
                "workers": [{
                    "slide": 1,
                    "started_at": "2026-09-19T12:00:00.000000+00:00",
                    "completed_at": "2026-09-19T12:01:00.000000+00:00",
                    "seconds": 60.0,
                    "status": "delivered-unexported",
                }],
            },
        }
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return root

    def test_valid_parallel_run_passes(self) -> None:
        report = VERIFY_RUN.verify_output(self.make_run())
        self.assertTrue(report["pass"], report["errors"])

    def test_start_spread_above_threshold_fails(self) -> None:
        report = VERIFY_RUN.verify_output(self.make_run(spread=2.001))
        self.assertFalse(report["pass"])
        self.assertTrue(any("exceeds" in error for error in report["errors"]))

    def test_missing_canonical_artifacts_fails(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="dc-bypass-test-"))
        (root / "slide01.png").write_bytes(b"not a canonical run")
        report = VERIFY_RUN.verify_output(root)
        self.assertFalse(report["pass"])
        self.assertTrue(any("missing required artifact" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
