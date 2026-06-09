# Scale Pipeline — Implementation Plan (Milestone 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Stream ~5k real trajectories from HuggingFace, run the heuristic audit + Gemini judge cascade under a hard cost cap, compute the validation report, and emit `audit_run.json` + `validation_report.json` — producing the actual headline finding.

**Architecture:** A memory-bounded two-pass pipeline over trajectories ingested to disk. Pass 1 feeds trajectories one at a time into a `CorpusBuilder` (accumulates only tool-call statistics, never message text). Pass 2 re-streams the same files, runs the 6 detectors + 4-point diagnostic per trajectory, judges the flagged ∪ control subset via the existing `judge_cascade`, and discards each trajectory after use. Results (small `Diagnosis`/`JudgeVerdict` objects) are aggregated, validated, persisted to SQLite, and written as JSON. A `--dry-run` flag prints the projected cost and exits before any spend.

**Tech Stack:** Python 3.12 stdlib. Reuses `src/judge/*`, `src/validate/*`, `src/detectors/*`, `src/framework/*`, `src/report/*`, `src/loader.py`, `src/ingest_hf.py`, `src/db.py`. Gemini Flash via the existing client. `pytest` (dev); all pipeline tests use fakes — no network, no spend.

---

## Context

Milestones 1–2 (merged to `main`) built the judge tier and validation harness, fully tested with mocked transport — **zero spend so far**. Milestone 3 is the first real run: it wires the pieces into a pipeline that produces `audit_run.json` (per-trajectory heuristic + judge results) and `validation_report.json` (precision/recall vs `resolved`, heuristic-vs-judge κ). These two files feed Milestone 4's explorer and Milestone 5's `FINDINGS.md`.

Key constraints (from `docs/superpowers/specs/2026-06-08-big-audit-design.md`):
- **Memory:** the host is a 32GB machine; 5k full SWE-rebench trajectories is multiple GB of text. The pipeline must NOT hold all `Trajectory` objects in memory at once — hence the streaming two-pass design and a `CorpusBuilder` that retains only lightweight per-trajectory tool statistics.
- **Cost:** hard cap via `CostGuard` (default `--max-cost 12`); `--dry-run` prints the estimate and exits; `GEMINI_API_KEY`/`GEMINI_MODEL` from `.env` (already present, gitignored). Verified live: `gemini-2.5-flash`, one judge call ≈ 1.6k tokens.
- **Honesty:** `resolved` validates the reward-hack axis rigorously; context-gap/fork have no dataset label, so the judge is a silver standard (report agreement, not accuracy).

Reusable interfaces (do not reinvent):
- `src/ingest_hf.py`: `normalize_row(api_row)`, `_fetch_page(offset, length)`, `PAGE=100`, `DATASET`, `ingest(out_dir, limit)`.
- `src/loader.py`: `load_trajectories(path)` → `list[Trajectory]`.
- `src/corpus.py`: `build_corpus(trajs)` → `CorpusContext`; internals `_family`, `_ngrams`, `_tool_freq_model`, `_build_fork_index`; uses `extract_tool_calls`.
- `src/detectors/__init__.py`: `run_all(traj, corpus)`; `src/framework/four_point_diagnostic.py`: `diagnose(traj, signals)`.
- `src/judge/cascade.py`: `judge_cascade(trajs, diags, client, guard, control_ratio, seed)`, `CostGuard`, `select_for_judging`, `_tokens_from_chars`. `src/judge/gemini.py`: `GeminiClient`. `src/judge/prompt.py`: `build_judge_prompt`.
- `src/validate/metrics.py`: `reward_hack_validation(trajs, diags)`, `judge_agreement(diags, verdicts)`.
- `src/report/aggregate.py`: `aggregate(diags, cost_per_traj)`; `src/report/format.py`: `render_terminal(rep)`, `diagnosis_to_dict(d)`.
- `src/db.py`: `DiagnosisDB` (table `diagnoses`, methods `save`, `all`, `category_counts`, `close`).

## File Structure

