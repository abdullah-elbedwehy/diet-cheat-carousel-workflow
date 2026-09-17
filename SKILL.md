---
name: diet-cheat-carousel-workflow
description: Produce Diet & Cheat Egyptian-Arabic Instagram carousel slides from user-supplied final copy, in the OLD shield or NEW hands-and-heart identity. Generates every slide in parallel through codex exec workers, exports to 1080x1440, saves to a folder in ~/Downloads, and never reviews images itself. Use when the user supplies slide text and says OLD or NEW, asks to regenerate a slide, gives feedback on a slide, or says "pull latest update".
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
- No visual review. Never open, view, describe, score, or judge a generated image. Never regenerate on your own initiative.
- Ask only for a missing identity or a missing slide's text. Nothing else.
- One identity per run. Never mix OLD and NEW marks.
- Never publish, upload, or message externally.

## Run

1. Parse the brief: identity, slides in order, per-slide copy, optional visual notes / size / extra refs. Missing identity or slide text → ask for exactly that and stop.
2. Lessons: `python3 <skill>/scripts/learn.py list --rules-only --identity <ID>`.
3. Read `references/identity-guide.md`, `references/compositions.md`, `references/prompt-contract.md`. Classify each slide's role from its content shape. Write `shared_contract` and each slide's `visual` per the contract. Paste the lesson rules under `LEARNED RULES` and list their ids in `lessons_applied`.
4. Write `job.json` in the current working directory. Schema and slug rules: `references/workflow.md`.
5. Run: `python3 <skill>/scripts/generate.py job.json`
   All slides dispatch at once. Wait for the script to finish. Do not run image generation yourself.
6. Report: the output folder path (in `~/Downloads`), the script's status table, and one line: the user reviews now via `REVIEW.md`. Nothing about how the images look.

## Regenerate

User names slide(s). If they gave a reason, record the lesson first (§Learn). Rewrite only those slides' `visual` to apply the rule. Then:
`python3 <skill>/scripts/generate.py job.json --only 3,5 --output-dir <same output folder>`
Report as in step 6. Previous versions are moved to `history/` automatically.

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
- `references/learning.md` — lesson lifecycle.
- `assets/` — logos and finish references attached to workers.
