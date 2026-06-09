from __future__ import annotations
import glob
import json
import os
import random
from src.models import Trajectory, JudgeVerdict
from src.ingest_hf import iter_normalized
from src.corpus import CorpusBuilder
from src.detectors import run_all
from src.framework.four_point_diagnostic import diagnose
from src.judge.cascade import CostGuard, _tokens_from_chars
from src.judge.gemini import GeminiClient
from src.judge.prompt import build_judge_prompt, JUDGE_SCHEMA, parse_verdict
from src.validate.ground_truth import gold_label
from src.validate.metrics import reward_hack_validation_from_labels, judge_agreement
from src.report.aggregate import aggregate
from src.report.format import diagnosis_to_dict
from src.db import DiagnosisDB


def _ingest(row_source, work_dir: str, limit: int) -> list[str]:
    """Stage up to `limit` normalized rows to disk; return the sorted file paths."""
    os.makedirs(work_dir, exist_ok=True)
    n = 0
    for norm in row_source:
        path = os.path.join(work_dir, f"{norm['task_id'].replace('/', '__')}_{n}.json")
        with open(path, "w") as f:
            json.dump(norm, f)
        n += 1
        if n >= limit:
            break
    return sorted(glob.glob(os.path.join(work_dir, "*.json")))


def _load_one(path: str) -> Trajectory:
    with open(path) as f:
        return Trajectory.from_dict(json.load(f))


def _verdict_to_dict(v: JudgeVerdict) -> dict:
    return {"trajectory_id": v.trajectory_id, "diagnosis": v.diagnosis,
            "failure_category": v.failure_category, "confidence": v.confidence,
            "reasoning": v.reasoning, "offending_message_index": v.offending_message_index}


def _verdict_from_row(r: dict) -> JudgeVerdict:
    raw = r.get("raw")
    try:
        raw = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except (TypeError, ValueError):
        raw = {}
    return JudgeVerdict(r["trajectory_id"], r["diagnosis"], r["failure_category"],
                        r["confidence"], r.get("reasoning", ""),
                        r.get("offending_message_index"), raw)


def _select_ids(diag_by_id: dict, control_ratio: float, seed: int) -> list[str]:
    flagged = [i for i, d in diag_by_id.items() if d.diagnosis != "CLEAN"]
    clean = [i for i, d in diag_by_id.items() if d.diagnosis == "CLEAN"]
    rng = random.Random(seed)
    k = min(int(len(clean) * control_ratio), len(clean))
    control = rng.sample(clean, k) if k else []
    return flagged + control


def run_audit_at_scale(limit=5000, control_ratio=0.1, guard=None, client=None,
                       row_source=None, work_dir="trajectories", out_dir=".",
                       db_path=None, seed=13, dry_run=False) -> dict:
    """Audit `limit` trajectories: heuristic pass, then judge cascade on the
    flagged + control subset, then validation + artifacts.

    Memory-bounded: trajectories are staged to disk and streamed ONE AT A TIME in
    every pass — the run never holds the full trajectory set in RAM (only small
    Diagnosis/label/verdict records). Suitable for large runs on small machines.

    Judge verdicts are persisted to SQLite incrementally as they are produced, and
    trajectories already present in the DB are skipped — so an interrupted run can
    be resumed by re-invoking with the same --db.

    dry_run=True stages + estimates cost over the would-be-judged subset, then
    returns WITHOUT any judge/API call and WITHOUT writing artifacts.
    """
    guard = guard or CostGuard(max_calls=limit, max_input_tokens=10**9, max_cost_usd=12.0)
    row_source = row_source if row_source is not None else iter_normalized(limit)

    paths = _ingest(row_source, work_dir, limit)
    path_by_id: dict[str, str] = {}

    # Pass 1: corpus statistics (one trajectory at a time).
    builder = CorpusBuilder()
    for p in paths:
        t = _load_one(p)
        builder.add(t)
        path_by_id[t.trajectory_id] = p
    corpus = builder.build()

    # Pass 2: heuristic diagnosis (stream; retain only small records).
    diags = []
    diag_by_id = {}
    gold_by_id = {}
    total_cost = 0.0
    for p in paths:
        t = _load_one(p)
        d = diagnose(t, run_all(t, corpus))
        diags.append(d)
        diag_by_id[d.trajectory_id] = d
        gold_by_id[t.trajectory_id] = gold_label(t)
        total_cost += t.cost

    chosen_ids = _select_ids(diag_by_id, control_ratio, seed)

    if dry_run:
        prompts = [build_judge_prompt(_load_one(path_by_id[i])) for i in chosen_ids]
        est = guard.estimate(prompts)
        return {"dry_run": True, "n": len(paths), "to_judge": len(chosen_ids),
                "est_input_tokens": est["input_tokens"], "est_cost_usd": est["cost_usd"]}

    client = client or GeminiClient()
    db = DiagnosisDB(db_path) if db_path else None

    # Resume: load any verdicts already persisted, skip those ids below.
    verdicts: dict[str, JudgeVerdict] = {}
    if db:
        for r in db.verdicts():
            verdicts[r["trajectory_id"]] = _verdict_from_row(r)

    # Pass 3: judge (stream; persist each verdict immediately).
    judged = skipped = errors = 0
    for i in chosen_ids:
        if i in verdicts:        # already judged in a prior run
            continue
        t = _load_one(path_by_id[i])
        prompt = build_judge_prompt(t)
        est_tokens = _tokens_from_chars(len(prompt))
        if not guard.before_call(est_tokens):
            skipped += 1
            continue
        try:
            v = parse_verdict(i, client.generate_json(prompt, JUDGE_SCHEMA))
            verdicts[i] = v
            if db:
                db.save_verdict(v)
            judged += 1
        except Exception:
            errors += 1
        finally:
            guard.record(est_tokens)

    validation = {
        "reward_hack": reward_hack_validation_from_labels(gold_by_id, diag_by_id),
        "judge_agreement": judge_agreement(diag_by_id, verdicts),
    }
    avg_cost = (total_cost / len(paths)) if paths else 0.0
    report = aggregate(diags, cost_per_traj=avg_cost)
    judge_stats = {"judged": judged, "skipped": skipped, "errors": errors,
                   "est_input_tokens": guard.input_tokens,
                   "billed_tokens": getattr(client, "total_tokens", None)}

    if db:
        for d in diags:
            db.save(d)
        db.close()

    os.makedirs(out_dir, exist_ok=True)
    run_obj = {
        "diagnoses": [diagnosis_to_dict(d) for d in diags],
        "verdicts": {vid: _verdict_to_dict(v) for vid, v in verdicts.items()},
        "report": report, "validation": validation, "judge_stats": judge_stats,
    }
    with open(os.path.join(out_dir, "audit_run.json"), "w") as f:
        json.dump(run_obj, f, indent=2)
    with open(os.path.join(out_dir, "validation_report.json"), "w") as f:
        json.dump({**validation, "judge_stats": judge_stats, "n": len(paths)}, f, indent=2)

    return {"n": len(paths), "diagnoses": diags, "verdicts": verdicts,
            "report": report, "validation": validation, "judge_stats": judge_stats}