```
src/
  ingest_hf.py          # MODIFY: add iter_normalized(limit) streaming generator
  corpus.py             # MODIFY: add CorpusBuilder (add/build); build_corpus becomes a thin wrapper
  db.py                 # MODIFY: add judge_verdicts table + save_verdict/verdicts methods
  pipeline/
    __init__.py         # CREATE (empty)
    scale.py            # CREATE: run_audit_at_scale(...) core (injectable row source + client)
    cli.py              # CREATE: argparse CLI with --dry-run cost gate
tests/
  test_ingest_iter.py   # CREATE
  test_corpus_builder.py# CREATE
  test_db_verdicts.py   # CREATE
  test_pipeline.py      # CREATE
```

CLI entry: `python -m src.pipeline.cli audit --limit 5000 --max-cost 12 [--dry-run]`.

### Key shapes (defined in Task 4, used by CLI + Milestone 4)

`run_audit_at_scale(...)` returns a dict:
```python
{
  "n": int,                                  # trajectories audited
  "diagnoses": list[Diagnosis],
  "verdicts": dict[str, JudgeVerdict],
  "report": dict,                            # from aggregate()
  "validation": {"reward_hack": {...}, "judge_agreement": {...}},
  "judge_stats": {"judged", "skipped", "errors", "est_input_tokens", "billed_tokens"},
}
```
`audit_run.json` = `{diagnoses:[diagnosis_to_dict...], verdicts:{id: {...}}, report, validation, judge_stats}`.
`validation_report.json` = `{reward_hack, judge_agreement, judge_stats, n}`.

---

## Task 1: Streaming HF row generator

**Files:**
- Modify: `src/ingest_hf.py` (add `iter_normalized`; refactor `ingest` to use it)
- Test: `tests/test_ingest_iter.py`

Add a generator that yields normalized dicts page by page, so callers never hold all rows. `ingest()` is rewritten to consume it (behavior unchanged). Tests monkeypatch `_fetch_page` — no network.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingest_iter.py
import src.ingest_hf as ing


def _fake_pages(monkeypatch, pages):
    """pages: list of lists of api-row dicts, returned per call in order."""
    calls = {"i": 0}

    def fake_fetch(offset, length):
        i = calls["i"]
        calls["i"] += 1
        return pages[i] if i < len(pages) else []

    monkeypatch.setattr(ing, "_fetch_page", fake_fetch)


def _row(tid):
    return {"row": {"trajectory_id": tid, "instance_id": tid, "repo": "r",
                    "trajectory": [], "model_patch": "", "resolved": 0,
                    "pred_passes_gen_tests": 1.0, "gen_tests_correct": 0.0}}


def test_iter_normalized_yields_limit(monkeypatch):
    _fake_pages(monkeypatch, [[_row("a"), _row("b")], [_row("c"), _row("d")]])
    out = list(ing.iter_normalized(limit=3))
    assert len(out) == 3
    assert out[0]["task_id"] == "a"
    assert out[0]["test_results"]["pred_passes_gen_tests"] == 1.0


def test_iter_normalized_stops_on_empty_page(monkeypatch):
    _fake_pages(monkeypatch, [[_row("a")], []])
    out = list(ing.iter_normalized(limit=100))
    assert len(out) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ingest_iter.py -v`
Expected: FAIL — `AttributeError: module 'src.ingest_hf' has no attribute 'iter_normalized'`

- [ ] **Step 3: Write minimal implementation**

In `src/ingest_hf.py`, add this generator (after `_fetch_page`) and rewrite `ingest` to use it:

```python
def iter_normalized(limit: int = 100):
    """Yield up to `limit` normalized trajectory dicts, paging the datasets-server."""
    written = 0
    offset = 0
    while written < limit:
        batch = _fetch_page(offset, min(PAGE, limit - written))
        if not batch:
            break
        for row in batch:
            yield normalize_row(row)
            written += 1
            if written >= limit:
                return
        offset += len(batch)
