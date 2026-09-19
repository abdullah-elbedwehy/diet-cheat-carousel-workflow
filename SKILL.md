---
name: diet-cheat-carousel-workflow
description: Produce approval-gated Diet & Cheat Egyptian-Arabic Instagram carousel slides in the OLD shield or NEW hands-and-heart identity. Delivery dimensions come from job.size.deliver, and every generated run must pass mechanical validation before it is reported.
---

# Diet & Cheat Carousel

Build the exact prompt package, show it, wait for approval, then run the one canonical generator. The user performs aesthetic review; the scripts perform mechanical checks.

`<skill>` means this skill directory.

## Hard rules

- **Single image-production path:** the agent has exactly one way to produce an image: `python3 <skill>/scripts/generate.py job.json --yes`. It never calls an image tool, never calls `codex exec` directly, never loops over slides, and never produces a slide outside this script. If the script cannot run, stop and report why; never fall back.
- Copy is locked. Preserve every supplied character, line break, punctuation mark, Latin token, emoji, and diacritic. Never rewrite, correct, translate, shorten, reorder, or add copy.
- The approval gate is mandatory for new runs and `--only` regeneration. Never infer approval from context, silence, a question, or an acknowledgement. Never pass `--yes` on the agent's own initiative.
- No aesthetic review. Never describe, score, or judge appearance. Exact resize verification, near-navy flattening, pixel sampling, REF-01 template matching, and OCR are deterministic image processing, not aesthetic review.
- Never pass `--concurrency` unless the user explicitly requests a cap. Default concurrency is the complete selected batch.
- Ask only for missing identity or missing slide copy. Use one identity per run. Never publish, upload, or message externally.

## Run — Phase 1: build, preview, stop

1. Parse identity (`OLD` or `NEW`), ordered locked copy, each supplied slide-number string, optional visual notes, explicit delivery size, and extra references. Missing identity or required copy means ask only for that and stop.
2. Read `references/identity-guide.md`, `references/compositions.md`, `references/prompt-contract.md`, `references/render-spec.md`, and `references/workflow.md`. Load lessons with `python3 <skill>/scripts/learn.py list --rules-only --identity <ID>`.
3. Write schema-2 `job.json`. Insert `references/render-spec.md` **byte-for-byte** into `shared_contract`, followed by bounded identity and lesson rules. For every slide write separate `number`, `intent`, `subject`, `visual`, and `copy` fields. `intent` states what the slide communicates; `subject` names the object that must remain; `visual` is one scene line.
4. Apply the structural gold rule from `render-spec.md` before dispatch. If a scene names a whole object as gold, rewrite that scene so gold is only a small object part. The generator preflight must also pass.
5. Run `python3 <skill>/scripts/generate.py job.json --dry-run`. For regeneration add `--only N,M --output-dir <same folder>`. This writes the job and exact prompts but dispatches nothing.
6. Show the shared contract once. For every selected slide show its number string, intent, subject, and exact copy. Then stop with one line: `Waiting for explicit go-ahead.`

Any response except an explicit generation command is an edit request. Apply the edit, rerun Phase 1, show the complete revised preview, and wait again.

## Run — Phase 2: explicit go only

Accept only an unambiguous generation command after the latest preview: `ابدأ ولّد`, `ولّد`, `go`, `generate`, `approved`, or `اعتمد`.

7. Run `python3 <skill>/scripts/generate.py <output>/job.json --yes --output-dir <output>`. For approved regeneration include `--only N,M`. `--yes` exists for explicit approved or non-interactive use, is off by default, and is never added without that approval.
8. Mechanical validation is mandatory. The generator invokes `scripts/validate.py`; a run is not reportable until `mechanical-validation.json` passes. One mechanical retry may regenerate the entire failed slide with intent, subject, visual, number, and copy unchanged. Never patch, inpaint, or overlay.
9. Before reporting, require `prompts.md`, `logs/` with one `slideNN.prompt.txt` per selected slide, `manifest.json`, and `manifest.json.dispatch`. Run `python3 <skill>/scripts/verify_run.py <output>`. If any artifact or dispatch proof is missing, say plainly that the script did not complete; never report success.
10. Report the output folder, status table, the dispatch line (`workers`, `concurrency`, `start_spread`, `simultaneous`), and validation columns for dimensions, RGB/no alpha, background, shield, and guillemets. Point to `REVIEW.md`; say nothing aesthetic.

## Regenerate

Record `regeneration.reason` and `regeneration.failure_class`. Intent never changes. Subject changes only when `regeneration.failure_class` is exactly `object`. Change only the visual detail required by the recorded failure; keep number and copy locked. Run the same Phase 1 preview for `--only`, show the revised fields, and wait for explicit approval.

A mechanical retry is not a prompt rewrite: it reuses intent, subject, visual, number, and copy unchanged, then regenerates the whole slide once.

## Learn

`learn.py add` requires a lesson class. This release adds and documents that argument.

```bash
python3 <skill>/scripts/learn.py add \
  --identity <OLD|NEW|BOTH> \
  --class <text-rendering|geometry|colour|identity|composition|output-format> \
  --trigger "<what the user said>" \
  --pattern "<generalized cause>" \
  --rule "<one imperative instruction>"
```

Confirm the lesson id. `show lessons` runs `learn.py list`; `promote lessons` runs `learn.py promote`, then commit and push.

## References and scripts

- `references/render-spec.md` — numeric source of truth inserted byte-for-byte into `shared_contract`; delivery, background, shield, gold, copy, and meaning lock.
- `references/workflow.md` — schema 2, approval gate, output layout, dispatch, validation, and failure handling.
- `references/prompt-contract.md` — shared/per-slide prompt boundary.
- `references/identity-guide.md` — identity assets and palette only; fixed geometry comes from `render-spec.md`.
- `references/compositions.md` — role composition and reviewed gold examples.
- `references/learning.md` — lesson classes and lifecycle.
- `scripts/generate.py` — only image-producing path; approval-gated batch dispatcher.
- `scripts/validate.py` — mechanical raster checks and `REVIEW.md` columns.
- `scripts/verify_run.py` — canonical artifact and dispatch-proof guard.
- `assets/` — production marks and identity references attached by the generator.
