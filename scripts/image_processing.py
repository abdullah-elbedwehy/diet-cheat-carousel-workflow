#!/usr/bin/env python3
"""Deterministic raster processing and mechanical image checks.

Background flattening in this module is image processing, not aesthetic review:
the AI never judges how an image looks. Pixels are selected only by a fixed RGB
distance rule, then validators compare exact values and fixed geometry.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageFilter
except ImportError as exc:  # pragma: no cover - exercised by installer checks
    raise RuntimeError(
        "Pillow is required. Run: python3 -m pip install -r requirements.txt"
    ) from exc


NAVY = (18, 24, 29)  # #12181D
NAVY_TOLERANCE = 12


def within_rgb_tolerance(pixel: tuple[int, int, int], target: tuple[int, int, int], tolerance: int) -> bool:
    """Return true when every RGB channel is within the inclusive tolerance."""
    return max(abs(pixel[index] - target[index]) for index in range(3)) <= tolerance


def flatten_background(
    source: Path,
    destination: Path,
    target: tuple[int, int, int] = NAVY,
    tolerance: int = NAVY_TOLERANCE,
) -> dict:
    """Set only near-target pixels to the exact target and emit opaque RGB PNG.

    This is deterministic image processing, not aesthetic review. The rule does
    not inspect semantics or judge appearance: each pixel either falls within
    the fixed per-channel tolerance or is copied byte-for-byte. The output is
    always RGB, so no alpha channel survives.
    """
    if tolerance < 0:
        raise ValueError("tolerance must be >= 0")
    with Image.open(source) as opened:
        image = opened.convert("RGB")
    raw = bytearray(image.tobytes())
    changed = 0
    untouched = 0
    for offset in range(0, len(raw), 3):
        pixel = (raw[offset], raw[offset + 1], raw[offset + 2])
        if within_rgb_tolerance(pixel, target, tolerance):
            if pixel != target:
                raw[offset:offset + 3] = bytes(target)
                changed += 1
        else:
            untouched += 1
    flattened = Image.frombytes("RGB", image.size, bytes(raw))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{destination.stem}-", suffix=".png", dir=destination.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        flattened.save(temporary, format="PNG")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "width": image.width,
        "height": image.height,
        "mode": "RGB",
        "target": list(target),
        "tolerance": tolerance,
        "changed_pixels": changed,
        "untouched_outside_tolerance": untouched,
    }


def image_info(path: Path) -> dict:
    with Image.open(path) as image:
        image.load()
        has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
        return {"width": image.width, "height": image.height, "mode": image.mode, "has_alpha": has_alpha}


def sample_control_pixels(path: Path) -> list[dict]:
    with Image.open(path) as opened:
        image = opened.convert("RGB")
    points = [
        (0, 0),
        (image.width - 1, 0),
        (0, image.height - 1),
        (image.width - 1, image.height - 1),
        (image.width // 2, image.height // 2),
    ]
    return [{"xy": [x, y], "rgb": list(image.getpixel((x, y)))} for x, y in points]


def _white_mask(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    raw = rgb.tobytes()
    mask = bytearray(rgb.width * rgb.height)
    out = 0
    for offset in range(0, len(raw), 3):
        red, green, blue = raw[offset:offset + 3]
        mask[out] = 255 if min(red, green, blue) >= 170 and max(red, green, blue) - min(red, green, blue) <= 60 else 0
        out += 1
    return Image.frombytes("L", rgb.size, bytes(mask)).convert("1")


def _components(mask: Image.Image, scale: int) -> list[tuple[int, int, int, int]]:
    pixels = mask.load()
    width, height = mask.size
    seen: set[tuple[int, int]] = set()
    boxes: list[tuple[int, int, int, int]] = []
    for y in range(height):
        for x in range(width):
            if not pixels[x, y] or (x, y) in seen:
                continue
            seen.add((x, y))
            stack = [(x, y)]
            left = right = x
            top = bottom = y
            while stack:
                current_x, current_y = stack.pop()
                left = min(left, current_x)
                right = max(right, current_x)
                top = min(top, current_y)
                bottom = max(bottom, current_y)
                for neighbor in (
                    (current_x + 1, current_y),
                    (current_x - 1, current_y),
                    (current_x, current_y + 1),
                    (current_x, current_y - 1),
                ):
                    nx, ny = neighbor
                    if 0 <= nx < width and 0 <= ny < height and pixels[nx, ny] and neighbor not in seen:
                        seen.add(neighbor)
                        stack.append(neighbor)
            boxes.append((left * scale, top * scale, (right + 1) * scale, (bottom + 1) * scale))
    return boxes


def _normalized_binary(mask: Image.Image, box: tuple[int, int, int, int], size: int = 48) -> Image.Image | None:
    cropped = mask.crop(box)
    content = cropped.getbbox()
    if not content:
        return None
    return (
        cropped.crop(content)
        .resize((size, size), Image.Resampling.LANCZOS)
        .convert("L")
        .point(lambda value: 255 if value >= 96 else 0)
        .convert("1")
    )


def find_shield_matches(image_path: Path, reference_path: Path, minimum_score: float = 0.70) -> list[dict]:
    """Template-match shield-like white components across the complete slide.

    White components are clustered mechanically, normalized to 48x48, and
    compared with REF-01's alpha silhouette using intersection-over-union.
    """
    with Image.open(image_path) as opened:
        image = opened.convert("RGB")
    with Image.open(reference_path) as opened:
        reference = opened.convert("RGBA")
    reference_mask = reference.getchannel("A")
    reference_box = reference_mask.getbbox()
    if not reference_box:
        raise ValueError(f"shield reference has no opaque pixels: {reference_path}")
    reference_normalized = _normalized_binary(reference_mask.convert("1"), reference_box)
    assert reference_normalized is not None

    scale = 4
    white = _white_mask(image)
    small = (
        white.resize((max(1, image.width // scale), max(1, image.height // scale)), Image.Resampling.BOX)
        .convert("L")
        .point(lambda value: 255 if value > 20 else 0)
        .filter(ImageFilter.MaxFilter(5))
        .convert("1")
    )
    matches: list[dict] = []
    for box in _components(small, scale):
        width = box[2] - box[0]
        height = box[3] - box[1]
        if not (45 <= width <= 240 and 45 <= height <= 240 and 0.5 <= width / height <= 1.5):
            continue
        candidate = _normalized_binary(white, box)
        if candidate is None:
            continue
        intersection = sum(ImageChops.logical_and(reference_normalized, candidate).histogram()[1:])
        union = sum(ImageChops.logical_or(reference_normalized, candidate).histogram()[1:])
        score = intersection / union if union else 0.0
        if score >= minimum_score:
            matches.append({"box": list(box), "score": round(score, 4)})
    return sorted(matches, key=lambda item: item["score"], reverse=True)


def box_inside(box: list[int], region: tuple[int, int, int, int]) -> bool:
    center_x = (box[0] + box[2]) / 2
    center_y = (box[1] + box[3]) / 2
    return region[0] <= center_x <= region[2] and region[1] <= center_y <= region[3]


def chevron_direction(image: Image.Image) -> str:
    """Classify a cropped guillemet as left/right using its middle-row tip."""
    gray = image.convert("L")
    mask = gray.point(lambda value: 255 if value >= 135 else 0)
    content = mask.getbbox()
    if not content:
        return "unknown"
    mask = mask.crop(content)
    pixels = mask.load()
    width, height = mask.size
    middle: list[int] = []
    outer: list[int] = []
    for y in range(height):
        for x in range(width):
            if not pixels[x, y]:
                continue
            if height * 0.35 <= y <= height * 0.65:
                middle.append(x)
            elif y <= height * 0.25 or y >= height * 0.75:
                outer.append(x)
    if not middle or not outer:
        return "unknown"
    difference = (sum(middle) / len(middle)) - (sum(outer) / len(outer))
    if difference <= -0.06 * width:
        return "left"
    if difference >= 0.06 * width:
        return "right"
    return "unknown"
