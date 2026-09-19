# Shared prompt contract

`job.shared_contract` is one text block every worker receives. Start with `references/render-spec.md` byte-for-byte, then append the bounded identity and lesson blocks below.

1. **Use case + asset**: `Use case: infographic-diagram. Asset: Arabic Instagram carousel slide N of T, portrait at job.size.deliver aspect ratio, one complete raster.`
2. **Identity block**: palette, mark, decoration from `identity-guide.md` for the selected identity. Name the attached logo image as the exact mark.
3. **Set consistency**: shared grid, logo top-right, 96 px outer margins, headline zone top 25–40%, footer zone, same lighting and line system across all slides.
4. **Arabic rendering**: right-to-left, properly connected letterforms, modern bold geometric Arabic display for headline, clean Arabic sans for body, 1.35–1.5 line height. Latin tokens LTR, isolated, exact capitalization. Emoji rendered as supplied.
5. **Copy lock**: render every supplied character verbatim; no added words, labels, captions, page numbers, watermarks, brand names, or decorative text.
6. **Avoid list**: the other identity's mark, neon glow, glossy gamer look, bodybuilding clichés, people/hands/faces, branded packaging, fake words, Latin-looking Arabic, broken joins, duplicated or reversed text, wrong numbers.
7. **Active lessons**: output of `python3 scripts/learn.py list --rules-only --identity <ID>`, pasted as a `LEARNED RULES` list. Also record their ids in `job.lessons_applied`.

Per slide, record three separate values:

- `intent`: what the slide must communicate; this never changes on regeneration.
- `subject`: the named object that must remain unless the failure itself is classified `object`.
- `visual`: exactly one scene line. Gold may name only a small object part from `render-spec.md`, never a whole object.

On regeneration, add `regeneration.reason` and `regeneration.failure_class`. Change only the visual detail named by the reason.

Per-slide `copy`: the supplied text exactly, line breaks preserved.
