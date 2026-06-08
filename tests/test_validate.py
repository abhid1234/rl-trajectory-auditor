from src.models import Trajectory
from src.validate.ground_truth import gold_label, REWARD_HACK_TRUE, CLEAN_TRUE, UNKNOWN


def _t(gen, gold, resolved):
    return Trajectory.from_dict({"task_id": "t", "messages": [], "patch": "",
        "test_results": {"pred_passes_gen_tests": gen, "pred_passes_gold_tests": gold},
        "resolved": resolved, "model": "m"})


def test_reward_hack_truth():
    assert gold_label(_t(1.0, 0.0, False)) == REWARD_HACK_TRUE


def test_clean_truth():
    assert gold_label(_t(1.0, 1.0, True)) == CLEAN_TRUE


def test_unknown_when_just_fails():
    assert gold_label(_t(0.0, 0.0, False)) == UNKNOWN
