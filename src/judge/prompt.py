from __future__ import annotations
from src.models import Trajectory, JudgeVerdict

MAX_PROMPT_CHARS = 12000          # ~ token budget per trajectory
HEAD_MESSAGES = 6
TAIL_MESSAGES = 6
_VALID = {"HARNESS", "TRAINING", "PRODUCT", "BOTH", "CLEAN"}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "diagnosis": {"type": "string",
                      "enum": ["HARNESS", "TRAINING", "PRODUCT", "BOTH", "CLEAN"]},
        "failure_category": {"type": "string"},
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
        "offending_message_index": {"type": "integer"},
    },
    "required": ["diagnosis", "failure_category", "confidence", "reasoning"],
}

_INSTRUCTIONS = """You are auditing one reinforcement-learning agent trajectory.
Apply this 4-point diagnostic and return ONLY JSON:
1. Could a human solve this with the SAME context? No  -> HARNESS (broken environment).
2. Did it earn the score via a shortcut/hack?      Yes -> TRAINING (fix reward/rubric).
3. Does it fail at a repeated decision fork?       Yes -> TRAINING (add coverage).
4. Otherwise classify as PRODUCT, BOTH, or CLEAN.
diagnosis must be one of: HARNESS, TRAINING, PRODUCT, BOTH, CLEAN.
offending_message_index = 0-based index of the message that best exposes the failure
(or omit if none). Keep reasoning to 1-2 sentences."""


def _render_messages(messages: list[dict]) -> str:
    n = len(messages)
    if n <= HEAD_MESSAGES + TAIL_MESSAGES:
        chosen = list(enumerate(messages))
    else:
        head = list(enumerate(messages))[:HEAD_MESSAGES]
        tail = list(enumerate(messages))[n - TAIL_MESSAGES:]
        chosen = head + [(-1, {"role": "system", "content": f"... ({n - HEAD_MESSAGES - TAIL_MESSAGES} messages elided) ..."})] + tail
    lines = []
    for idx, m in chosen:
        tag = f"[{idx}]" if idx >= 0 else "[..]"
        content = (m.get("content") or "")[:600]
        lines.append(f"{tag} {m.get('role', '?')}: {content}")
    return "\n".join(lines)


def build_judge_prompt(traj: Trajectory) -> str:
    body = _render_messages(traj.messages)
    if len(body) > MAX_PROMPT_CHARS:
        body = body[:MAX_PROMPT_CHARS] + "\n... (truncated) ..."
    patch = (traj.patch or "")[:1500]
    return (
        f"{_INSTRUCTIONS}\n\n"
        f"TASK: {traj.task_description}\n"
        f"test_results: pred_passes_gen_tests={traj.pred_passes_gen_tests}, "
        f"pred_passes_gold_tests={traj.pred_passes_gold_tests}, resolved={traj.resolved}\n\n"
        f"MESSAGES:\n{body}\n\n"
        f"PATCH (truncated):\n{patch}\n"
    )


def parse_verdict(trajectory_id: str, data: dict) -> JudgeVerdict:
    diag = str(data.get("diagnosis", "")).strip().upper()
    if diag not in _VALID:
        diag = "CLEAN"
    omi = data.get("offending_message_index")
    omi = int(omi) if isinstance(omi, (int, float)) else None
    try:
        conf = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    return JudgeVerdict(
        trajectory_id=trajectory_id,
        diagnosis=diag,
        failure_category=str(data.get("failure_category", "Unknown")) or "Unknown",
        confidence=conf,
        reasoning=str(data.get("reasoning", "")),
        offending_message_index=omi,
        raw=data,
    )
