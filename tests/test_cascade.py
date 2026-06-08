import pytest
from src.judge.cascade import CostGuard, CHARS_PER_TOKEN, FLASH_USD_PER_1K_TOKENS
from src.models import Trajectory, Diagnosis
from src.judge.cascade import select_for_judging, judge_cascade


def test_estimate_reports_calls_tokens_cost():
    prompts = ["x" * (4 * CHARS_PER_TOKEN) for _ in range(10)]  # ~4 tokens each
    guard = CostGuard(max_calls=100, max_input_tokens=10_000, max_cost_usd=15.0)
    est = guard.estimate(prompts)
    assert est["calls"] == 10
    assert est["input_tokens"] == 40
    assert est["cost_usd"] == pytest.approx(40 / 1000 * FLASH_USD_PER_1K_TOKENS, rel=1e-6)


def test_before_call_blocks_on_call_ceiling():
    guard = CostGuard(max_calls=2, max_input_tokens=10**9, max_cost_usd=15.0)
    assert guard.before_call(10) is True
    guard.record(10)
    assert guard.before_call(10) is True
    guard.record(10)
    assert guard.before_call(10) is False  # 3rd call blocked


def test_before_call_blocks_on_token_ceiling():
    guard = CostGuard(max_calls=100, max_input_tokens=50, max_cost_usd=15.0)
    assert guard.before_call(40) is True
    guard.record(40)
    assert guard.before_call(40) is False   # would exceed 50


def test_before_call_blocks_on_cost_ceiling():
    # cost ceiling of 0 blocks everything
    guard = CostGuard(max_calls=10**9, max_input_tokens=10**9, max_cost_usd=0.0)
    assert guard.before_call(1) is False


def _t(tid, diag):
    traj = Trajectory.from_dict({"task_id": tid, "trajectory_id": tid,
        "messages": [{"role": "user", "content": "hi"}],
        "patch": "", "test_results": {"pred_passes_gen_tests": 0.0, "pred_passes_gold_tests": 0.0},
        "resolved": False, "model": "m"})
    d = Diagnosis(tid, diag, "cat", 0.5, [], "fix", {})
    return traj, d


def test_select_includes_all_flagged_plus_control():
    items = [_t(f"f{i}", "TRAINING") for i in range(4)] + [_t(f"c{i}", "CLEAN") for i in range(10)]
    trajs = [t for t, _ in items]
    diags = {t.trajectory_id: d for t, d in items}
    chosen = select_for_judging(trajs, diags, control_ratio=0.5, seed=1)
    flagged_ids = {f"f{i}" for i in range(4)}
    chosen_ids = {t.trajectory_id for t in chosen}
    assert flagged_ids.issubset(chosen_ids)              # all flagged judged
    n_control = len(chosen_ids - flagged_ids)
    assert n_control == 5                                # 50% of 10 clean


def test_select_is_deterministic_with_seed():
    items = [_t(f"c{i}", "CLEAN") for i in range(10)]
    trajs = [t for t, _ in items]
    diags = {t.trajectory_id: d for t, d in items}
    a = {t.trajectory_id for t in select_for_judging(trajs, diags, control_ratio=0.3, seed=7)}
    b = {t.trajectory_id for t in select_for_judging(trajs, diags, control_ratio=0.3, seed=7)}
    assert a == b


class _StubClient:
    def __init__(self):
        self.total_tokens = 0
        self.last_usage = {}
        self.seen = []

    def generate_json(self, prompt, schema):
        self.seen.append(prompt)
        self.total_tokens += 50
        return {"diagnosis": "TRAINING", "failure_category": "Reward Hack",
                "confidence": 0.8, "reasoning": "hack", "offending_message_index": 0}


def test_judge_cascade_returns_verdicts():
    items = [_t("f0", "TRAINING"), _t("f1", "TRAINING")]
    trajs = [t for t, _ in items]
    diags = {t.trajectory_id: d for t, d in items}
    guard = CostGuard(max_calls=10, max_input_tokens=10**9, max_cost_usd=15.0)
    result = judge_cascade(trajs, diags, _StubClient(), guard, control_ratio=0.0, seed=1)
    assert set(result["verdicts"].keys()) == {"f0", "f1"}
    assert result["verdicts"]["f0"].diagnosis == "TRAINING"
    assert result["judged"] == 2
    assert result["skipped"] == 0


def test_judge_cascade_respects_cost_guard():
    items = [_t(f"f{i}", "TRAINING") for i in range(5)]
    trajs = [t for t, _ in items]
    diags = {t.trajectory_id: d for t, d in items}
    guard = CostGuard(max_calls=2, max_input_tokens=10**9, max_cost_usd=15.0)
    result = judge_cascade(trajs, diags, _StubClient(), guard, control_ratio=0.0, seed=1)
    assert result["judged"] == 2
    assert result["skipped"] == 3


class _RaisingClient:
    total_tokens = 0

    def generate_json(self, prompt, schema):
        raise RuntimeError("boom")


def test_judge_cascade_counts_errors_and_still_records_budget():
    items = [_t(f"f{i}", "TRAINING") for i in range(3)]
    trajs = [t for t, _ in items]
    diags = {t.trajectory_id: d for t, d in items}
    guard = CostGuard(max_calls=10, max_input_tokens=10**9, max_cost_usd=15.0)
    result = judge_cascade(trajs, diags, _RaisingClient(), guard, control_ratio=0.0, seed=1)
    assert result["errors"] == 3
    assert result["judged"] == 0
    assert guard.calls == 3                 # finally recorded each attempted call
    assert result["billed_tokens"] == 0     # client tracked 0
