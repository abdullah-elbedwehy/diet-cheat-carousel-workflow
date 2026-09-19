# Parallel dispatch investigation — 2026-09-19

## Phase 1 — system layers and serialization points

Recorded before timing experiments or implementation changes.

| Layer | What it does | How it could serialize work |
|---|---|---|
| Calling/outer agent | Chooses whether to invoke `scripts/generate.py` or generate images through its own tools | It can bypass the script entirely or invoke one image-generation call at a time |
| Python dispatcher | Builds one `Worker` and one thread per selected slide; the default semaphore size equals the worker count | An explicit `--concurrency N`, a semaphore bug, thread launch order, or blocking work before thread start could throttle dispatch |
| Worker subprocess | Each worker calls `subprocess.run(codex exec --ephemeral ...)` | Process creation may contend on shared files, environment state, or OS resources |
| Codex CLI session | Loads config, plugins, skills, credentials, and creates one ephemeral Codex session | Shared `CODEX_HOME` state, database/cache locks, auth/token refresh, plugin initialization, or an internal local queue could serialize progress |
| Image tool in each session | Performs the single built-in Imagegen call and writes under `$CODEX_HOME/generated_images/...` | Tool calls may be queued per account, per host, per session family, or by a shared usage/rate limiter |
| Upstream image service/API | Executes image generation | Account/model concurrency limits, capacity queues, rate limits, or request scheduling can cap real generation concurrency even when local sessions overlap |

## Baseline code facts

- Canonical checkout: `/Users/abdullah/Downloads/diet-cheat-carousel-workflow`
- Baseline branch/HEAD: `main` at `9ad8e064880e414fa68e8ba31cb91f52027f4cbd`
- Baseline version: `1.0.1`
- Default dispatcher creates one thread per selected slide.
- Default semaphore limit is `len(workers)` when `--concurrency` is omitted.
- Each worker uses blocking `subprocess.run`, but each call occurs in a separate Python thread.
- Baseline artifacts do not store worker start/completion timestamps or the effective concurrency limit in `manifest.json`.
- Baseline `REVIEW.md` does not state dispatch timing.

## Hypotheses to test

1. Recent runs bypassed `scripts/generate.py`.
2. The Python dispatcher throttled or serialized worker starts.
3. `codex exec --ephemeral` sessions serialize locally through shared state.
4. Codex sessions overlap, but Imagegen calls are queued downstream.
5. A real upstream concurrency ceiling exists below the requested slide count.

## Phase 2 — measurements

### Artifact audit

- Search scope: `/Users/abdullah/Downloads`, through five directory levels, for `DC-*`, `manifest.json`, and `prompts.md`.
- Canonical `~/Downloads/DC-*` run folders found: **0**.
- Therefore no recent run can be shown to have used this repository's `scripts/generate.py`. The expected `job.json`, `prompts.md`, `manifest.json`, `source/`, and `logs/` artifact set is absent.
- Before this investigation, the installed skill link `~/.codex/skills/diet-cheat-carousel-workflow` targeted the missing directory `/Users/abdullah/Downloads/diet-cheat-carousel-workflow`. That made the canonical runner unavailable to the outer agent.

### Python and command-line behavior

- Source inspection: with no explicit `--concurrency`, `limit = len(workers)`, one thread is created per worker, every thread is started before any thread is joined, and each thread runs one blocking subprocess independently.
- No evidence of a GIL-bound critical section exists: the work is external subprocess I/O.
- No recent canonical command exists from which an explicit `--concurrency` value could be recovered, because the canonical runner was not used.
- Separate environment finding: `/opt/homebrew/bin/codex` was version `0.141.0` and failed against the configured `gpt-5.6-sol`; `/Users/abdullah/.local/bin/codex` was `0.144.3` and succeeded. This is a CLI-selection failure risk, not a serialization mechanism.

### Eight concurrent `codex exec` reproduction

Eight independent `codex exec --ephemeral` calls used Codex CLI `0.144.3`, separate work directories, and one trivial response each.

- Process start spread: **0.015150 seconds**.
- Successful sessions: **8/8**.
- All eight started before the first completed: **yes**.
- Completion spread: **9.224661 seconds**.
- Observed local Codex-session concurrency ceiling: **at least 8**.
- No session lock, rate limit, or serialized local queue appeared in the successful reproduction.

### Eight concurrent Imagegen reproduction from the prior real carousel run

