from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
GENERATE = ROOT / "scripts" / "generate.py"
VALIDATE = ROOT / "scripts" / "validate.py"
RENDER_SPEC = ROOT / "references" / "render-spec.md"


def seven_slide_job(path: Path) -> dict:
    render_spec = RENDER_SPEC.read_text(encoding="utf-8")
    job = {
        "schema": 2,
        "identity": "OLD",
        "topic_slug": "approval-proof",
        "refs": [],
        "size": {"generate": "1024x1536", "deliver": "1080x1350"},
        "background": {"hex": "#12181D", "tolerance": 12},
        "shared_contract": render_spec,
        "slides": [
            {
                "n": number,
                "number": f"{number:02d} / 07",
                "role": "explainer",
                "intent": f"communicate distinct meaning {number}",
                "subject": f"line diagram {number}",
                "visual": f"A white line diagram with one small gold dot number {number}.",
                "copy": f"نص السلايد {number}",
            }
            for number in range(1, 8)
        ],
    }
    path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    return job


class ApprovalGateTests(unittest.TestCase):
    def run_preview(self, dry_run: bool) -> None:
        with tempfile.TemporaryDirectory(prefix="dc-approval-test-") as temporary:
            root = Path(temporary)
            job_path = root / "job.json"
            output = root / "output"
            job = seven_slide_job(job_path)
            command = [sys.executable, str(GENERATE), str(job_path), "--output-dir", str(output)]
            if dry_run:
                command.append("--dry-run")
            process = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn("0 workers dispatched", process.stdout)
            self.assertIn("Waiting for explicit go-ahead.", process.stdout)
            self.assertFalse((output / "manifest.json").exists())
            self.assertFalse((output / "source").exists())

            preview = json.loads((output / "preview-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(preview["approval"], "pending")
            self.assertEqual(preview["workers_dispatched"], 0)
            self.assertEqual(len(preview["slides"]), 7)

            marker = "BEGIN BYTE-IDENTICAL SHARED CONTRACT\n"
            end_marker = "END BYTE-IDENTICAL SHARED CONTRACT"
            contracts = []
            for slide in job["slides"]:
                prompt = (output / "logs" / f"slide{slide['n']:02d}.prompt.txt").read_text(encoding="utf-8")
                start = prompt.index(marker) + len(marker)
                end = prompt.index(end_marker)
                contracts.append(prompt[start:end])
                self.assertIn(slide["number"], prompt)
                self.assertIn(slide["intent"], prompt)
                self.assertIn(slide["subject"], prompt)
            self.assertTrue(all(contract == contracts[0] for contract in contracts))
            self.assertEqual(contracts[0], RENDER_SPEC.read_text(encoding="utf-8"))

    def test_seven_slide_dry_run_has_byte_exact_contract_and_no_dispatch(self) -> None:
        self.run_preview(dry_run=True)

    def test_missing_yes_halts_at_same_approval_gate(self) -> None:
        self.run_preview(dry_run=False)


class ValidationFailureTests(unittest.TestCase):
    def test_wrong_size_and_missing_shield_both_fail(self) -> None:
        with tempfile.TemporaryDirectory(prefix="dc-validation-test-") as temporary:
            root = Path(temporary)
            output = root / "output"
            slides = output / "slides"
            slides.mkdir(parents=True)
            Image.new("RGB", (100, 100), (18, 24, 29)).save(
                slides / "DC-OLD-validation-proof-slide01.png"
            )
            Image.new("RGB", (1080, 1350), (18, 24, 29)).save(
                slides / "DC-OLD-validation-proof-slide02.png"
            )
            job = {
                "identity": "OLD",
                "topic_slug": "validation-proof",
                "refs": ["assets/OLD-shield-logo.png"],
                "size": {"deliver": "1080x1350"},
                "background": {"hex": "#12181D"},
                "slides": [
                    {"n": 1, "copy": "صورة بمقاس خاطئ"},
                    {"n": 2, "copy": "صورة بلا شيلد"},
                ],
            }
            job_path = root / "job.json"
            job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
            process = subprocess.run(
                [sys.executable, str(VALIDATE), str(job_path), "--output-dir", str(output)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(process.returncode, 1)
            report = json.loads((output / "mechanical-validation.json").read_text(encoding="utf-8"))
            wrong_size, shieldless = report["slides"]
            self.assertFalse(wrong_size["dimensions_pass"])
            self.assertTrue(shieldless["dimensions_pass"])
            self.assertFalse(shieldless["shield_pass"])
            self.assertFalse(report["pass"])
            review = (output / "REVIEW.md").read_text(encoding="utf-8")
            self.assertIn("| 01 | FAIL | 100x100 |", review)


class SingleSourceRuleTests(unittest.TestCase):
    def test_delivery_gold_and_old_shield_have_no_competing_active_values(self) -> None:
        generate_source = GENERATE.read_text(encoding="utf-8")
        validate_source = VALIDATE.read_text(encoding="utf-8")
        identity = (ROOT / "references" / "identity-guide.md").read_text(encoding="utf-8")
        prompt_contract = (ROOT / "references" / "prompt-contract.md").read_text(encoding="utf-8")
        lessons = (ROOT / "learnings" / "shared" / "lessons.md").read_text(encoding="utf-8")
        compositions = (ROOT / "references" / "compositions.md").read_text(encoding="utf-8")
        render_spec = RENDER_SPEC.read_text(encoding="utf-8")

        self.assertNotIn("DEFAULT_DELIVER_SIZE", generate_source)
        self.assertNotIn("DEFAULT_DELIVER_SIZE", validate_source)
        self.assertNotIn("shield, once, top-right", identity)
        self.assertNotIn("logo top-right", prompt_contract)
        self.assertNotIn("identity mark exactly once, top-right", lessons)
        self.assertIn("fixed bottom-left region", render_spec)
        self.assertIn("normative gold\nrule lives only in `references/render-spec.md`", compositions)


if __name__ == "__main__":
    unittest.main()
