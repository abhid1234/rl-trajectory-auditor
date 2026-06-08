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


from src.models import Diagnosis, JudgeVerdict
from src.validate.metrics import (confusion_matrix, precision_recall_f1,
                                   cohens_kappa, reward_hack_validation, judge_agreement)


def test_confusion_and_prf():
    y_true = [1, 1, 0, 0, 1]
    y_pred = [1, 0, 0, 1, 1]
    cm = confusion_matrix(y_true, y_pred)
    assert cm == {"tp": 2, "fp": 1, "fn": 1, "tn": 1}
    prf = precision_recall_f1(cm)
    assert prf["precision"] == 2 / 3
    assert prf["recall"] == 2 / 3
    assert prf["f1"] == 2 / 3


def test_cohens_kappa_perfect_and_chance():
    assert cohens_kappa(["A", "B", "A"], ["A", "B", "A"]) == 1.0
    assert cohens_kappa(["A", "A", "B", "B"], ["B", "B", "A", "A"]) == -1.0


def _traj_diag(tid, gen, gold, resolved, heur_category):
    from src.models import Trajectory
    t = Trajectory.from_dict({"task_id": tid, "messages": [], "patch": "",
        "test_results": {"pred_passes_gen_tests": gen, "pred_passes_gold_tests": gold},
        "resolved": resolved, "model": "m"})
    diag = "TRAINING" if heur_category == "Reward Hack" else "CLEAN"
    d = Diagnosis(tid, diag, heur_category, 0.9, [], "fix", {})
    return t, d


def test_reward_hack_validation_scores_detector():
    # prediction = (failure_category == "Reward Hack")
    # t1: real hack, predicted hack  (tp)
    # t2: real hack, predicted clean (fn)
    # t3: clean,     predicted hack  (fp)
    # t4: clean,     predicted clean (tn)
    rows = [_traj_diag("t1", 1.0, 0.0, False, "Reward Hack"),
            _traj_diag("t2", 1.0, 0.0, False, "Clean"),
            _traj_diag("t3", 1.0, 1.0, True, "Reward Hack"),
            _traj_diag("t4", 1.0, 1.0, True, "Clean"),
            _traj_diag("t5", 0.0, 0.0, False, "Clean")]   # UNKNOWN gold -> excluded
    trajs = [t for t, _ in rows]
    diags = {t.trajectory_id: d for t, d in rows}
    out = reward_hack_validation(trajs, diags)
    assert out["confusion"] == {"tp": 1, "fp": 1, "fn": 1, "tn": 1}
    assert out["n_evaluated"] == 4


def test_judge_agreement():
    diags = {"a": Diagnosis("a", "TRAINING", "c", 0.9, [], "f", {}),
             "b": Diagnosis("b", "HARNESS", "c", 0.9, [], "f", {})}
    verdicts = {"a": JudgeVerdict("a", "TRAINING", "c", 0.9, "r", None),
                "b": JudgeVerdict("b", "TRAINING", "c", 0.9, "r", None)}
    out = judge_agreement(diags, verdicts)
    assert out["n"] == 2
    assert out["agreement"] == 0.5
    assert out["kappa"] == 0.0


def test_cohens_kappa_empty_input():
    from src.validate.metrics import cohens_kappa
    assert cohens_kappa([], []) == 0.0
