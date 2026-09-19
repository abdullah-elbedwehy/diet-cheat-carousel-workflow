---
name: diet-cheat-carousel-workflow
description: Produce Diet & Cheat Egyptian-Arabic Instagram carousel slides from user-supplied final copy, in the OLD shield or NEW hands-and-heart identity. Generates every slide in parallel, exports to the exact declared size, runs deterministic raster validation, and leaves aesthetic review to the user.
---

# Diet & Cheat Carousel — direct production

You turn the user's locked slide copy into image prompts, run the parallel generator, and report the output folder. The user reviews. You do not.

## Commands the user may say

| User says | You do |
|---|---|
| `OLD.` / `NEW.` + slides | Full run (§Run) |
| `regenerate slide 3` (+ reason) | Record lesson if a reason is given → §Regenerate |
| feedback like `slide 2 الكلمة الإنجليزية اتعكست` | Record lesson (§Learn) → offer regenerate |
| `pull latest update` / `حدّث الوركفلو` | `bash <skill>/scripts/update.sh` → show its output |
| `show lessons` | `python3 <skill>/scripts/learn.py list` |
| `promote lessons` (maintainer) | `python3 <skill>/scripts/learn.py promote` then commit + push |

`<skill>` = this skill's directory (the folder containing this file).

## Hard rules

- Copy is locked. Every character the user supplied renders as-is. You never rewrite, fix, translate, shorten, reorder, or add text.
- No aesthetic review. Never describe, score, or judge how a generated image looks. Deterministic image processing is allowed: exact resize verification, near-navy pixel flattening, pixel samples, REF-01 template matching, and OCR. These checks do not change this rule.
- `scripts/generate.py` is the only valid image-producing path. Never call Imagegen directly from the outer agent, even when the brief asks for parallel generation. A folder of images without the runner's `job.json`, `prompts.md`, `manifest.json`, `logs/`, `source/`, and passing `run-verification.json` is a failed/bypassed run, not a delivery.
- Never pass `--concurrency` unless the user explicitly asks for a concurrency cap. The default is the full selected worker count.
- Ask only for a missing identity or a missing slide's text. Nothing else.
- One identity per run. Never mix OLD and NEW marks.
- Never publish, upload, or message externally.

## Run

1. Parse the brief: identity, slides in order, per-slide copy, optional visual notes / size / extra refs. Missing identity or slide text → ask for exactly that and stop.
2. Lessons: `python3 <skill>/scripts/learn.py list --rules-only --identity <ID>`.
3. Read `references/identity-guide.md`, `references/compositions.md`, `references/prompt-contract.md`, and `references/render-spec.md`. Put `render-spec.md` byte-for-byte in `shared_contract`. Classify each slide's role and write separate `intent`, `subject`, and one-line `visual` fields.
4. Before any generation, reject any scene line that makes a whole object gold. Rewrite it as one small object part: dot, tip, handle, rung, step, or band. Write schema-2 `job.json` using `references/workflow.md`.
5. Run: `python3 <skill>/scripts/generate.py job.json`
   All slides dispatch at once. Wait for the script to finish. Do not run image generation yourself.
6. Require `mechanical-validation.json` and `run-verification.json` to pass. Confirm exact dimensions, RGB/no alpha, exact five background samples, shield check, guillemet status, and dispatch proof. A mechanical failure triggers one automatic whole-slide regeneration. Never patch a raster.
7. Report: the output folder path (in `~/Downloads`), the script's status table, dispatch proof, and one line: the user reviews now via `REVIEW.md`. Nothing about how the images look.

## Regenerate

User names slide(s). Record `regeneration.reason` and `regeneration.failure_class`, then record the lesson when reusable. Keep `intent` byte-identical. Keep `subject` byte-identical unless the failure class is exactly `object`. Change only the visual detail required by the reason. Then:
`python3 <skill>/scripts/generate.py job.json --only 3,5 --output-dir <same output folder>`
Report as in step 7. Previous versions are moved to `history/` automatically.

## Learn

```
python3 <skill>/scripts/learn.py add --identity <OLD|NEW|BOTH> \
  --trigger "<what the user said>" \
  --pattern "<generalized cause in the copy/prompt>" \
  --rule "<one imperative instruction for the image model>"
```
Rules and format: `references/learning.md`. Confirm the lesson id to the user in one line.

## References

- `references/workflow.md` — job.json schema, output layout, failure handling.
- `references/identity-guide.md` — palettes, marks, shared visual language.
- `references/compositions.md` — slide role → layout.
- `references/prompt-contract.md` — how to write `shared_contract` and `visual`.
- `references/render-spec.md` — exact output, flattening, shield, gold, and regeneration contract.
- `references/learning.md` — lesson lifecycle.
- `scripts/verify_run.py` — rejects bypassed runs and full-parallel runs whose worker-start spread exceeds the documented threshold.
- `assets/` — logos and finish references attached to workers.
