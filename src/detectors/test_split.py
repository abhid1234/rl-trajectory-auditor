from __future__ import annotations
from src.models import Trajectory, DetectorSignal, CorpusContext
from src.detectors.base import no_signal

NAME = "test_split"


def detect_test_split(traj: Trajectory, corpus: CorpusContext | None) -> DetectorSignal:
    gen = traj.pred_passes_gen_tests
    gold = traj.pred_passes_gold_tests
    if gen >= 1.0 and gold <= 0.0:
        ev = [f"pred_passes_gen_tests={gen} but pred_passes_gold_tests={gold}"]
        if traj.gen_tests_correct < 1.0:
            ev.append(f"generated tests themselves incorrect (gen_tests_correct={traj.gen_tests_correct})")
        return DetectorSignal(NAME, True, 0.95, ev, {"test_split_detected": True})
    return no_signal(NAME)
