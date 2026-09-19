# Design — parallel direct-production carousel skill

Date: 2026-09-17. Status: approved.

## Goal
User supplies identity + final slide copy. Skill converts to per-slide prompts, generates all slides in parallel after an explicit approval gate, exports to the exact size declared by `job.size.deliver`, saves to `~/Downloads/DC-<ID>-<slug>-<stamp>/`, validates mechanically, then reports the path. No AI visual review. Learns from user feedback. Self-updates from a public repo.

## Decisions
- Runtime: Codex CLI / app. Skill installed at `~/.codex/skills/diet-cheat-carousel-workflow` as a git clone.
- Parallelism: `scripts/generate.py` spawns one `codex exec --full-auto --ephemeral -i <logo> -i <example>` worker per slide, all at once (thread per worker). Guaranteed concurrency, no API key.
- Copy lock: on-image text verbatim. Intelligence only in composition / object / hierarchy choice.
- Learning: structured lesson blocks. `learnings/shared/lessons.md` in git (maintainer-curated), `learnings/local/lessons.md` gitignored. Every run injects active rules into the shared contract. Feedback → `learn.py add`. Maintainer → `learn.py promote` → commit → push.
- Repo scope: skill only at repo root. ChatGPT GPT path dropped (cannot write Downloads, pull git, or guarantee parallel).
- Export: macOS `sips`, centered whole-raster crop + resize to `job.size.deliver`, followed by deterministic near-background flattening and mechanical validation.
- Regenerate: `--only N --output-dir <same>`; previous files to `history/`.

## Components
| Unit | Does | Depends on |
|---|---|---|
| `SKILL.md` | agent flow, commands, hard rules | references |
| `scripts/generate.py` | job.json → workers → export → checks → manifest/REVIEW/run log | codex, sips, python3 |
| `scripts/learn.py` | add / list / retire / promote / runs | lesson files |
| `scripts/update.sh` | ff-only pull, changelog, active rules | git |
| `install.sh` | clone into CODEX_HOME/skills, checks | git, codex |
| `references/*` | identity, compositions, prompt contract, workflow, learning | — |

## Data flow
brief → (agent) job.json → generate.py → `source/*.png` → sips → `slides/*.png` + manifest.json + REVIEW.md → user review → feedback → learn.py → next job.json.

## Error handling
- Worker: timeout 900 s, 2 attempts on transport/tool failure only. `failed` status reported with log path.
- Export failure → `export-failed`, source kept.
- update.sh refuses to pull over local tracked modifications.
- learn.py validates identity/status/fields; malformed blocks warned and skipped.

## Testing
- `generate.py --dry-run` on a 2-slide job: prompts written, no codex calls.
- Historical 1.0 test fixture: two workers started within the same second and both files landed at the then-job's declared `1080x1440`. This is evidence, not a current size rule.
- `learn.py add/list/retire/promote` round trip.
- `update.sh` on a clean clone.
