from __future__ import annotations
from collections import Counter
from src.models import Trajectory, Diagnosis, JudgeVerdict
from src.validate.ground_truth import gold_label, REWARD_HACK_TRUE, CLEAN_TRUE, UNKNOWN


def confusion_matrix(y_true: list[int], y_pred: list[int]) -> dict:
    tp = fp = fn = tn = 0
    for yt, yp in zip(y_true, y_pred):
        if yp and yt:
            tp += 1
        elif yp and not yt:
            fp += 1
        elif not yp and yt:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall_f1(cm: dict) -> dict:
    tp, fp, fn = cm["tp"], cm["fp"], cm["fn"]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def cohens_kappa(a: list[str], b: list[str]) -> float:
    n = len(a)
    if n == 0:
        return 0.0
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    labels = set(a) | set(b)
    pe = sum((ca[l] / n) * (cb[l] / n) for l in labels)
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def reward_hack_validation(trajs: list[Trajectory], diags: dict[str, Diagnosis]) -> dict:
    """Heuristic reward-hack prediction vs gold, excluding UNKNOWN-gold trajectories."""
    y_true, y_pred = [], []
    for t in trajs:
        gold = gold_label(t)
        if gold == UNKNOWN:
            continue
        d = diags.get(t.trajectory_id)
        pred_hack = 1 if (d is not None and d.failure_category == "Reward Hack") else 0
        y_true.append(1 if gold == REWARD_HACK_TRUE else 0)
        y_pred.append(pred_hack)
    cm = confusion_matrix(y_true, y_pred)
    return {"confusion": cm, **precision_recall_f1(cm), "n_evaluated": len(y_true)}


def judge_agreement(diags: dict[str, Diagnosis], verdicts: dict[str, JudgeVerdict]) -> dict:
    ids = sorted(set(diags) & set(verdicts))
    heur = [diags[i].diagnosis for i in ids]
    judge = [verdicts[i].diagnosis for i in ids]
    n = len(ids)
    agreement = (sum(1 for a, b in zip(heur, judge) if a == b) / n) if n else 0.0
    return {"n": n, "agreement": agreement, "kappa": cohens_kappa(heur, judge)}