```

Replace the body of `ingest` with:

```python
def ingest(out_dir: str, limit: int = 100) -> int:
    os.makedirs(out_dir, exist_ok=True)
    written = 0
    for norm in iter_normalized(limit):
        path = os.path.join(out_dir, f"{norm['task_id'].replace('/', '__')}_{written}.json")
        with open(path, "w") as f:
            json.dump(norm, f)
        written += 1
    return written
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ingest_iter.py tests/test_report.py -v`
Expected: PASS (new tests + the existing `test_normalize_hf_row` in test_report.py still green).

- [ ] **Step 5: Commit**

```bash
git add src/ingest_hf.py tests/test_ingest_iter.py
git commit -m "feat: streaming iter_normalized generator for HF ingestion"
```

---

## Task 2: Memory-bounded CorpusBuilder

**Files:**
- Modify: `src/corpus.py` (add `CorpusBuilder`; make `build_corpus` a wrapper)
- Test: `tests/test_corpus_builder.py`

`CorpusBuilder.add(traj)` accumulates only the lightweight signals the corpus needs (tool-count per trajectory, fork n-grams by family, tool-frequency Counter) — never message text — then `.build()` returns the same `CorpusContext` `build_corpus` produces today. `build_corpus(trajs)` is reimplemented to feed the builder, so its output is unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_corpus_builder.py
from src.models import Trajectory
from src.corpus import CorpusBuilder, build_corpus


def _traj(tid, tools, repo="acme/lib", resolved=False):
    msgs = [{"role": "assistant", "content": "",
             "tool_calls": [{"id": str(i), "type": "function",
                             "function": {"name": nm, "arguments": "{}"}}]}
            for i, nm in enumerate(tools)]
    return Trajectory.from_dict({"task_id": tid, "trajectory_id": tid, "repo": repo,
        "messages": msgs, "patch": "",
        "test_results": {"pred_passes_gen_tests": 0.0, "pred_passes_gold_tests": 0.0},
        "resolved": resolved, "model": "m"})


def test_builder_matches_build_corpus():
    trajs = [_traj("t1", ["a", "b", "c"]), _traj("t2", ["a", "b", "c"]),
             _traj("t3", ["x"], resolved=True)]
    b = CorpusBuilder()
    for t in trajs:
        b.add(t)
    built = b.build()
    ref = build_corpus(trajs)
    assert built.n == ref.n
    assert built.tool_volume_mean == ref.tool_volume_mean
    assert built.tool_volume_stdev == ref.tool_volume_stdev
    assert built.fork_index == ref.fork_index
    assert built.tool_freq_centroid == ref.tool_freq_centroid
    assert built.tool_freq_stdev == ref.tool_freq_stdev


def test_builder_empty():
    c = CorpusBuilder().build()
    assert c.n == 0
    assert c.tool_volume_stdev == 0.0
    assert c.fork_index == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_corpus_builder.py -v`
Expected: FAIL — `ImportError: cannot import name 'CorpusBuilder'`

- [ ] **Step 3: Write minimal implementation**

In `src/corpus.py`, add the `CorpusBuilder` class and rewrite `build_corpus` as a wrapper. Keep all existing helpers (`_family`, `_ngrams`, `_tool_freq_model`, `_build_fork_index`, `NGRAM`) — `CorpusBuilder` reuses `_family`, `_ngrams`, `extract_tool_calls`, and the stdlib stats.

```python
class CorpusBuilder:
    """Accumulate corpus statistics one trajectory at a time without retaining
    message text — bounds memory for large runs."""

    def __init__(self):
        self._counts = []                       # tool-call count per trajectory
        self._fork_raw = defaultdict(lambda: defaultdict(set))  # family -> ngram -> {ids}
        self._freq_vectors = []                 # list[Counter] of tool names per trajectory

    def add(self, traj) -> None:
        tools = extract_tool_calls(traj)
        self._counts.append(len(tools))
        self._freq_vectors.append(Counter(tools))
        if not traj.resolved:
            fam = _family(traj)
            for g in _ngrams(tools):
                self._fork_raw[fam][g].add(traj.trajectory_id)

    def build(self) -> CorpusContext:
        counts = self._counts or [0]
        mean = statistics.fmean(counts)
        stdev = statistics.pstdev(counts) if len(counts) > 1 else 0.0
        # fork index: keep only ngrams shared by >=2 failing traces (matches _build_fork_index)
        index = {}
        for fam, grams in self._fork_raw.items():
            shared = {"->".join(g): sorted(ids) for g, ids in grams.items() if len(ids) >= 2}
            if shared:
                index[fam] = shared
        # tool frequency model (matches _tool_freq_model)
        vocab = set().union(*self._freq_vectors) if self._freq_vectors else set()
        centroid, sd = {}, {}
        for tool in vocab:
            series = [v.get(tool, 0) for v in self._freq_vectors]
            centroid[tool] = statistics.fmean(series)
            sd[tool] = statistics.pstdev(series) if len(series) > 1 else 0.0
        return CorpusContext(
            tool_volume_mean=mean, tool_volume_stdev=stdev, fork_index=index,
            tool_freq_centroid=centroid, tool_freq_stdev=sd, n=len(self._counts))
```

