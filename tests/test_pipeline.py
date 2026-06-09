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
    assert "hack1" in out["verdicts"]
    assert "clean1" not in out["verdicts"]
    assert out["report"]["total"] == 3
    assert out["validation"]["reward_hack"]["n_evaluated"] >= 1
    assert "judge_agreement" in out["validation"]
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
    assert est["to_judge"] >= 1
    assert "est_cost_usd" in est
    assert not (tmp_path / "audit_run.json").exists()