The prior `first-week-fatigue` task used eight separate Codex/Imagegen workers and retained `logs-v2/batch-events.jsonl` plus the source rasters.

| Round | Worker start spread | Worker completion spread | Batch wall time | Source-file mtime spread | All started before first finish |
|---|---:|---:|---:|---:|---|
| Attempt 1 | `0.012522s` | `71.961551s` | `186.895887s` | `64.157s` | Yes |
| Attempt 2 | `0.014917s` | `59.363993s` | `187.162010s` | `52.738s` | Yes |

All eight prompts were written within `0.000577s`. Eight full image calls completed inside roughly three minutes per round. Sequential image execution would require approximately eight individual generation durations, not one batch duration with a 53–64 second completion spread. The observed Imagegen concurrency ceiling is therefore **at least 8** on this account and host at the time measured. Different completion timestamps are normal parallel-task variance, not proof of serialized dispatch.

### Hypothesis table

| Hypothesis | What was measured | Result |
|---|---|---|
| Outer agent bypassed the script | Zero canonical `DC-*` artifact sets; installed skill target was missing | **Ruled in** |
| Python threading serialized starts | Source starts every thread before joins; successful 8-session reproduction started within `0.015150s` | Ruled out |
| `--concurrency` throttled the recent run | No canonical invocation/artifacts exist; default source limit equals worker count | Ruled out for the code path; not applicable to the bypassed run |
| Shared Codex session state serialized workers | 8/8 current CLI sessions succeeded concurrently; no lock or queue error | Ruled out up to eight sessions |
| Imagegen serialized calls | Real 8-image rounds completed in about `187s`, with all workers already active | Ruled out up to eight image calls |
| Upstream ceiling below eight | Eight real image workers overlapped | Ruled out at the measured time; ceiling above eight not tested |

## Root cause

**The image-generation path bypassed the repository runner.** The canonical installed-skill link pointed at a missing checkout, and recent outputs lack every artifact that `generate.py` necessarily writes. Prompt wording could not fix this because the code responsible for parallel dispatch was never reached.

Confidence: **high (0.97)**. The artifact absence and broken target prove the bypass. The independent Codex and Imagegen measurements rule out serialization in the tested eight-way path.

## Phase 3 — option evaluation

Score: `5` directly solves the proved root cause; `1` does not.

| Option | Score | Addresses proved cause? | Cost and risk | Does not solve |
|---|---:|---|---|---|
| A. Make bypass impossible | **5** | Yes. Require the runner and fail completion when its artifact/proof set is absent | Small skill, manifest, verifier, and test changes | Cannot physically prevent a user from invoking another tool outside the skill; it prevents that path from being reported as a valid workflow run |
| B. Replace threads with processes | 1 | No. Threads launch external processes concurrently and measured starts are already sub-20ms | More complexity and cross-process state handling | Outer-agent bypass; upstream limits |
| C. Isolate session environments | 1 | No. Eight shared-account sessions succeeded concurrently | Auth/config duplication and fragile temporary homes | Outer-agent bypass; Imagegen account limits |
| D. Call the image API directly | 2 | No. It would remove the nested layer, but that layer is not the bottleneck | New API-key/auth handling, cost surface, prompt plumbing, loss of built-in skill behavior | Agent bypass unless the skill still enforces the script; account limits may remain |
| E. Accept a lower ceiling | 1 | No lower ceiling was measured; observed capacity is at least eight | Would unnecessarily slow valid runs and misdocument the system | Outer-agent bypass |
| F. Batch differently | 1 | No. Eight calls already overlap, and combining slides violates one-slide-one-image | Breaks copy isolation and regeneration semantics | Outer-agent bypass |

### Selected fix

Choose **A plus permanent dispatch observability**:

1. Keep the proven thread/subprocess architecture.
2. Make `scripts/generate.py` the only valid production path in `SKILL.md`.
3. Write start/completion timestamps and the effective concurrency limit into `manifest.json`.
4. Write append-only worker events under `logs/batch-events.jsonl`.
5. Put the worker count, start spread, and simultaneous verdict at the top of `REVIEW.md`.
6. Add a post-run verifier that fails when required artifacts are absent or a nominally full-parallel run exceeds a `2.0s` start-spread threshold.

The `2.0s` threshold is intentionally much looser than the measured `0.015150s`: it tolerates ordinary process-start variance while still detecting sequential or wave-based launch behavior before a run can be reported as valid.
