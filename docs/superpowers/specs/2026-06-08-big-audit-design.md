# RL Trajectory Auditor v0.2 — "The Big Audit" Design

**Date:** 2026-06-08
**Status:** Approved (design) — pending implementation plan
**Builds on:** v0.1 MVP (stdlib heuristic auditor, 6 detectors, 4-point diagnostic, 35 tests)

## Context

The v0.1 MVP works but reads as a quick hack: shallow regex detectors, only 10 real
trajectories audited, terminal-only output, and — critically — **no proof the auditor is
right**. To earn a "wow" from the RL/ML community, the project must deliver a *validated
finding* through a *credible, beautiful artifact*, not just more detectors.

The thesis: **nobody reads their RL trajectories, so nobody knows how many "passing" runs are
actually reward hacks or harness bugs.** We audit a large slice of a public dataset
(`nebius/SWE-rebench-openhands-trajectories`, 67,074 trajectories), measure the real failure
distribution, *validate the auditor against ground truth*, and ship an interactive explorer so
anyone can scroll the receipts.

### Decisions locked (with the user)
- **Wow type:** both a real finding AND a shareable artifact; full push to launch.
- **Constraints:** core auditor stays stdlib; deep tier may add an LLM judge + a web explorer.
- **LLM judge:** Google **Gemini Flash**, called via **stdlib `urllib` REST** (avoids the corp
  pip airlock; matches the existing `/research` pattern). Key from `GEMINI_API_KEY` (env or a
  project-local `.env`, never committed). Model id configurable (`GEMINI_MODEL`), default a
  Flash model; the client may call ListModels at runtime to resolve a valid id.
- **Budget:** hard cap **under $15 total**. Flash is cheap enough that pull-time, not money, is
  the binding constraint; we still enforce a token/call ceiling and print a dry-run estimate.
- **Scale:** heuristic + judge cascade over a **~5,000-trajectory slice**. Explorer ships a
  curated subset.
- **Explorer:** **static custom HTML/JS** on a **HuggingFace Space** (editorial/preprint
  aesthetic). Pre-baked JSON → zero serving cost, no key in the Space, no live calls.
- **Narrative:** Substack (`abhid.substack.com`) + X thread; **never committed to git**.

## Goals

