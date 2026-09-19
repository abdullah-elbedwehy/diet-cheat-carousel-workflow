# Execution contract

## 1. Brief intake
Brief = identity (`OLD`/`NEW`) + slides in final order with exact on-image copy (+ optional visual notes, size, extra refs).
Missing identity or a slide's copy → ask only for that. Nothing else is asked. No concept pack, caption, or copy rewrite. The mandatory approval gate below still applies.

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
      "number": "01 / 07",
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

## 4. Approval preview

`python3 <skill>/scripts/generate.py job.json --dry-run`

Show `shared_contract` once, then each selected slide's number string, intent,
subject, and exact copy. Stop and wait. Missing `--yes` also halts safely at
this gate with zero workers dispatched. The gate applies to `--only`.

Only `ابدأ ولّد`, `ولّد`, `go`, `generate`, `approved`, or `اعتمد` is approval.
Anything else requests an edit or leaves the preview pending.

Before preview, reject and rewrite any scene that names an entire object as
gold. The normative gold rule is in `render-spec.md`.

## 5. Generate after approval

`python3 <skill>/scripts/generate.py job.json --yes`

For an approved regeneration:
`python3 <skill>/scripts/generate.py job.json --only N,M --output-dir <same-folder> --yes`

The agent never adds `--yes` without a user go word. `--yes` exists for
explicitly approved non-interactive execution and is off by default.

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

## 6. Validate and report

Generation runs `scripts/validate.py` before verification. A run is not
reportable until validation passes. Before reporting, confirm `prompts.md`, one
prompt file per slide under `logs/`, `manifest.json`, and
`manifest.json.dispatch` all exist. If any is absent, say plainly that the
script did not run.

Print the output folder, the dispatch line, and validation columns from
`REVIEW.md`. Require `run-verification.json` to pass. Say the user reviews now.
Do not open, describe, or aesthetically judge any image.

## 7. Regenerate
User names slides (+ what went wrong). Record `regeneration.reason` and `regeneration.failure_class`. Intent remains byte-identical. Subject remains byte-identical unless the failure class is exactly `object`. Number and copy remain byte-identical. Rewrite only the visual detail named by the failure. Preview with `--only`, show the revised fields, and wait for approval before adding `--yes`. Previous files go to `history/` only after approved generation starts.

## 8. Failures
A mechanically failed slide gets one automatic whole-slide retry with the same intent, subject, copy, and visual. A slide still failed after that retry is reported with the log path; no patch, inpaint, overlay, or further automatic retry occurs.
