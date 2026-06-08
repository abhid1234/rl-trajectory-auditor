from __future__ import annotations
from src.models import Trajectory, DetectorSignal, Diagnosis

_FIXES = {
    "Context Gap": "Add the missing context (config/files/env) to the harness or system prompt. "
                   "No retrain needed — fix the environment before the next run.",
    "Reward Hack": "Add adversarial test variants and strengthen the rubric to check real code "
                   "correctness, not output/test surface patterns.",
    "Stuck at Fork": "Add training coverage for this decision point; the model repeats the same "
                     "failing maneuver across traces in this task family.",
    "Emergent/Unknown": "Inspect product routing and action policy — anomalous behavior with no "
                        "harness/reward cause. Likely a product-side or policy issue.",
    "Clean": "No action — trajectory resolved correctly with no anomalies.",
    "Unclassified Failure": "Manual review: failed but no detector fired with confidence. "
                            "Eyeball the trace.",
}


def diagnose(traj: Trajectory, signals: dict[str, DetectorSignal]) -> Diagnosis:
    s = signals
    harness = s["context_check"].fired
    reward = s["reward_hack"].fired or s["test_split"].fired
    fork = s["fork_pattern"].fired
    emergent = s["emergent"].fired

    flat = {
        "test_split_detected": s["test_split"].details.get("test_split_detected", False),
        "fork_pattern": s["fork_pattern"].details.get("fork_pattern"),
        "context_complete": s["context_check"].details.get("context_complete", True),
        "tool_volume": s["tool_volume"].details.get("tool_volume", "normal"),
    }
    evidence = [e for sig in s.values() if sig.fired for e in sig.evidence]

    if traj.resolved and not (harness or reward or fork or emergent):
        return Diagnosis(traj.trajectory_id, "CLEAN", "Clean", 0.9, [],
                         _FIXES["Clean"], flat)

    training = reward or fork
    if harness and training:
        diagnosis, category = "BOTH", "Reward Hack" if reward else "Stuck at Fork"
        conf = max(s["context_check"].score, s["reward_hack"].score, s["fork_pattern"].score)
    elif harness:
        diagnosis, category, conf = "HARNESS", "Context Gap", s["context_check"].score
    elif reward:
        diagnosis, category = "TRAINING", "Reward Hack"
        conf = max(s["reward_hack"].score, s["test_split"].score)
    elif fork:
        diagnosis, category, conf = "TRAINING", "Stuck at Fork", s["fork_pattern"].score
    elif emergent:
        diagnosis, category, conf = "PRODUCT", "Emergent/Unknown", s["emergent"].score
    else:
        diagnosis, category, conf = "PRODUCT", "Unclassified Failure", 0.3

    return Diagnosis(traj.trajectory_id, diagnosis, category, round(conf, 2),
                     evidence, _FIXES.get(category, _FIXES["Unclassified Failure"]), flat)
