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
  "schema": 1,
  "identity": "OLD",
  "topic_slug": "coffee-vs-energy",
  "refs": ["assets/OLD-shield-logo.png", "assets/OLD-example.png"],
  "size": {"generate": "1024x1536", "deliver": "1080x1440"},
  "lessons_applied": ["L-20260917-001"],
  "shared_contract": "...",
  "slides": [
    {"n": 1, "role": "hook", "copy": "...verbatim...", "visual": "..."}
  ]
}
```
`topic_slug`: 2–4 lowercase ASCII words from the topic, hyphenated. Never Arabic in the slug.

## 4. Generate
`python3 <skill>/scripts/generate.py job.json`
- All slides dispatch at once as independent `codex exec` workers with the refs attached.
- Each worker makes one image, saves `source/DC-<ID>-<slug>-slideNN-source.png`.
- Export: centered 3:4 crop + resize → `slides/DC-<ID>-<slug>-slideNN.png` at `1080x1440`.
- Checks: file exists, byte size, dimensions. Nothing visual.
- Writes `brief.md`, `prompts.md`, `job.json`, `manifest.json`, `REVIEW.md`, `logs/`.
- Output folder: `~/Downloads/DC-<ID>-<slug>-<YYYYMMDD-HHMM>/`.

## 5. Report
Print the output folder path and the status table from the script. Say the user reviews now. Do not open, view, describe, or judge any image.

## 6. Regenerate
User names slides (+ what went wrong). Steps: record the lesson (see `learning.md`) → rebuild only those slides' `visual` with the new rule → `generate.py job.json --only N,M --output-dir <same folder>`. Previous files go to `history/`.

## 7. Failures
A slide `failed` after 2 attempts → report it with the log path; do not auto-retry further. User decides.
