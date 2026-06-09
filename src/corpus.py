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


class CorpusBuilder:
    """Accumulate corpus statistics one trajectory at a time without retaining
    message text — bounds memory for large runs."""

    def __init__(self):
        self._counts = []                       # tool-call count per trajectory
        self._fork_raw = defaultdict(lambda: defaultdict(set))  # family -> ngram -> {ids}
        self._freq_vectors = []                 # list[Counter] of tool names per trajectory

    def add(self, traj) -> None:
        tools = extract_tool_calls(traj)
        self._counts.append(len(tools))
        self._freq_vectors.append(Counter(tools))
        if not traj.resolved:
            fam = _family(traj)
            for g in _ngrams(tools):
                self._fork_raw[fam][g].add(traj.trajectory_id)

    def build(self) -> CorpusContext:
        counts = self._counts or [0]
        mean = statistics.fmean(counts)
        stdev = statistics.pstdev(counts) if len(counts) > 1 else 0.0
        index = {}
        for fam, grams in self._fork_raw.items():
            shared = {"->".join(g): sorted(ids) for g, ids in grams.items() if len(ids) >= 2}
            if shared:
                index[fam] = shared
        vocab = set().union(*self._freq_vectors) if self._freq_vectors else set()
        centroid, sd = {}, {}
        for tool in vocab:
            series = [v.get(tool, 0) for v in self._freq_vectors]
            centroid[tool] = statistics.fmean(series)
            sd[tool] = statistics.pstdev(series) if len(series) > 1 else 0.0
        return CorpusContext(
            tool_volume_mean=mean, tool_volume_stdev=stdev, fork_index=index,
            tool_freq_centroid=centroid, tool_freq_stdev=sd, n=len(self._counts))


def build_corpus(trajs: list[Trajectory]) -> CorpusContext:
    b = CorpusBuilder()
    for t in trajs:
        b.add(t)
    return b.build()
