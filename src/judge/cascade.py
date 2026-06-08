from __future__ import annotations

import random
from src.models import Trajectory, Diagnosis, JudgeVerdict
from src.judge.prompt import build_judge_prompt, JUDGE_SCHEMA, parse_verdict

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


def select_for_judging(trajs: list[Trajectory], diags: dict[str, Diagnosis],
                       control_ratio: float = 0.1, seed: int = 13) -> list[Trajectory]:
    flagged, clean = [], []
    for t in trajs:
        d = diags.get(t.trajectory_id)
        if d is not None and d.diagnosis != "CLEAN":
            flagged.append(t)
        else:
            clean.append(t)
    rng = random.Random(seed)
    k = int(len(clean) * control_ratio)
    control = rng.sample(clean, k) if k else []
    return flagged + control


def judge_cascade(trajs: list[Trajectory], diags: dict[str, Diagnosis], client,
                  guard: CostGuard, control_ratio: float = 0.1, seed: int = 13) -> dict:
    chosen = select_for_judging(trajs, diags, control_ratio, seed)
    verdicts: dict[str, JudgeVerdict] = {}
    judged = skipped = errors = 0
    for t in chosen:
        prompt = build_judge_prompt(t)
        est_tokens = _tokens_from_chars(len(prompt))
        if not guard.before_call(est_tokens):
            skipped += 1
            continue
        try:
            data = client.generate_json(prompt, JUDGE_SCHEMA)
            verdicts[t.trajectory_id] = parse_verdict(t.trajectory_id, data)
            judged += 1
        except Exception:
            errors += 1
        finally:
            guard.record(est_tokens)
    return {"verdicts": verdicts, "judged": judged, "skipped": skipped, "errors": errors,
            "total_tokens": getattr(client, "total_tokens", 0)}
