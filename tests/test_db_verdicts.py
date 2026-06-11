from src.models import JudgeVerdict
from src.db import DiagnosisDB


def test_verdict_roundtrip(tmp_path):
    db = DiagnosisDB(str(tmp_path / "exp.db"))
    db.save_verdict(JudgeVerdict("t1", "TRAINING", "Reward Hack", 0.9, "hacked", 2, {"x": 1}))
    db.save_verdict(JudgeVerdict("t2", "HARNESS", "Context Gap", 0.7, "missing", None, {}))
    rows = db.verdicts()
    assert len(rows) == 2
    by_id = {r["trajectory_id"]: r for r in rows}
    assert by_id["t1"]["diagnosis"] == "TRAINING"
    assert by_id["t1"]["offending_message_index"] == 2
    assert by_id["t2"]["offending_message_index"] is None
    db.close()
