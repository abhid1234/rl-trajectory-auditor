from pathlib import Path
from src.models import Trajectory
from src.detectors import run_all
from src.corpus import build_corpus
from src.framework.four_point_diagnostic import diagnose
from src.framework.checklist import CHECKLIST, checklist_status


def _t(**kw):
    base = {"task_id": "t", "repo": "acme/lib", "messages": [], "patch": "",
            "test_results": {"pred_passes_gen_tests": 0.0, "pred_passes_gold_tests": 0.0},
            "resolved": False, "model": "m"}
    base.update(kw)
    return Trajectory.from_dict(base)


def _diag(traj, corpus=None):
    return diagnose(traj, run_all(traj, corpus or build_corpus([traj])))


def test_reward_hack_is_training():
    t = _t(patch="diff --git a/tests/test_x.py b/tests/test_x.py\n+++ b/tests/test_x.py\n+assert True\n",
           test_results={"pred_passes_gen_tests": 1.0, "pred_passes_gold_tests": 0.0})
    d = _diag(t)
    assert d.diagnosis == "TRAINING"
    assert d.failure_category == "Reward Hack"
    assert d.confidence > 0.5
    assert d.signals["test_split_detected"] is True
    assert "rubric" in d.fix_recommendation.lower()


def test_context_gap_is_harness():
    t = _t(messages=[{"role": "tool", "content": "config.yaml: No such file or directory"}])
    d = _diag(t)
    assert d.diagnosis == "HARNESS"
    assert d.failure_category == "Context Gap"


def test_clean_when_resolved():
    t = _t(resolved=True, test_results={"pred_passes_gen_tests": 1.0, "pred_passes_gold_tests": 1.0})
    d = _diag(t)
    assert d.diagnosis == "CLEAN"
    assert d.failure_category == "Clean"


def test_both_when_harness_and_training():
    t = _t(patch="diff --git a/tests/test_x.py b/tests/test_x.py\n+++ b/tests/test_x.py\n+assert True\n",
           test_results={"pred_passes_gen_tests": 1.0, "pred_passes_gold_tests": 0.0},
           messages=[{"role": "tool", "content": "config.yaml: No such file or directory"}])
    d = _diag(t)
    assert d.diagnosis == "BOTH"


# --- checklist ---

def test_checklist_has_ten_items():
    assert len(CHECKLIST) == 10
    assert all({"id", "question", "implemented_by"} <= set(item) for item in CHECKLIST)


def test_checklist_status_marks_fired_items():
    t = _t(patch="diff --git a/tests/test_x.py b/tests/test_x.py\n+++ b/tests/test_x.py\n+assert True\n",
           test_results={"pred_passes_gen_tests": 1.0, "pred_passes_gold_tests": 0.0})
    status = checklist_status(run_all(t, build_corpus([t])))
    triggered = [row for row in status if row["triggered"]]
    assert any(row["implemented_by"] == "reward_hack" for row in triggered)


# --- fixtures end-to-end ---

FIX = Path(__file__).parent / "fixtures"


def _audit_fixtures():
    from src.loader import load_trajectories
    trajs = load_trajectories(str(FIX))
    corpus = build_corpus(trajs)
    return {t.task_id: diagnose(t, run_all(t, corpus)) for t in trajs}


def test_fixtures_classify_correctly():
    d = _audit_fixtures()
    assert d["acme-reward-hack-1"].diagnosis == "TRAINING"
    assert d["acme-reward-hack-1"].failure_category == "Reward Hack"
    assert d["acme-context-1"].diagnosis == "HARNESS"
    assert d["acme-context-1"].failure_category == "Context Gap"
    assert d["acme-clean-1"].diagnosis == "CLEAN"
    assert d["acme-fork-1"].signals["fork_pattern"] is not None
    assert d["acme-fork-1"].failure_category in ("Stuck at Fork", "Context Gap", "Reward Hack")
