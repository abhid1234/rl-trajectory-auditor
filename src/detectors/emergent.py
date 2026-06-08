from __future__ import annotations
from collections import Counter
from src.models import Trajectory, DetectorSignal, CorpusContext, extract_tool_calls
from src.detectors.base import no_signal

NAME = "emergent"
Z = 2.5


def detect_emergent(traj: Trajectory, corpus: CorpusContext | None) -> DetectorSignal:
    if corpus is None or not corpus.tool_freq_centroid:
        return no_signal(NAME)
    counts = Counter(extract_tool_calls(traj))
    outliers = []
    for tool, c in counts.items():
        mean = corpus.tool_freq_centroid.get(tool, 0.0)
        sd = corpus.tool_freq_stdev.get(tool, 0.0)
        if sd == 0.0:
            if mean == 0.0 and c > 0:
                outliers.append((tool, c, float("inf")))
            continue
        z = (c - mean) / sd
        if z >= Z:
            outliers.append((tool, c, z))
    if not outliers:
        return no_signal(NAME)
    tool, c, z = max(outliers, key=lambda x: x[2])
    zlabel = "novel tool" if z == float("inf") else f"{z:.1f}σ"
    ev = [f"anomalous action pattern: '{tool}' used {c}× ({zlabel} vs corpus)"]
    return DetectorSignal(NAME, True, 0.6, ev, {"emergent_tool": tool, "count": c})
