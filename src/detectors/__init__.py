from __future__ import annotations
from src.models import Trajectory, DetectorSignal, CorpusContext
from src.detectors.test_split import detect_test_split
from src.detectors.reward_hack import detect_reward_hack
from src.detectors.context_check import detect_context_check
from src.detectors.tool_volume import detect_tool_volume
from src.detectors.fork_pattern import detect_fork_pattern
from src.detectors.emergent import detect_emergent

DETECTORS = [
    ("test_split", detect_test_split),
    ("reward_hack", detect_reward_hack),
    ("context_check", detect_context_check),
    ("tool_volume", detect_tool_volume),
    ("fork_pattern", detect_fork_pattern),
    ("emergent", detect_emergent),
]


def run_all(traj: Trajectory, corpus: CorpusContext | None) -> dict[str, DetectorSignal]:
    return {name: fn(traj, corpus) for name, fn in DETECTORS}
