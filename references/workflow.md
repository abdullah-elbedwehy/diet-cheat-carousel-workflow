# Execution contract

## 1. Brief intake
Brief = identity (`OLD`/`NEW`) + slides in final order with exact on-image copy (+ optional visual notes, size, extra refs).
Missing identity or a slide's copy → ask only for that. Nothing else is asked. No concept pack, no approval gate, no caption, no rewrite.

## 2. Lessons
Run `python3 scripts/learn.py list --rules-only --identity <ID>`. Paste the rules into the shared contract. Put the ids in `job.lessons_applied`.

## 3. job.json
Write to the current working directory (not inside the skill). Schema:

```json
{
  "schema": 2,
  "identity": "OLD",
  "topic_slug": "coffee-vs-energy",
  "refs": ["assets/OLD-shield-logo.png", "assets/OLD-example.png"],
  "size": {"generate": "1024x1536", "deliver": "1080x1350"},
  "background": {"hex": "#12181D", "tolerance": 12},
  "lessons_applied": ["L-20260917-001"],
  "shared_contract": "...",
  "slides": [
    {
      "n": 1,
      "role": "hook",
      "intent": "what the slide must communicate",
      "subject": "named object that must remain",
      "copy": "...verbatim...",
      "visual": "one scene line"
    }
  ]
}
```
`topic_slug`: 2–4 lowercase ASCII words from the topic, hyphenated. Never Arabic in the slug. `shared_contract` contains `references/render-spec.md` byte-for-byte. Every slide records meaning (`intent`) separately from drawing (`subject` + `visual`).

## 4. Generate
`python3 <skill>/scripts/generate.py job.json`
- All slides dispatch at once as independent `codex exec` workers with the refs attached.
- Do not pass `--concurrency` unless the user explicitly requested a cap. With no flag, the effective limit is the full selected worker count.
- Each worker makes one image, saves `source/DC-<ID>-<slug>-slideNN-source.png`.
- Export: centered whole-raster crop + distinct-file resize → exact `job.size.deliver`, then near-navy flattening. The delivered dimensions are read back; mismatch is a hard failure.
- Checks: exact dimensions, RGB/no alpha, exact four corners + center, REF-01 shield count/location, and guillemet OCR. These are mechanical image-processing checks, not aesthetic review.
- Writes `brief.md`, `prompts.md`, `job.json`, `manifest.json`, `REVIEW.md`, `run-verification.json`, `source/`, and `logs/`.
- Output folder: `~/Downloads/DC-<ID>-<slug>-<YYYYMMDD-HHMM>/`.

### Dispatch proof

`manifest.json.dispatch` records the effective concurrency limit, every worker's UTC start/completion timestamps, the first-to-last start spread, and the simultaneous-dispatch verdict. `logs/batch-events.jsonl` keeps the corresponding append-only events.

The full-parallel start-spread threshold is `2.0s`. The measured 2026-09-19 baseline on this Mac was `0.015150s` for eight successful `codex exec` sessions and `0.012522–0.014917s` for two real eight-image rounds. The observed Codex and Imagegen concurrency ceiling is therefore at least eight; a higher ceiling was not tested. Completion times may differ by a minute even when every worker started together.

After each run, `scripts/verify_run.py` checks the canonical artifact set and dispatch proof. A full-parallel run fails when its start spread exceeds `2.0s`, when a worker completes before every worker starts, or when required runner artifacts are missing. Images created outside `scripts/generate.py` cannot pass this check.

## 5. Report
Print the output folder path, status table, and `manifest.json.dispatch` summary. Require `run-verification.json` to pass. Say the user reviews now. Do not open, view, describe, or judge any image.

## 6. Regenerate
User names slides (+ what went wrong). Record `regeneration.reason` and `regeneration.failure_class`. Intent remains byte-identical. Subject remains byte-identical unless the failure class is exactly `object`. Rewrite only the visual detail named by the failure. Then run `generate.py job.json --only N,M --output-dir <same folder>`. Previous files go to `history/`.

## 7. Failures
A mechanically failed slide gets one automatic whole-slide retry with the same intent, subject, copy, and visual. A slide still failed after that retry is reported with the log path; no patch, inpaint, overlay, or further automatic retry occurs.
