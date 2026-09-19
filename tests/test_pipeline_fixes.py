from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATE = load_module("generate", ROOT / "scripts" / "generate.py")
PROCESSING = load_module("image_processing", ROOT / "scripts" / "image_processing.py")


class ExactExportTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("sips"), "macOS sips required")
    def test_square_tall_and_wide_sources_land_on_exact_delivery_size(self) -> None:
        target = (1080, 1350)
        for source_size in ((900, 900), (900, 1600), (1600, 900)):
            with self.subTest(source_size=source_size), tempfile.TemporaryDirectory(prefix="dc-export-test-") as temp:
                root = Path(temp)
                source = root / "source.png"
                destination = root / "delivery.png"
                image = Image.new("RGB", source_size, (18, 27, 34))
                ImageDraw.Draw(image).rectangle((source_size[0] // 3, source_size[1] // 3, source_size[0] * 2 // 3, source_size[1] * 2 // 3), fill=(231, 237, 243))
                image.save(source)
                dimensions, _ = GENERATE.export_to_delivery(source, destination, target)
                self.assertEqual(dimensions, target)
                self.assertEqual(GENERATE.sips_dims(destination), target)
                info = PROCESSING.image_info(destination)
                self.assertEqual((info["width"], info["height"]), target)
                self.assertEqual(info["mode"], "RGB")
                self.assertFalse(info["has_alpha"])


class BackgroundFlattenTests(unittest.TestCase):
    def test_only_near_navy_pixels_change(self) -> None:
        with tempfile.TemporaryDirectory(prefix="dc-flatten-test-") as temp:
            root = Path(temp)
            source = root / "before.png"
            destination = root / "after.png"
            image = Image.new("RGBA", (120, 100), (19, 29, 34, 255))
            pixels = image.load()
            control = [(0, 0), (119, 0), (0, 99), (119, 99), (60, 50)]
            for point, color in zip(control, [(20, 28, 32), (19, 27, 31), (21, 27, 33), (19, 27, 32), (18, 25, 29)]):
                pixels[point] = (*color, 255)
            brand_pixels = {
                (20, 20): (231, 237, 243),
                (21, 20): (244, 184, 72),
                (22, 20): (104, 225, 248),
                (23, 20): (46, 60, 75),
            }
            for point, color in brand_pixels.items():
                pixels[point] = (*color, 255)
            image.save(source)

            PROCESSING.flatten_background(source, destination, (18, 24, 29), 12)
            after = Image.open(destination)
            self.assertEqual(after.mode, "RGB")
            for point in control:
                self.assertEqual(after.getpixel(point), (18, 24, 29))
            for point, color in brand_pixels.items():
                self.assertEqual(after.getpixel(point), color)


class ShieldTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="dc-shield-test-")
        self.root = Path(self.temp.name)
        self.reference = ROOT / "assets" / "OLD-shield-logo.png"
        mark = Image.open(self.reference).convert("RGBA")
        self.mark = mark.resize((120, 122), Image.Resampling.LANCZOS)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def slide(self, placements: list[tuple[int, int]]) -> Path:
        image = Image.new("RGB", (1080, 1350), (18, 24, 29))
        for placement in placements:
            image.paste(self.mark, placement, self.mark)
        path = self.root / f"slide-{len(list(self.root.glob('*.png')))}.png"
        image.save(path)
        return path

    def test_absent_duplicate_and_outside_fail_exactly_one_inside_rule(self) -> None:
        region = GENERATE.parse_size("1080x1350")
        allowed = (0, int(region[1] * 0.76), int(region[0] * 0.25), region[1])

        present = PROCESSING.find_shield_matches(self.slide([(60, 1160)]), self.reference)
        self.assertEqual(len(present), 1)
        self.assertTrue(PROCESSING.box_inside(present[0]["box"], allowed))

        absent = PROCESSING.find_shield_matches(self.slide([]), self.reference)
        self.assertEqual(absent, [])

        duplicate = PROCESSING.find_shield_matches(self.slide([(60, 1160), (700, 1050)]), self.reference)
        self.assertEqual(len(duplicate), 2)

        outside = PROCESSING.find_shield_matches(self.slide([(700, 1050)]), self.reference)
        self.assertEqual(len(outside), 1)
        self.assertFalse(PROCESSING.box_inside(outside[0]["box"], allowed))


class PromptPreflightTests(unittest.TestCase):
    def test_gold_dot_passes_and_whole_balloon_fails(self) -> None:
        GENERATE.validate_gold_assignment({"n": 1, "visual": "A white line chart with one small gold dot at the break."})
        with self.assertRaises(SystemExit):
            GENERATE.validate_gold_assignment({"n": 2, "visual": "A whole gold balloon fills the band."})

    def test_regeneration_preserves_intent_and_named_object(self) -> None:
        prior = {"slides": [{
            "n": 1, "number": "01 / 07", "intent": "show a sudden drop",
            "subject": "line chart", "copy": "النص",
        }]}
        valid = [{
            "n": 1, "number": "01 / 07", "intent": "show a sudden drop",
            "subject": "line chart", "copy": "النص",
            "regeneration": {"reason": "quote orientation", "failure_class": "text-rendering"},
        }]
        GENERATE.enforce_regeneration_lock(prior, {}, valid, [1])
        changed = [{
            "n": 1, "number": "01 / 07", "intent": "show a sudden drop",
            "subject": "chair and suitcase", "copy": "النص",
            "regeneration": {"reason": "quote orientation", "failure_class": "text-rendering"},
        }]
        with self.assertRaises(SystemExit):
            GENERATE.enforce_regeneration_lock(prior, {}, changed, [1])

    def test_schema_two_prompt_records_intent_and_subject(self) -> None:
        with tempfile.TemporaryDirectory(prefix="dc-job-test-") as temp:
            path = Path(temp) / "job.json"
            render_spec = (ROOT / "references" / "render-spec.md").read_text(encoding="utf-8")
            payload = {
                "schema": 2,
                "identity": "OLD",
                "topic_slug": "meaning-lock",
                "shared_contract": render_spec,
                "refs": [],
                "size": {"generate": "1024x1536", "deliver": "1080x1350"},
                "slides": [{
                    "n": 1,
                    "number": "01 / 01",
                    "role": "hook",
                    "intent": "show the early break",
                    "subject": "line chart",
                    "visual": "A white line chart with one small gold dot at the break.",
                    "copy": "النص",
                }],
            }
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            job = GENERATE.load_job(path)
            prompt = GENERATE.build_prompt(job, job["slides"][0], 1, "./slide.png", [])
            self.assertIn("show the early break", prompt)
            self.assertIn("line chart", prompt)
            self.assertIn("01 / 01", prompt)


if __name__ == "__main__":
    unittest.main()