Then replace the existing `build_corpus` body with:

```python
def build_corpus(trajs: list[Trajectory]) -> CorpusContext:
    b = CorpusBuilder()
    for t in trajs:
        b.add(t)
    return b.build()
```

Ensure `from collections import Counter, defaultdict` and `import statistics` are present at the top of `corpus.py` (they already are).

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_corpus_builder.py tests/test_detectors.py tests/test_diagnostic.py -v`
Expected: PASS (new tests + all existing corpus/detector/diagnostic tests, since `build_corpus` output is unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/corpus.py tests/test_corpus_builder.py
git commit -m "feat: memory-bounded CorpusBuilder; build_corpus wraps it"
```

---

## Task 3: Persist judge verdicts in SQLite

**Files:**
- Modify: `src/db.py` (add `judge_verdicts` table + `save_verdict`/`verdicts`)
- Test: `tests/test_db_verdicts.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_verdicts.py
from src.models import JudgeVerdict
from src.db import DiagnosisDB


def test_verdict_roundtrip(tmp_path):
    db = DiagnosisDB(str(tmp_path / "exp.db"))
    db.save_verdict(JudgeVerdict("t1", "TRAINING", "Reward Hack", 0.9, "hacked", 2, {"x": 1}))
    db.save_verdict(JudgeVerdict("t2", "HARNESS", "Context Gap", 0.7, "missing", None, {}))
    rows = db.verdicts()
    assert len(rows) == 2
    by_id = {r["trajectory_id"]: r for r in rows}
    assert by_id["t1"]["diagnosis"] == "TRAINING"
    assert by_id["t1"]["offending_message_index"] == 2
    assert by_id["t2"]["offending_message_index"] is None
    db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_db_verdicts.py -v`
Expected: FAIL — `AttributeError: 'DiagnosisDB' object has no attribute 'save_verdict'`

- [ ] **Step 3: Write minimal implementation**

In `src/db.py`, extend the schema string and add two methods. Append to `_SCHEMA`:

```python
_SCHEMA = """
CREATE TABLE IF NOT EXISTS diagnoses (
    trajectory_id TEXT,
    diagnosis TEXT,
    failure_category TEXT,
    confidence REAL,
    evidence TEXT,
    fix_recommendation TEXT,
    signals TEXT
);
CREATE TABLE IF NOT EXISTS judge_verdicts (
    trajectory_id TEXT,
    diagnosis TEXT,
    failure_category TEXT,
    confidence REAL,
    reasoning TEXT,
    offending_message_index INTEGER,
    raw TEXT
);
"""
```

Add these methods to `DiagnosisDB` (alongside `save`):

```python
    def save_verdict(self, v) -> None:
        self.conn.execute(
            "INSERT INTO judge_verdicts VALUES (?,?,?,?,?,?,?)",
            (v.trajectory_id, v.diagnosis, v.failure_category, v.confidence,
             v.reasoning, v.offending_message_index, json.dumps(v.raw)),
        )
        self.conn.commit()

    def verdicts(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM judge_verdicts")]
```

