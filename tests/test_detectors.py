from src.models import Trajectory, DetectorSignal
from src.detectors.base import no_signal
from src.detectors.test_split import detect_test_split
from src.detectors.reward_hack import detect_reward_hack
from src.detectors.context_check import detect_context_check
from src.detectors.tool_volume import detect_tool_volume
from src.detectors.fork_pattern import detect_fork_pattern
from src.detectors.emergent import detect_emergent
from src.corpus import build_corpus
from src.detectors import DETECTORS, run_all


def test_no_signal_helper():
    s = no_signal("reward_hack")
    assert isinstance(s, DetectorSignal)
    assert s.name == "reward_hack"
    assert s.fired is False
    assert s.score == 0.0
    assert s.evidence == []


# --- test_split ---

def _traj(gen, gold, resolved=False):
    return Trajectory.from_dict({
        "task_id": "t", "messages": [], "patch": "",
        "test_results": {"pred_passes_gen_tests": gen, "pred_passes_gold_tests": gold},
        "resolved": resolved, "model": "m",
    })


def test_split_fires_on_self_pass_gold_fail():
    s = detect_test_split(_traj(1.0, 0.0), None)
    assert s.fired is True
    assert s.score >= 0.9
    assert any("gold" in e.lower() for e in s.evidence)
    assert s.details["test_split_detected"] is True


def test_split_quiet_when_both_pass():
    assert detect_test_split(_traj(1.0, 1.0, resolved=True), None).fired is False


def test_split_quiet_when_both_fail():
    assert detect_test_split(_traj(0.0, 0.0), None).fired is False


# --- reward_hack ---

def _traj_patch(patch, gen=1.0, gold=0.0):
    return Trajectory.from_dict({
        "task_id": "t", "messages": [], "patch": patch,
        "test_results": {"pred_passes_gen_tests": gen, "pred_passes_gold_tests": gold},
        "resolved": gold >= 1.0, "model": "m",
    })


def test_reward_hack_fires_on_test_file_edit():
    patch = "diff --git a/tests/test_x.py b/tests/test_x.py\n+++ b/tests/test_x.py\n+    assert True\n"
    s = detect_reward_hack(_traj_patch(patch), None)
    assert s.fired is True
    assert any("test file" in e.lower() for e in s.evidence)


def test_reward_hack_fires_on_hardcoded_return():
    patch = "diff --git a/src/x.py b/src/x.py\n+    return 42  # expected\n"
    s = detect_reward_hack(_traj_patch(patch), None)
    assert s.fired is True


def test_reward_hack_quiet_on_real_fix():
    patch = "diff --git a/src/x.py b/src/x.py\n+    if dim is None:\n+        dim = data.dims[0]\n"
    s = detect_reward_hack(_traj_patch(patch, gen=1.0, gold=1.0), None)
    assert s.fired is False


# --- tool_volume ---

def _traj_tools(n_calls, task="t"):
    msgs = [{"role": "assistant", "content": "", "tool_calls":
             [{"id": str(i), "type": "function", "function": {"name": "execute_bash", "arguments": "{}"}}]}
            for i in range(n_calls)]
    return Trajectory.from_dict({"task_id": task, "messages": msgs, "patch": "",
        "test_results": {"pred_passes_gen_tests": 0.0, "pred_passes_gold_tests": 0.0},
        "resolved": False, "model": "m"})


def test_tool_volume_flags_outlier():
    corpus_trajs = [_traj_tools(10) for _ in range(9)] + [_traj_tools(200)]
    ctx = build_corpus(corpus_trajs)
    high = detect_tool_volume(_traj_tools(200), ctx)
    assert high.fired is True
    assert high.details["tool_volume"] in ("high", "low")


def test_tool_volume_quiet_for_typical():
    corpus_trajs = [_traj_tools(10) for _ in range(10)]
    ctx = build_corpus(corpus_trajs)
    assert detect_tool_volume(_traj_tools(10), ctx).fired is False


# --- context_check ---

def _traj_obs(obs_texts, resolved=False):
    msgs = [{"role": "tool", "content": o} for o in obs_texts]
    return Trajectory.from_dict({"task_id": "t", "messages": msgs, "patch": "",
        "test_results": {"pred_passes_gen_tests": 0.0, "pred_passes_gold_tests": 0.0},
        "resolved": resolved, "model": "m"})


def test_context_check_flags_missing_file():
    s = detect_context_check(_traj_obs(["cat config.yaml", "config.yaml: No such file or directory"]), None)
    assert s.fired is True
    assert s.details["context_complete"] is False
    assert any("No such file" in e or "missing" in e.lower() for e in s.evidence)


def test_context_check_quiet_when_clean():
    s = detect_context_check(_traj_obs(["all tests passed"], resolved=True), None)
    assert s.fired is False
    assert s.details["context_complete"] is True


# --- fork_pattern ---

def _traj_seq(names, task_id, repo="acme/lib", resolved=False):
    msgs = [{"role": "assistant", "content": "",
             "tool_calls": [{"id": str(i), "type": "function", "function": {"name": nm, "arguments": "{}"}}]}
            for i, nm in enumerate(names)]
    return Trajectory.from_dict({"task_id": task_id, "repo": repo, "messages": msgs, "patch": "",
        "test_results": {"pred_passes_gen_tests": 0.0, "pred_passes_gold_tests": 0.0},
        "resolved": resolved, "model": "m"})


def test_fork_pattern_detects_repeated_failing_sequence():
    seq = ["read_file", "edit_file", "run_tests"]
    a = _traj_seq(seq, "acme-1")
    b = _traj_seq(seq, "acme-2")
    ctx = build_corpus([a, b])
    s = detect_fork_pattern(a, ctx)
    assert s.fired is True
    assert s.details["fork_pattern"] is not None
    assert len(s.details["shared_with"]) >= 1


def test_fork_pattern_quiet_for_unique_path():
    a = _traj_seq(["read_file", "edit_file", "run_tests"], "acme-1")
    b = _traj_seq(["search", "write_file", "submit"], "acme-2")
    ctx = build_corpus([a, b])
    assert detect_fork_pattern(a, ctx).fired is False


# --- emergent ---

def test_emergent_flags_unusual_tool_mix():
    typical = [_traj_seq(["read_file", "edit_file", "run_tests"], f"acme-{i}") for i in range(8)]
    weird = _traj_seq(["sudo"] * 12, "acme-99")
    ctx = build_corpus(typical + [weird])
    assert detect_emergent(weird, ctx).fired is True


def test_emergent_quiet_for_normal():
    typical = [_traj_seq(["read_file", "edit_file", "run_tests"], f"acme-{i}") for i in range(8)]
    ctx = build_corpus(typical)
    assert detect_emergent(typical[0], ctx).fired is False


# --- registry ---

def test_registry_has_all_six():
    names = [name for name, _ in DETECTORS]
    assert names == ["test_split", "reward_hack", "context_check",
                     "tool_volume", "fork_pattern", "emergent"]


def test_run_all_returns_signal_per_detector():
    t = _traj_patch("diff --git a/tests/test_x.py b/tests/test_x.py\n+++ b/tests/test_x.py\n+assert True\n")
    ctx = build_corpus([t])
    signals = run_all(t, ctx)
    assert set(signals.keys()) == {"test_split", "reward_hack", "context_check",
                                   "tool_volume", "fork_pattern", "emergent"}
