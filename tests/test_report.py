import json as _json
from src.models import Diagnosis
from src.report.aggregate import aggregate
from src.report.format import render_terminal, diagnosis_to_dict
from src.db import DiagnosisDB
from src.auditor import run_audit
from src.ingest_hf import normalize_row


def _d(diag, cat, conf=0.9):
    return Diagnosis("id", diag, cat, conf, ["ev"], "fix", {})


def test_aggregate_counts_categories_and_splits():
    diags = [_d("TRAINING", "Reward Hack"), _d("TRAINING", "Reward Hack"),
             _d("HARNESS", "Context Gap"), _d("CLEAN", "Clean")]
    rep = aggregate(diags)
    assert rep["total"] == 4
    assert rep["categories"]["Reward Hack"] == 2
    assert rep["splits"]["HARNESS"] == 1
    assert rep["splits"]["TRAINING"] == 2
    assert rep["clean"] == 1


def test_render_terminal_contains_bars_and_headers():
    rep = aggregate([_d("TRAINING", "Reward Hack"), _d("CLEAN", "Clean")])
    text = render_terminal(rep)
    assert "FAILURE DISTRIBUTION" in text
    assert "HARNESS vs TRAINING" in text
    assert "█" in text or "#" in text


def test_diagnosis_to_dict_matches_spec_keys():
    d = _d("TRAINING", "Reward Hack")
    out = diagnosis_to_dict(d)
    assert {"trajectory_id", "diagnosis", "failure_category", "confidence",
            "evidence", "fix_recommendation", "signals"} <= set(out)


def test_db_roundtrip(tmp_path):
    db = DiagnosisDB(str(tmp_path / "exp.db"))
    db.save(_d("TRAINING", "Reward Hack"))
    db.save(_d("HARNESS", "Context Gap"))
    rows = db.all()
    assert len(rows) == 2
    counts = db.category_counts()
    assert counts["Reward Hack"] == 1
    db.close()


def test_run_audit_end_to_end(tmp_path):
    hack = {"task_id": "h1", "repo": "acme/lib", "patch": "diff --git a/tests/t.py b/tests/t.py\n+++ b/tests/t.py\n+assert True\n",
            "messages": [], "test_results": {"pred_passes_gen_tests": 1.0, "pred_passes_gold_tests": 0.0},
            "resolved": False, "model": "m"}
    clean = {"task_id": "c1", "repo": "acme/lib", "patch": "diff --git a/src/x.py b/src/x.py\n+ok\n",
             "messages": [], "test_results": {"pred_passes_gen_tests": 1.0, "pred_passes_gold_tests": 1.0},
             "resolved": True, "model": "m"}
    (tmp_path / "h.json").write_text(_json.dumps(hack))
    (tmp_path / "c.json").write_text(_json.dumps(clean))
    diags, report = run_audit(str(tmp_path))
    assert len(diags) == 2
    assert report["splits"].get("TRAINING", 0) >= 1
    assert report["splits"].get("CLEAN", 0) >= 1


def test_normalize_hf_row():
    row = {"row": {
        "trajectory_id": "chatcmpl-1", "instance_id": "acme__lib-7", "repo": "acme/lib",
        "trajectory": [{"role": "user", "content": "fix", "name": None, "tool_call_id": None, "tool_calls": []}],
        "tools": [], "model_patch": "diff", "exit_status": "submitted",
        "resolved": 0, "gen_tests_correct": 0.0, "pred_passes_gen_tests": 1.0,
    }}
    out = normalize_row(row)
    assert out["task_id"] == "acme__lib-7"
    assert out["test_results"]["pred_passes_gen_tests"] == 1.0
    assert out["test_results"]["pred_passes_gold_tests"] == 0.0  # from resolved=0
    assert out["resolved"] is False
    assert out["messages"][0]["role"] == "user"