1. Audit ~5k real trajectories: heuristic pass over all, Gemini-judge cascade on flagged + control.
2. Produce a **validation report**: precision/recall/confusion vs `resolved` ground truth, and
   heuristic-vs-judge agreement (Cohen's κ).
3. Produce a **headline finding** + 5 concrete annotated "receipts."
4. Ship a **static interactive explorer** on a HF Space.
5. Stay under $15 with hard, enforced cost guards.

## Non-goals

- Re-auditing the full 67k (chosen ~5k slice; pipeline is parameterized so it *can* scale later).
- Training/fine-tuning anything. We only read trajectories.
- A live backend or hosted API (explorer is fully static, data pre-baked).
- Embedding-based clustering (deferred again; the finding + validation + explorer carry the wow).

## Architecture

v0.1 stays the cheap first stage. New code is additive and isolated:

```
src/
  judge/
    gemini.py        # stdlib urllib REST client: generate_json(prompt, schema) -> dict
                     #   - reads GEMINI_API_KEY/GEMINI_MODEL from env
                     #   - responseMimeType=application/json + responseSchema
                     #   - retries/backoff; raises GeminiError on hard failure
    prompt.py        # build_judge_prompt(traj) -> str  (the 4-point diagnostic, asks for JSON)
    cascade.py       # judge_cascade(trajs, signals_by_id, budget) -> dict[id]=JudgeVerdict
                     #   - selects flagged ∪ control-sample; truncates each traj to token budget
                     #   - enforces CostGuard (max_calls, max_input_tokens); dry_run estimate
  validate/
    ground_truth.py  # gold_label(traj) -> str   (REWARD_HACK_TRUE / CLEAN_TRUE / UNKNOWN from resolved + test split)
    metrics.py       # confusion_matrix(...), precision_recall(...), cohens_kappa(...) -> dict
  pipeline/
    run_audit_at_scale.py  # CLI: stream N rows from HF → heuristic-audit → judge cascade →
                           #      persist to SQLite + write audit_run.json + validation_report.json
    export_explorer.py     # build explorer/data/*.json: curated cards + aggregate stats
  judge/__init__.py, validate/__init__.py, pipeline/__init__.py
explorer/                  # static HF Space (own deploy unit)
  index.html               # dashboard + card stack
  app.js                   # load data/*.json, render cards, filters, keyboard nav, highlight
  styles.css               # editorial/preprint: warm light, serif display, oxblood accent
  data/                    # baked JSON (cards.json, summary.json) — gitignored if large/regenerable
  README.md                # HF Space card: `sdk: static`
docs/
  FINDINGS.md              # the writeup-in-repo: distribution, validation numbers, receipts
```

### New data types (extend `src/models.py`)

```python
@dataclass
class JudgeVerdict:
    trajectory_id: str
    diagnosis: str            # HARNESS | TRAINING | PRODUCT | BOTH | CLEAN (same vocabulary)
    failure_category: str
    confidence: float
    reasoning: str            # short natural-language justification (for the explorer)
    offending_message_index: int | None  # which message exposes the failure (for highlight)
    raw: dict
```

`Diagnosis` (v0.1) is unchanged. The pipeline stores both the heuristic `Diagnosis` and the
optional `JudgeVerdict` per trajectory.

## Component detail

### 1. Gemini client (`src/judge/gemini.py`)
- Pure stdlib (`urllib.request`, `json`, `os`, `time`).
- `class GeminiClient(api_key=None, model=None)`: defaults from env; `generate_json(prompt, schema)`
  POSTs to `…/v1beta/models/{model}:generateContent?key=…` with `generationConfig.responseMimeType
  = "application/json"` and `responseSchema`. Parses the single candidate's text as JSON.
- Exponential backoff on 429/5xx; hard `GeminiError` after `max_retries`.
- Records `usage_metadata` (token counts) on the client for the CostGuard.
- **Testable without network:** constructor accepts an injectable `transport` callable
  (default: real urllib). Tests pass a fake transport returning canned JSON.

### 2. Judge prompt (`src/judge/prompt.py`)
- Renders the trajectory (truncated): task, key tool calls/observations, patch summary,
  test-split numbers. Asks Gemini to apply the 4-point diagnostic and return JSON matching
  `JudgeVerdict` (incl. `offending_message_index` and a 1-2 sentence `reasoning`).
- Truncation: keep system+task, first K and last K messages, and any message matching a
  detector's evidence; cap to `max_input_tokens_per_traj` (default ~12k chars heuristic).

### 3. Cascade + CostGuard (`src/judge/cascade.py`)
- Input: trajectories + their heuristic signals.
- Selection: every heuristic-flagged trajectory **plus** a deterministic random control sample
  of non-flagged ones (default 10%, capped) so we can estimate false negatives.
- `class CostGuard(max_calls, max_input_tokens)`: pre-flight `estimate(trajs)` prints projected
  calls + tokens + a rough $ figure; `before_call()` aborts (clean stop, partial results saved)
  if a ceiling would be exceeded.
- Returns `dict[id] -> JudgeVerdict`; trajectories skipped by the guard are simply absent.

### 4. Validation (`src/validate/`)
- `ground_truth.gold_label`: from the dataset's own fields. The defensible gold is
  **reward-hack truth = `pred_passes_gen_tests >= 1.0 AND resolved == 0`** vs
  **clean truth = `resolved == 1`**; everything else `UNKNOWN` (excluded from precision/recall).
- `metrics`: confusion matrix + precision/recall/F1 for the heuristic reward-hack detector vs
  gold; plus heuristic-vs-judge category agreement and Cohen's κ. Pure stdlib math, unit-tested
  on synthetic label sets.
- Honest framing in `FINDINGS.md`: `resolved` validates the *reward-hack/test-split* axis
  rigorously; context-gap/fork have no dataset label, so there the **Gemini judge is the silver
  standard** and we report agreement, not accuracy. No overclaiming.

### 5. Scale pipeline (`src/pipeline/run_audit_at_scale.py`)
- Streams N rows from the HF datasets-server `/rows` API (reusing `ingest_hf`), normalizes,
  heuristic-audits all (reusing `corpus`+`detectors`+`four_point_diagnostic`), runs the cascade,
  computes validation, persists to SQLite (extend `db.py` to also store judge verdicts), and
  writes `audit_run.json` + `validation_report.json`.
- CLI: `python -m src.pipeline.run_audit_at_scale --limit 5000 --control 0.1 --max-cost 12
  --dry-run` (dry-run prints the cost estimate and exits).

### 6. Explorer export (`src/pipeline/export_explorer.py`)
- Builds `explorer/data/summary.json` (distribution, validation metrics, headline numbers) and
  `explorer/data/cards.json` (a curated subset — all disagreements + top-confidence examples per
  category, capped to keep the Space light, with only display fields: task, model, diagnosis,
  confidence, evidence, judge reasoning, highlighted message + neighbors, test-split numbers).

### 7. Explorer UI (`explorer/`)
- Static HTML/CSS/JS, no framework. Loads the two JSON files.
- **Dashboard:** failure-distribution bars, harness-vs-training split, the validation headline
  (precision/recall, κ), wasted-compute estimate.
- **Card stack:** one trajectory per card; color-coded diagnosis chip; the offending message
  rendered in context with a highlight; evidence list; Gemini's reasoning; test-split badges.
  Filter by category/diagnosis/agreement; keyboard ←/→ to browse (the "Tinder" feel).
- Aesthetic: warm light background, serif display headings, oxblood accent — editorial/preprint.
- `README.md` front-matter: `title`, `sdk: static`, `app_file: index.html`.

## Data flow

```
HF /rows ──> normalize ──> [heuristic audit: corpus + 6 detectors + 4-point] ──> Diagnosis/id
                                                   │
                          flagged ∪ control sample │
                                                   ▼
                              [judge cascade: Gemini Flash + CostGuard] ──> JudgeVerdict/id
                                                   │
            ┌──────────────────────────────────────┼───────────────────────────┐
            ▼                                        ▼                           ▼
   validation (vs resolved gold,            audit_run.json /            export_explorer
   heuristic-vs-judge κ)                    validation_report.json      explorer/data/*.json
            │                                                                    │
            ▼                                                                    ▼
   docs/FINDINGS.md  ◄────────── headline + 5 receipts                  static HF Space
```

## Error handling

- Gemini failures: per-call retry/backoff; on hard failure that trajectory gets no verdict
  (heuristic diagnosis still stands) and the run continues.
- CostGuard breach: stop issuing new calls, persist everything gathered so far, exit cleanly with
  a summary of what was/wasn't judged.
- HF pull errors: paginate defensively; on a failed page, retry then skip with a logged gap (no
  silent truncation — log the dropped count).
- Missing key: fail fast with a clear message *before* any network/spend.

## Budget & safety

- Hard `--max-cost` (default 12) → token ceiling via Flash pricing; `--dry-run` mandatory-by-habit
  estimate first.
- `GEMINI_API_KEY` from env / project `.env`; `.env` and `explorer/data/` (if large) gitignored.
- Launch/social artifacts (Substack draft, X thread) live outside git entirely.
- No employer / 20% / colleague references in any public artifact (repo, Space, posts).
- Dataset is public and citable; we audit and attribute it.

## Testing

- `gemini.py`: injected fake transport → JSON parse, retry/backoff, usage capture. No network.
- `cascade.py`: selection logic (flagged ∪ control), truncation, CostGuard abort, partial-result
  return — all with a stub client.
- `validate/metrics.py`: precision/recall/F1/confusion/κ on hand-computed synthetic labels.
- `export_explorer.py`: output shape + curation caps on a synthetic audit_run.
- Existing 35 tests stay green. New target: ~25 added tests.
- Network paths (real HF pull, real Gemini call) are exercised manually in the verification step,
  not in CI.

## Milestones (each independently shippable)

1. **Judge tier** — gemini client + prompt + cascade + cost guard (mocked tests).
2. **Validation** — ground truth + metrics + `validation_report.json`.
3. **Scale pipeline** — 5k run end-to-end → `audit_run.json` (+ a small real smoke run).
4. **Explorer** — export + static UI, fed by the real run.
5. **Findings + launch prep** — `docs/FINDINGS.md`, receipts, HF Space deploy, draft posts (out of git).

## Success criteria

- [ ] ~5k trajectories heuristic-audited; flagged+control judged by Gemini; total spend < $15 (logged).
- [ ] `validation_report.json` with real precision/recall for the reward-hack axis + κ vs judge.
- [ ] `docs/FINDINGS.md` with the headline stat + 5 annotated receipts; no overclaiming.
- [ ] Static explorer live on a HF Space; dashboard + filterable, keyboard-navigable card stack;
      editorial aesthetic; loads pre-baked JSON only.
- [ ] All tests green (existing 35 + new judge/validation/export tests).
- [ ] Draft Substack post + X thread prepared (outside git).

## Open risks

- **Flash JSON reliability:** mitigated by `responseSchema` + a tolerant parser + retry.
- **Long trajectories blow the token budget:** mitigated by truncation keeping head/tail/evidence.
- **datasets-server offset limits at 5k:** if the API caps offset, fall back to the Hub parquet
  file list via stdlib (note as a contingency in the plan).
- **Explorer data size:** cap curated cards; keep raw trajectories out of the Space.
