# Changelog

## 1.2.0 — 2026-09-19

- **Wrong export size:** shipped rasters remained `1122x1402`. Cause: the crop branch resized its destination in place, which did not reliably produce the requested pixels. Export now uses distinct crop and resize files, reads the delivered dimensions back, and hard-fails on any mismatch. Square, tall, and wide source tests assert exact `job.size.deliver` output.
- **Vignette background:** shipped backgrounds drifted around `#12181D`. Cause: model radial shading survived prompt wording. Export now flattens only pixels within 12 per RGB channel to exact navy, emits RGB/no alpha, and requires exact four-corner plus center samples. The tolerance comes from rejected-slide evidence and a before/after illustration crop proves every non-near-navy pixel remained byte-identical.
- **Missing/duplicated/misplaced shield:** CTA could ship without REF-01. Cause: no mechanical mark check existed. Validation now template-matches the reference across the whole slide; exactly one match must be inside the fixed bottom-left region. Real rejected slides and synthetic absent/duplicate/outside fixtures verify the detector.
- **Mirrored guillemets:** CTA punctuation could ship wrong. Cause: copy validation did not inspect the body raster. Validation now crops the body, runs macOS Vision OCR, verifies logical sequence and RTL geometry when character boxes are reliable, and always prints OCR body text into `REVIEW.md`; unreliable boxes are labeled `OCR-ONLY` instead of pretending orientation was proven.
- **Inert gold budget:** whole gold objects passed because an image model cannot measure an area fraction. The contract now permits gold only as a small object part. Prompt preflight rejects whole-object gold before dispatch, and reviewed pass/fail assignments are recorded in `references/compositions.md`.
- **Meaning drift on regeneration:** a failed scene could change from one object to an unrelated one. Cause: intent and object were embedded only in free-form visual prose. Schema 2 now records `intent`, `subject`, and `visual` separately; regeneration locks intent and subject unless the recorded failure class is `object`.
- Mechanical shield or guillemet failures now join dimension/background failures in `validate.py`, appear as columns in `REVIEW.md`, and trigger one automatic whole-slide retry.

## 1.1.0 — 2026-09-19

- Proved the recurring serialization report was a runner bypass: the installed skill target was missing and recent outputs had none of the canonical `job.json`, `prompts.md`, `manifest.json`, `source/`, or `logs/` artifacts.
- Kept the thread plus `codex exec --ephemeral` architecture. Eight current CLI sessions started within `0.015150s`; two real eight-Imagegen rounds started within `0.012522–0.014917s`. Observed concurrency is at least eight for both layers.
- Rejected process replacement and isolated `CODEX_HOME` because no local serialization was measured; rejected direct API migration because it adds auth/cost plumbing without addressing the bypass; rejected a lower ceiling and multi-slide batching because the measured eight-way path works and one-slide-one-image remains mandatory.
- Added per-worker UTC start/completion events, `manifest.json.dispatch`, a dispatch line at the top of `REVIEW.md`, and a `2.0s` full-parallel start-spread guard.
- Added `scripts/verify_run.py` and regression tests. Missing canonical artifacts or invalid full-parallel timing now fail loudly.
- Documented that `--concurrency` must not be passed unless the user explicitly requests a cap.

## 1.0.1

- Refreshed `manifest.json.output_dir` during regeneration into an existing output folder.
- Split the `sips` crop and resize export into separate calls and improved worker copy guidance and status formatting.
