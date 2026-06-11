from src.models import Trajectory
from src.corpus import CorpusBuilder, build_corpus


def _traj(tid, tools, repo="acme/lib", resolved=False):
    msgs = [{"role": "assistant", "content": "",
             "tool_calls": [{"id": str(i), "type": "function",
                             "function": {"name": nm, "arguments": "{}"}}]}
            for i, nm in enumerate(tools)]
    return Trajectory.from_dict({"task_id": tid, "trajectory_id": tid, "repo": repo,
        "messages": msgs, "patch": "",
        "test_results": {"pred_passes_gen_tests": 0.0, "pred_passes_gold_tests": 0.0},
        "resolved": resolved, "model": "m"})


def test_builder_matches_build_corpus():
    trajs = [_traj("t1", ["a", "b", "c"]), _traj("t2", ["a", "b", "c"]),
             _traj("t3", ["x"], resolved=True)]
    b = CorpusBuilder()
    for t in trajs:
        b.add(t)
    built = b.build()
    ref = build_corpus(trajs)
    assert built.n == ref.n
    assert built.tool_volume_mean == ref.tool_volume_mean
    assert built.tool_volume_stdev == ref.tool_volume_stdev
    assert built.fork_index == ref.fork_index
    assert built.tool_freq_centroid == ref.tool_freq_centroid
    assert built.tool_freq_stdev == ref.tool_freq_stdev


def test_builder_empty():
    c = CorpusBuilder().build()
    assert c.n == 0
    assert c.tool_volume_stdev == 0.0
    assert c.fork_index == {}
