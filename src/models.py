from __future__ import annotations
import re
from dataclasses import dataclass, field

_SYNTHETIC_TOOL_RE = re.compile(r"^\s*([a-zA-Z_][\w\-]*)\s*:")


@dataclass
class Trajectory:
    trajectory_id: str
    task_id: str
    task_description: str
    messages: list[dict]
    patch: str
    pred_passes_gen_tests: float
    pred_passes_gold_tests: float
    gen_tests_correct: float
    resolved: bool
    model: str
    repo: str
    cost: float
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "Trajectory":
        is_hf = "trajectory" in d and "messages" not in d
        messages = d["trajectory"] if is_hf else d.get("messages", [])

        if is_hf:
            resolved_raw = d.get("resolved", 0)
            gold = float(bool(resolved_raw))
            gen = float(d.get("pred_passes_gen_tests", 0.0))
            gen_correct = float(d.get("gen_tests_correct", 1.0))
            task_id = d.get("instance_id", d.get("trajectory_id", "unknown"))
            traj_id = d.get("trajectory_id", task_id)
            patch = d.get("model_patch", "")
            repo = d.get("repo", "")
            desc = d.get("task_description", "")
            resolved = bool(resolved_raw)
        else:
            tr = d.get("test_results", {})
            gen = float(tr.get("pred_passes_gen_tests", 0.0))
            gold = float(tr.get("pred_passes_gold_tests", float(bool(d.get("resolved", False)))))
            gen_correct = float(tr.get("gen_tests_correct", 1.0))
            task_id = d.get("task_id", d.get("trajectory_id", "unknown"))
            traj_id = d.get("trajectory_id", task_id)
            patch = d.get("patch", "")
            repo = d.get("repo", "")
            desc = d.get("task_description", "")
            resolved = bool(d.get("resolved", gold >= 1.0))

        return cls(
            trajectory_id=str(traj_id),
            task_id=str(task_id),
            task_description=desc,
            messages=messages,
            patch=patch,
            pred_passes_gen_tests=gen,
            pred_passes_gold_tests=gold,
            gen_tests_correct=gen_correct,
            resolved=resolved,
            model=d.get("model", "unknown"),
            repo=repo,
            cost=float(d.get("cost", 0.0)),
            raw=d,
        )


@dataclass
class DetectorSignal:
    name: str
    fired: bool
    score: float
    evidence: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


@dataclass
class Diagnosis:
    trajectory_id: str
    diagnosis: str
    failure_category: str
    confidence: float
    evidence: list[str]
    fix_recommendation: str
    signals: dict


@dataclass
class CorpusContext:
    tool_volume_mean: float
    tool_volume_stdev: float
    fork_index: dict
    tool_freq_centroid: dict
    tool_freq_stdev: dict
    n: int


def extract_tool_calls(traj: Trajectory) -> list[str]:
    """Ordered list of tool/function names invoked across the trajectory.
    Handles structured tool_calls (real HF data) and the synthetic
    'name: args' assistant-content convention from the spec."""
    names: list[str] = []
    for m in traj.messages:
        tcs = m.get("tool_calls") or []
        if tcs:
            for tc in tcs:
                fn = (tc.get("function") or {}).get("name")
                if fn:
                    names.append(fn)
            continue
        if m.get("role") == "assistant" and isinstance(m.get("content"), str):
            match = _SYNTHETIC_TOOL_RE.match(m["content"])
            if match:
                names.append(match.group(1))
    return names
