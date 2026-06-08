from __future__ import annotations
from src.models import Trajectory, DetectorSignal, CorpusContext, extract_tool_calls
from src.corpus import _family, _ngrams
from src.detectors.base import no_signal

NAME = "fork_pattern"


def detect_fork_pattern(traj: Trajectory, corpus: CorpusContext | None) -> DetectorSignal:
    if corpus is None or not corpus.fork_index:
        return no_signal(NAME)
    fam_index = corpus.fork_index.get(_family(traj), {})
    if not fam_index:
        return no_signal(NAME)
    my_grams = {"->".join(g) for g in _ngrams(extract_tool_calls(traj))}
    matches = []
    for gram, ids in fam_index.items():
        if gram in my_grams:
            others = [i for i in ids if i != traj.trajectory_id]
            if others:
                matches.append((gram, others))
    if not matches:
        return no_signal(NAME)
    gram, others = max(matches, key=lambda x: len(x[1]))
    ev = [f"repeated failing tool sequence [{gram}] also in {len(others)} other trace(s)"]
    return DetectorSignal(NAME, True, min(0.5 + 0.1 * len(others), 0.95), ev,
                          {"fork_pattern": gram, "shared_with": others})
