from __future__ import annotations

CHARS_PER_TOKEN = 4                     # rough heuristic for estimation only
FLASH_USD_PER_1K_TOKENS = 0.0003        # conservative Flash input price ($0.30 / 1M tokens)


def _tokens_from_chars(n_chars: int) -> int:
    return n_chars // CHARS_PER_TOKEN


class CostGuard:
    def __init__(self, max_calls: int, max_input_tokens: int, max_cost_usd: float):
        self.max_calls = max_calls
        self.max_input_tokens = max_input_tokens
        self.max_cost_usd = max_cost_usd
        self.calls = 0
        self.input_tokens = 0

    def estimate(self, prompts: list[str]) -> dict:
        toks = sum(_tokens_from_chars(len(p)) for p in prompts)
        return {
            "calls": len(prompts),
            "input_tokens": toks,
            "cost_usd": toks / 1000 * FLASH_USD_PER_1K_TOKENS,
        }

    def _cost(self, tokens: int) -> float:
        return tokens / 1000 * FLASH_USD_PER_1K_TOKENS

    def before_call(self, next_tokens: int) -> bool:
        if self.calls + 1 > self.max_calls:
            return False
        if self.input_tokens + next_tokens > self.max_input_tokens:
            return False
        if self._cost(self.input_tokens + next_tokens) > self.max_cost_usd:
            return False
        return True

    def record(self, tokens: int) -> None:
        self.calls += 1
        self.input_tokens += tokens