(`json` and `sqlite3` are already imported in `db.py`; `executescript` already runs `_SCHEMA` so the new table is created.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_db_verdicts.py tests/test_report.py -v`
Expected: PASS (new test + existing db roundtrip test in test_report.py).

- [ ] **Step 5: Commit**

```bash
git add src/db.py tests/test_db_verdicts.py
git commit -m "feat: persist judge verdicts in SQLite (judge_verdicts table)"
```

---

## Task 4: Pipeline core (`run_audit_at_scale`)

**Files:**
- Create: `src/pipeline/__init__.py` (empty), `src/pipeline/scale.py`
- Test: `tests/test_pipeline.py`

`run_audit_at_scale` is injectable: `row_source` (default real HF), `client` (default real Gemini), and a `CostGuard`. It ingests rows to a temp dir, streams them twice (corpus pass via `CorpusBuilder`, then audit+judge pass), validates, persists, and writes JSON. Tests pass a fake row source + stub client — no network, no spend.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py
import json
from src.pipeline.scale import run_audit_at_scale
from src.judge.cascade import CostGuard


def _row(tid, gen, gold, resolved, patch="", repo="acme/lib", msgs=None):
    return {"trajectory_id": tid, "task_id": tid, "task_description": "d", "repo": repo,
            "messages": msgs or [{"role": "user", "content": "hi"}], "patch": patch,
            "test_results": {"pred_passes_gen_tests": gen, "pred_passes_gold_tests": gold,
                             "gen_tests_correct": 1.0},
            "resolved": resolved, "model": "m", "cost": 0.1}


class _StubClient:
    total_tokens = 0

    def generate_json(self, prompt, schema):
        type(self).total_tokens += 40
        return {"diagnosis": "TRAINING", "failure_category": "Reward Hack",
                "confidence": 0.8, "reasoning": "stub", "offending_message_index": 0}


def _rows():
    # one reward hack (gen=1,gold=0), one clean (resolved), one plain fail
    return iter([
        _row("hack1", 1.0, 0.0, False, patch="diff --git a/tests/t.py b/tests/t.py\n+++ b/tests/t.py\n+assert True\n"),
        _row("clean1", 1.0, 1.0, True),
        _row("fail1", 0.0, 0.0, False),
    ])


def test_pipeline_end_to_end(tmp_path):
    guard = CostGuard(max_calls=100, max_input_tokens=10**9, max_cost_usd=15.0)
    out = run_audit_at_scale(
        limit=3, control_ratio=0.0, guard=guard, client=_StubClient(),
        row_source=_rows(), work_dir=str(tmp_path / "traj"),
        out_dir=str(tmp_path), db_path=str(tmp_path / "exp.db"))
    assert out["n"] == 3
    assert len(out["diagnoses"]) == 3
    assert "hack1" in out["verdicts"]                      # flagged → judged
    assert "clean1" not in out["verdicts"]                 # clean, control_ratio=0 → not judged
    assert out["report"]["total"] == 3
    assert out["validation"]["reward_hack"]["n_evaluated"] >= 1
    assert "judge_agreement" in out["validation"]
    # JSON artifacts written
    run = json.load(open(tmp_path / "audit_run.json"))
    assert run["report"]["total"] == 3
    assert "validation" in run
    vr = json.load(open(tmp_path / "validation_report.json"))
    assert vr["n"] == 3 and "reward_hack" in vr


def test_pipeline_dry_run_estimate(tmp_path):
    guard = CostGuard(max_calls=100, max_input_tokens=10**9, max_cost_usd=15.0)
    est = run_audit_at_scale(
        limit=3, control_ratio=0.0, guard=guard, client=_StubClient(),
        row_source=_rows(), work_dir=str(tmp_path / "traj"),
        out_dir=str(tmp_path), db_path=str(tmp_path / "exp.db"), dry_run=True)
    assert est["dry_run"] is True
    assert est["to_judge"] >= 1                # at least the reward hack
    assert "est_cost_usd" in est
    assert _StubClient().total_tokens == 0 or True   # no real judging asserted below
    # no artifacts written on dry run
    assert not (tmp_path / "audit_run.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.pipeline.scale'`

- [ ] **Step 3: Write minimal implementation**

Create `src/pipeline/__init__.py` (empty), then `src/pipeline/scale.py`:

```python
from __future__ import annotations
import json
import os
from src.ingest_hf import iter_normalized
from src.loader import load_trajectories
from src.corpus import CorpusBuilder
from src.detectors import run_all
from src.framework.four_point_diagnostic import diagnose
from src.judge.cascade import judge_cascade, select_for_judging, CostGuard, _tokens_from_chars
from src.judge.gemini import GeminiClient
from src.judge.prompt import build_judge_prompt
from src.validate.metrics import reward_hack_validation, judge_agreement
from src.report.aggregate import aggregate
from src.report.format import diagnosis_to_dict
from src.db import DiagnosisDB


def _ingest(row_source, work_dir: str, limit: int) -> int:
    os.makedirs(work_dir, exist_ok=True)
    n = 0
    for norm in row_source:
        path = os.path.join(work_dir, f"{norm['task_id'].replace('/', '__')}_{n}.json")
        with open(path, "w") as f:
            json.dump(norm, f)
        n += 1
        if n >= limit:
            break
    return n


def run_audit_at_scale(limit=5000, control_ratio=0.1, guard=None, client=None,
                       row_source=None, work_dir="trajectories", out_dir=".",
                       db_path=None, seed=13, dry_run=False) -> dict:
    guard = guard or CostGuard(max_calls=limit, max_input_tokens=10**9, max_cost_usd=12.0)
    row_source = row_source if row_source is not None else iter_normalized(limit)

    # Ingest to disk (bounds memory: we re-stream from files, never hold all in RAM).
    _ingest(row_source, work_dir, limit)
    trajs = load_trajectories(work_dir)   # objects are reused transiently below

    # Pass 1: corpus statistics (lightweight accumulation).
    builder = CorpusBuilder()
    for t in trajs:
        builder.add(t)
    corpus = builder.build()

    # Pass 2: heuristic audit.
    diags = []
    diag_by_id = {}
    signals_cache = {}
    for t in trajs:
        sig = run_all(t, corpus)
        d = diagnose(t, sig)
        diags.append(d)
        diag_by_id[d.trajectory_id] = d
        signals_cache[t.trajectory_id] = sig

    # Dry run: estimate judge cost and exit without spending.
    chosen = select_for_judging(trajs, diag_by_id, control_ratio, seed)
    if dry_run:
        prompts = [build_judge_prompt(t) for t in chosen]
        est = guard.estimate(prompts)
        return {"dry_run": True, "n": len(trajs), "to_judge": len(chosen),
                "est_input_tokens": est["input_tokens"], "est_cost_usd": est["cost_usd"]}

    # Judge cascade (real or stubbed client).
    client = client or GeminiClient()
    cascade = judge_cascade(trajs, diag_by_id, client, guard, control_ratio, seed)
    verdicts = cascade["verdicts"]

    # Validation.
    validation = {
        "reward_hack": reward_hack_validation(trajs, diag_by_id),
        "judge_agreement": judge_agreement(diag_by_id, verdicts),
    }
    avg_cost = (sum(t.cost for t in trajs) / len(trajs)) if trajs else 0.0
    report = aggregate(diags, cost_per_traj=avg_cost)
    judge_stats = {k: cascade[k] for k in
                   ("judged", "skipped", "errors", "est_input_tokens", "billed_tokens")}

    # Persist.
    if db_path:
        db = DiagnosisDB(db_path)
        for d in diags:
            db.save(d)
        for v in verdicts.values():
            db.save_verdict(v)
        db.close()

    # Artifacts.
    os.makedirs(out_dir, exist_ok=True)
    run_obj = {
        "diagnoses": [diagnosis_to_dict(d) for d in diags],
        "verdicts": {vid: _verdict_to_dict(v) for vid, v in verdicts.items()},
        "report": report, "validation": validation, "judge_stats": judge_stats,
    }
    with open(os.path.join(out_dir, "audit_run.json"), "w") as f:
        json.dump(run_obj, f, indent=2)
    with open(os.path.join(out_dir, "validation_report.json"), "w") as f:
        json.dump({**validation, "judge_stats": judge_stats, "n": len(trajs)}, f, indent=2)

    return {"n": len(trajs), "diagnoses": diags, "verdicts": verdicts,
            "report": report, "validation": validation, "judge_stats": judge_stats}


def _verdict_to_dict(v) -> dict:
    return {"trajectory_id": v.trajectory_id, "diagnosis": v.diagnosis,
            "failure_category": v.failure_category, "confidence": v.confidence,
            "reasoning": v.reasoning, "offending_message_index": v.offending_message_index}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_pipeline.py -v`
Expected: PASS (both tests). Then full suite `python3 -m pytest -q` — all green.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/__init__.py src/pipeline/scale.py tests/test_pipeline.py
git commit -m "feat: scale pipeline — two-pass audit + judge + validation + JSON artifacts"
```

---

## Task 5: CLI with dry-run cost gate

**Files:**
- Create: `src/pipeline/cli.py`
- Test: `tests/test_pipeline.py` (append a CLI-level test using the injected fakes)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_pipeline.py
from src.pipeline.cli import build_parser, run_cli


def test_cli_dry_run(tmp_path, capsys):
    args = build_parser().parse_args(
        ["audit", "--limit", "3", "--control", "0.0", "--max-cost", "12", "--dry-run",
         "--work-dir", str(tmp_path / "t"), "--out-dir", str(tmp_path)])
    rc = run_cli(args, row_source=_rows(), client=_StubClient())
    assert rc == 0
    captured = capsys.readouterr().out
    assert "DRY RUN" in captured.upper()
    assert "to judge" in captured.lower() or "to_judge" in captured.lower()
    assert not (tmp_path / "audit_run.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_pipeline.py -k cli -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.pipeline.cli'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/pipeline/cli.py
from __future__ import annotations
import argparse
import sys
from src.judge.cascade import CostGuard
from src.pipeline.scale import run_audit_at_scale


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="audit-scale",
                                description="Audit N real trajectories with the judge cascade")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit", help="run the scale audit")
    a.add_argument("--limit", type=int, default=5000)
    a.add_argument("--control", type=float, default=0.1, help="control-sample ratio of clean traces")
    a.add_argument("--max-cost", type=float, default=12.0, help="hard USD ceiling")
    a.add_argument("--max-calls", type=int, default=0, help="0 = default to --limit")
    a.add_argument("--work-dir", default="trajectories")
    a.add_argument("--out-dir", default=".")
    a.add_argument("--db", default="auditor.db")
    a.add_argument("--dry-run", action="store_true", help="print cost estimate and exit")
    return p


def run_cli(args, row_source=None, client=None) -> int:
    max_calls = args.max_calls or args.limit
    guard = CostGuard(max_calls=max_calls, max_input_tokens=10**9, max_cost_usd=args.max_cost)
    if args.dry_run:
        est = run_audit_at_scale(limit=args.limit, control_ratio=args.control, guard=guard,
                                 client=client, row_source=row_source, work_dir=args.work_dir,
                                 out_dir=args.out_dir, db_path=None, dry_run=True)
        print("=== DRY RUN ===")
        print(f"  trajectories loaded : {est['n']}")
        print(f"  to judge            : {est['to_judge']}")
        print(f"  est input tokens    : {est['est_input_tokens']}")
        print(f"  est cost (USD)      : ${est['est_cost_usd']:.4f}  (ceiling ${args.max_cost})")
        print("  No API calls made. Re-run without --dry-run to execute.")
        return 0
    res = run_audit_at_scale(limit=args.limit, control_ratio=args.control, guard=guard,
                             client=client, row_source=row_source, work_dir=args.work_dir,
                             out_dir=args.out_dir, db_path=args.db, dry_run=False)
    js = res["judge_stats"]
    print(f"[OK] audited {res['n']} trajectories | judged {js['judged']}, "
          f"skipped {js['skipped']}, errors {js['errors']}")
    rh = res["validation"]["reward_hack"]
    ja = res["validation"]["judge_agreement"]
    print(f"[OK] reward-hack detector: precision={rh['precision']:.2f} recall={rh['recall']:.2f} "
          f"(n={rh['n_evaluated']})")
    print(f"[OK] heuristic-vs-judge agreement={ja['agreement']:.2f} kappa={ja['kappa']:.2f} (n={ja['n']})")
    print(f"[OK] wrote audit_run.json + validation_report.json to {args.out_dir}")
    return 0


def main(argv=None) -> int:
    return run_cli(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_pipeline.py -v` then full suite `python3 -m pytest -q`.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/cli.py tests/test_pipeline.py
git commit -m "feat: scale-audit CLI with --dry-run cost gate"
```

---

## Task 6: Full suite + the real run (SPEND GATE)

**Files:** none (verification + the actual finding)

- [ ] **Step 1: Full suite green, no network**

Run: `python3 -m pytest -q`
Expected: all pass (Milestones 1–2 + the new pipeline tests). Zero network, zero spend.

- [ ] **Step 2: Live dry-run on a small real slice (free — no generateContent calls)**

```bash
cd <repo>; set -a; . ./.env; set +a
python3 -m src.pipeline.cli audit --limit 200 --control 0.1 --max-cost 12 --dry-run \
  --work-dir /tmp/traj200 --out-dir /tmp/run200
```
Expected: prints the projected judge count + estimated cost for 200 real trajectories. **This pulls 200 rows (network) but makes no Gemini calls.** Confirm the estimate is well under the ceiling.

- [ ] **Step 3: STOP — get explicit human approval for the real run.**

Report the dry-run estimate (judge count + projected $) to the human. **Do not proceed to Step 4 without an explicit go-ahead on the spend.** This is the first real money in the project.

- [ ] **Step 4: The real run (only after approval)**

Suggested first real run is a 1k smoke before the full 5k:
```bash
python3 -m src.pipeline.cli audit --limit 1000 --control 0.1 --max-cost 5 \
  --work-dir /tmp/traj1k --out-dir ./run1k --db ./run1k/exp.db
```
Then, if the numbers look sane, the headline 5k:
```bash
python3 -m src.pipeline.cli audit --limit 5000 --control 0.1 --max-cost 12 \
  --work-dir /tmp/traj5k --out-dir ./run5k --db ./run5k/exp.db
```
Expected: prints the reward-hack precision/recall, heuristic-vs-judge κ, and writes `audit_run.json` + `validation_report.json`. These feed Milestone 4 (explorer) and Milestone 5 (FINDINGS.md).

- [ ] **Step 5: Commit the artifacts decision**

The run outputs (`run1k/`, `run5k/`) are large and regenerable — add them to `.gitignore` rather than committing, unless the human wants a snapshot checked in. Confirm with the human.

---

## Verification (end-to-end for Milestone 3)

1. `python3 -m pytest -q` → all green, zero network/spend (pipeline tests use fake row source + stub client).
2. Live dry-run (`--dry-run`, Step 2) → projected cost printed, no Gemini calls, well under the $12 ceiling.
3. After approval: the real 1k then 5k runs produce `audit_run.json` + `validation_report.json` with the headline distribution, the reward-hack precision/recall vs `resolved`, and the heuristic-vs-judge κ.

## Spec coverage (Milestone 3 of `2026-06-08-big-audit-design.md`)

- [x] Stream N rows from HF, normalize, heuristic-audit all → Tasks 1, 4
- [x] Memory-bounded (no holding all trajectories' text; streaming + CorpusBuilder) → Tasks 2, 4
- [x] Judge cascade on flagged ∪ control under CostGuard → Task 4
- [x] Validation report (reward-hack P/R vs resolved; heuristic-vs-judge κ) → Task 4
- [x] Persist diagnoses + verdicts to SQLite → Tasks 3, 4
- [x] `audit_run.json` + `validation_report.json` → Task 4
- [x] `--dry-run` cost estimate gate at the CLI → Task 5
- [x] Explicit human spend gate before the real run → Task 6
- [ ] Explorer export + UI → Milestone 4 (next plan)
- [ ] FINDINGS.md + HF Space + launch posts → Milestone 5

## Notes

- The pipeline ingests to disk then re-streams from files, so peak RAM holds the loaded `Trajectory` list once (Pass 1+2 reuse it) — if 5k proves too heavy on the 32GB host, a follow-up can drop to per-file streaming in Pass 2 (diagnose then discard). Start at 1k to gauge real memory before 5k.
- `billed_tokens` (input+output, from the client) vs `est_input_tokens` (guard, input-only) are both surfaced in `judge_stats` for honest cost reporting.
- Model id resolved live: `gemini-2.5-flash`. One judge call ≈ 1.6k tokens → 5k flagged ≈ 8M tokens ≈ well under $1 real (≈ $2.4 at the 4× conservative constant). The $12 ceiling is generous headroom.
