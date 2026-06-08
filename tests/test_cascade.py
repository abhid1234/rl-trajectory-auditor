import pytest
from src.judge.cascade import CostGuard, CHARS_PER_TOKEN, FLASH_USD_PER_1K_TOKENS


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
