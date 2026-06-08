from __future__ import annotations
import statistics
from collections import Counter, defaultdict
from src.models import Trajectory, CorpusContext, extract_tool_calls

NGRAM = 3


def _family(traj: Trajectory) -> str:
    if traj.repo:
        return traj.repo
    tid = traj.task_id
    return tid.rsplit("-", 1)[0] if "-" in tid else tid


def _ngrams(seq: list[str], n: int = NGRAM):
    if len(seq) < n:
        return [tuple(seq)] if seq else []
    return [tuple(seq[i:i + n]) for i in range(len(seq) - n + 1)]


def _build_fork_index(trajs: list[Trajectory]) -> dict:
    # family -> ngram(str) -> sorted list of failing trajectory_ids
    raw: dict[str, dict[tuple, set]] = defaultdict(lambda: defaultdict(set))
    for t in trajs:
        if t.resolved:
            continue
        fam = _family(t)
        for g in _ngrams(extract_tool_calls(t)):
            raw[fam][g].add(t.trajectory_id)
    index: dict[str, dict[str, list]] = {}
    for fam, grams in raw.items():
        shared = {"->".join(g): sorted(ids) for g, ids in grams.items() if len(ids) >= 2}
        if shared:
            index[fam] = shared
    return index


def _tool_freq_model(trajs: list[Trajectory]) -> tuple[dict, dict]:
    vectors = [Counter(extract_tool_calls(t)) for t in trajs]
    vocab = set().union(*vectors) if vectors else set()
    centroid, stdev = {}, {}
    for tool in vocab:
        series = [v.get(tool, 0) for v in vectors]
        centroid[tool] = statistics.fmean(series)
        stdev[tool] = statistics.pstdev(series) if len(series) > 1 else 0.0
    return centroid, stdev


def build_corpus(trajs: list[Trajectory]) -> CorpusContext:
    counts = [len(extract_tool_calls(t)) for t in trajs] or [0]
    mean = statistics.fmean(counts)
    stdev = statistics.pstdev(counts) if len(counts) > 1 else 0.0
    centroid, sd = _tool_freq_model(trajs)
    return CorpusContext(
        tool_volume_mean=mean,
        tool_volume_stdev=stdev,
        fork_index=_build_fork_index(trajs),
        tool_freq_centroid=centroid,
        tool_freq_stdev=sd,
        n=len(trajs),
    )
