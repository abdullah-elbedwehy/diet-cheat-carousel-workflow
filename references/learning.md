# Learning system

The AI never reviews images. Learning comes from the user's review and regenerate requests. Every lesson is a structured block, stored by `scripts/learn.py`.

## When to record
- User reports a problem on any slide (text broken, logo wrong, layout wrong, object wrong, color wrong).
- User regenerates a slide with a reason.
- User states a standing preference ("always put the score bottom-left").

Do not record: praise, one-off content changes, requests that are already covered by an active lesson (apply it instead).

## How to record
```
python3 <skill>/scripts/learn.py add \
  --identity OLD|NEW|BOTH \
  --class text-rendering|geometry|colour|identity|composition|output-format \
  --trigger "what the user said" \
  --pattern "what in the copy/prompt caused it (generalized)" \
  --rule "one imperative instruction to add to the shared contract next time"
```
`--class` is required for every new lesson. Lessons from before schema 1.3 are
read as `composition` until they are curated.

Rule quality: specific, testable, phrased for the image model. Bad: "make Arabic better". Good: "Render Latin tokens that follow the Arabic prefix الـ on their own line; never inline them inside an Arabic sentence."

## How lessons are used
- Every run start: `learn.py list --rules-only --identity <ID>` → pasted into the shared contract as `LEARNED RULES`.
- Ids go into `job.lessons_applied` so the run log shows which rules were live.
- `learn.py retire <id>` when a rule stops being useful. Retired rules stay in the file for history.

## Files
- `learnings/shared/lessons.md` — versioned, comes with `pull latest update`.
- `learnings/local/lessons.md` — this machine only, gitignored. Local wins on id clash.
- `learnings/local/runs.jsonl` — one line per generate run: identity, slug, output dir, per-slide status, lessons applied.

## Maintainer
`learn.py promote` moves active local lessons into shared, then commit + push. Users receive them on the next update.
