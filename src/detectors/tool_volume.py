from __future__ import annotations
from src.models import Trajectory, DetectorSignal, CorpusContext, extract_tool_calls

NAME = "tool_volume"
Z = 2.0


def detect_tool_volume(traj: Trajectory, corpus: CorpusContext | None) -> DetectorSignal:
    n = len(extract_tool_calls(traj))
    if corpus is None or corpus.tool_volume_stdev == 0.0:
        return DetectorSignal(NAME, False, 0.0, [], {"tool_volume": "normal", "count": n})
    z = (n - corpus.tool_volume_mean) / corpus.tool_volume_stdev
    if abs(z) >= Z:
        kind = "high" if z > 0 else "low"
        ev = [f"tool calls={n} is {z:+.1f}σ from corpus mean {corpus.tool_volume_mean:.1f} ({kind})"]
        return DetectorSignal(NAME, True, min(abs(z) / 4.0, 0.95), ev,
                              {"tool_volume": kind, "count": n, "z": z})
    return DetectorSignal(NAME, False, 0.0, [], {"tool_volume": "normal", "count": n, "z": z})
