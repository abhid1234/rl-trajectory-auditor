from src.models import JudgeVerdict, Trajectory
from src.judge.prompt import build_judge_prompt, parse_verdict, JUDGE_SCHEMA, MAX_PROMPT_CHARS


def test_judge_verdict_fields():
    v = JudgeVerdict(
        trajectory_id="t1",
        diagnosis="TRAINING",
        failure_category="Reward Hack",
        confidence=0.9,
        reasoning="passes gen tests but gold fails",
        offending_message_index=3,
        raw={"k": "v"},
    )
    assert v.diagnosis == "TRAINING"
    assert v.offending_message_index == 3
    assert v.raw["k"] == "v"


def _traj(messages, **kw):
    base = {"task_id": "t1", "task_description": "Fix the bug", "messages": messages,
            "patch": "diff", "test_results": {"pred_passes_gen_tests": 1.0, "pred_passes_gold_tests": 0.0},
            "resolved": False, "model": "m"}
    base.update(kw)
    return Trajectory.from_dict(base)


def test_prompt_includes_task_and_diagnostic_vocab():
    p = build_judge_prompt(_traj([{"role": "user", "content": "Fix the bug"}]))
    assert "Fix the bug" in p
    assert "HARNESS" in p and "TRAINING" in p and "CLEAN" in p
    assert "JSON" in p.upper()


def test_prompt_truncates_long_trajectories():
    big = [{"role": "assistant", "content": "x" * 500} for _ in range(200)]
    p = build_judge_prompt(_traj(big))
    assert len(p) <= MAX_PROMPT_CHARS + 2000  # body capped; header/footer overhead allowed


def test_schema_is_object_with_required_keys():
    assert JUDGE_SCHEMA["type"] == "object"
    assert set(["diagnosis", "failure_category", "confidence", "reasoning"]).issubset(
        JUDGE_SCHEMA["properties"].keys())


def test_parse_verdict_maps_json():
    j = {"diagnosis": "TRAINING", "failure_category": "Reward Hack", "confidence": 0.88,
         "reasoning": "gamed the rubric", "offending_message_index": 2}
    v = parse_verdict("t1", j)
    assert v.trajectory_id == "t1"
    assert v.diagnosis == "TRAINING"
    assert v.confidence == 0.88
    assert v.offending_message_index == 2


def test_parse_verdict_tolerates_missing_fields():
    v = parse_verdict("t1", {"diagnosis": "clean"})
    assert v.diagnosis == "CLEAN"            # upper-cased/normalized
    assert v.failure_category == "Unknown"
    assert v.confidence == 0.0
    assert v.offending_message_index is None
