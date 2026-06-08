from src.models import JudgeVerdict


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
