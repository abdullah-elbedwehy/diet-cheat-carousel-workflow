# Composition templates by slide role

The agent classifies each supplied slide into one role from its content shape. The role picks a composition. Copy is never changed by classification.

| Role | Signals in the copy | Composition |
|---|---|---|
| `hook` | first slide; short; question or bold claim; `VS`; ≤ 4 lines | Hero object(s) fill the lower 55%. Headline huge in the top 40%, 1–3 lines, accent word colored. Nothing else. |
| `comparison` | two named options; numbers per option; `الأعلى` / `الأذكى` / `VS` | Two horizontal bands (top = option A, bottom = option B) split by a thin accent divider line carrying the one-line verdict if supplied. Each band: object on one side, name + sub-line + 2–3 large numbers with small unit labels on the other. Warning color on the "higher" band, positive color on the "smarter" band. Matches `client-approved-layout.jpg`. |
| `list` | bullets / numbered items; 3–8 short items | Headline top. Items as a clean vertical stack with generous line height; each item one line, accent tick or number. One supporting object small at a corner or faded behind. |
| `explainer` | paragraph(s); `يعني` / `لأن` / `ازاي`; ingredient callouts | Headline top 25%. Body split into 2–4 modular blocks with clear separation; a single object anchors one side. Callouts connected by thin lines when naming components. |
| `stat` | one dominant number or % | The number is the hero at 30–40% height, unit small; one line of context below; object subordinate. |
| `winner-cta` | `الفائز` / `WINNER` / trophy / `احفظ` / `شير` | Single centered hero object with a restrained accent ring; headline above; short evidence list below; CTA line strongest at the bottom. |

Rules
- Dense copy never gets smaller than phone-readable; split into modules instead.
- Latin technical terms (`Pre-workout`, `Bioavailability`) render as isolated LTR tokens on their own line or with clear spacing; never reorder them inside Arabic lines.
- Score / footer lines (`Coffee: 2 ☕`) sit at the same bottom corner on every slide of a set.
- Same logo position, margins, lighting, and line system across all slides of a set.

## Reviewed gold assignments

Passed structural assignments:

- a dot at the break of a line chart;
- the tip of a forking road;
- one rung of a stepladder;
- a band marking a missing level on a tank.

Failed assignments:

- a whole balloon;
- a whole staircase;
- a whole organ.

Gold is always a small part of the named object. If a scene line makes the
object itself gold, rewrite the scene before prompt construction.
