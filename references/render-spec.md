# Numeric render specification

Insert this file byte-for-byte into `job.shared_contract`. Do not paraphrase,
shorten, reorder, or selectively copy it.

## Canvas and output

- Delivery canvas: `job.size.deliver`; width and height are exact.
- Generation canvas: `job.size.generate`; export may center-crop and resize only the complete raster.
- OLD background: solid opaque `#12181D`; NEW background comes from `job.background.hex`.
- Output: RGB PNG, 8 bits per channel, no alpha channel.
- After resize, mechanically flatten every pixel whose red, green, and blue channels are each within `12` of the background target. Set those pixels to the exact target. Do not alter any other pixel.
- Tolerance `12` is empirical, not aesthetic: across the rejected `first-week-fatigue` set, all 32 corner samples were at most 7 levels from `#12181D`, while a dark illustration sample `#060B11` crossed the boundary at 13 on green. On the recorded illustration crop, 395,110 near-navy pixels changed and all 17,066 pixels outside tolerance stayed byte-identical.
- After export, read the delivered file dimensions back. Any mismatch with `job.size.deliver` is a hard failure. Never accept a near match and never silently resize again.
- The four corners and center control pixel must each equal the background target exactly. Those control points must remain unobstructed.

## Fixed shield

- OLD identity uses REF-01 exactly once.
- Width: `90 px`; left: `60 px`; bottom: `70 px`; preserve aspect ratio.
- No second shield, no shield elsewhere, no mirroring, no recoloring, no wordmark.
- Mechanical validation template-matches REF-01 across the complete slide. Zero matches, more than one match, or the only match outside the fixed bottom-left region fails.

## Title, body, and supplied copy

- Arabic is right-to-left, right-aligned, connected, and retains every supplied diacritic.
- Preserve every supplied character, punctuation mark, numeral, Latin token, emoji, space, and line break.
- Arabic guillemets use the supplied logical sequence and correct RTL mirrored orientation.
- When guillemets occur, crop the body region and OCR it. If orientation boxes are reliable, validate sequence, RTL position, and visible direction. If character-level boxes are unreliable, print the OCR body in `REVIEW.md` as `OCR-ONLY` for one-glance review.
- Never rewrite, correct, translate, shorten, expand, reorder, or add copy.

## Illustration treatment

- Outlined flat vector objects only. No gradients, shadows, glow, blur, grain, texture, 3D, photorealism, double outlines, or decorative particles.
- Maximum four named objects. No invented object may replace the job's named subject.
- Exactly one gold accent may occur in a filled illustration band.
- The gold element is a **small part of an object, never a whole object**: a dot on a line, a handle on a door, one rung of a ladder, one step of a staircase, or a band on a tank.
- If a job names a whole object as gold, the job is wrong and the agent must rewrite it before generation. Whole gold balloons, staircases, organs, doors, tanks, glasses, shakers, moons, clocks, puzzles, chairs, or suitcases are forbidden.
- Cyan is chrome only unless the identity contract explicitly says otherwise.

## Meaning lock and regeneration

- Every slide records `intent` (what it must communicate), `subject` (the named object that must remain), and `visual` (what to draw) separately.
- A regeneration changes only what its recorded failure reason requires.
- Intent never changes during regeneration.
- Subject never changes unless `regeneration.failure_class` is exactly `object` because the object itself failed.
- Mechanical retries reuse the same intent, subject, visual, and copy, and regenerate the whole slide once. Never patch, inpaint, overlay, or replace part of a raster.
