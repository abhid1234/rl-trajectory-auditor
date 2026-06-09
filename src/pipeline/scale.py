from __future__ import annotations
import json
import os
from src.ingest_hf import iter_normalized
from src.loader import load_trajectories
from src.corpus import CorpusBuilder
from src.detectors import run_all
from src.framework.four_point_diagnostic import diagnose
from src.judge.cascade import judge_cascade, select_for_judging, CostGuard
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


def _verdict_to_dict(v) -> dict:
    return {"trajectory_id": v.trajectory_id, "diagnosis": v.diagnosis,
            "failure_category": v.failure_category, "confidence": v.confidence,
            "reasoning": v.reasoning, "offending_message_index": v.offending_message_index}


def run_audit_at_scale(limit=5000, control_ratio=0.1, guard=None, client=None,
                       row_source=None, work_dir="trajectories", out_dir=".",
                       db_path=None, seed=13, dry_run=False) -> dict:
    """Audit `limit` trajectories: heuristic pass, then judge cascade on the
    flagged + control subset, then validation + artifacts.

    dry_run=True stages trajectories to work_dir and computes a cost ESTIMATE
    over the would-be-judged subset, then returns WITHOUT making any judge/API
    call and WITHOUT writing audit_run.json / validation_report.json.
    """
    guard = guard or CostGuard(max_calls=limit, max_input_tokens=10**9, max_cost_usd=12.0)
    row_source = row_source if row_source is not None else iter_normalized(limit)

    _ingest(row_source, work_dir, limit)
    trajs = load_trajectories(work_dir)

    builder = CorpusBuilder()
    for t in trajs:
        builder.add(t)
    corpus = builder.build()

    diags = []
    diag_by_id = {}
    for t in trajs:
        sig = run_all(t, corpus)
        d = diagnose(t, sig)
        diags.append(d)
        diag_by_id[d.trajectory_id] = d

    chosen = select_for_judging(trajs, diag_by_id, control_ratio, seed)
    if dry_run:
        prompts = [build_judge_prompt(t) for t in chosen]
        est = guard.estimate(prompts)
        return {"dry_run": True, "n": len(trajs), "to_judge": len(chosen),
                "est_input_tokens": est["input_tokens"], "est_cost_usd": est["cost_usd"]}

    client = client or GeminiClient()
    cascade = judge_cascade(trajs, diag_by_id, client, guard, control_ratio, seed)
    verdicts = cascade["verdicts"]

    validation = {
        "reward_hack": reward_hack_validation(trajs, diag_by_id),
        "judge_agreement": judge_agreement(diag_by_id, verdicts),
    }
    avg_cost = (sum(t.cost for t in trajs) / len(trajs)) if trajs else 0.0
    report = aggregate(diags, cost_per_traj=avg_cost)
    judge_stats = {k: cascade[k] for k in
                   ("judged", "skipped", "errors", "est_input_tokens", "billed_tokens")}

    if db_path:
        db = DiagnosisDB(db_path)
        for d in diags:
            db.save(d)
        for v in verdicts.values():
            db.save_verdict(v)
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
        json.dump({**validation, "judge_stats": judge_stats, "n": len(trajs)}, f, indent=2)

    return {"n": len(trajs), "diagnoses": diags, "verdicts": verdicts,
            "report": report, "validation": validation, "judge_stats": judge_stats}
