from __future__ import annotations
from dataclasses import asdict
from src.models import Diagnosis

_BAR_W = 18


def diagnosis_to_dict(d: Diagnosis) -> dict:
    return asdict(d)


def _bar(count: int, total: int) -> str:
    filled = round(_BAR_W * count / total) if total else 0
    return "█" * filled + "░" * (_BAR_W - filled)


def render_terminal(rep: dict) -> str:
    total = rep["total"] or 1
    lines = [f"FAILURE DISTRIBUTION ({rep['total']} trajectories audited):"]
    for cat, n in sorted(rep["categories"].items(), key=lambda x: -x[1]):
        pct = 100 * n / total
        lines.append(f"  {cat:<20} {_bar(n, total)} {n} ({pct:.0f}%)")
    lines.append("")
    lines.append("HARNESS vs TRAINING SPLIT:")
    labels = {"HARNESS": "Harness problems", "TRAINING": "Training problems",
              "PRODUCT": "Product issues", "BOTH": "Both/Unclear", "CLEAN": "Clean"}
    for key, label in labels.items():
        n = rep["splits"].get(key, 0)
        lines.append(f"  {label:<20} {n} ({100*n/total:.0f}%)")
    lines.append("")
    lines.append("TOP PRIORITY FIXES:")
    for i, fx in enumerate(rep["top_fixes"], 1):
        lines.append(f"  {i}. {fx['category']}: {fx['count']} trajectories")
        lines.append(f"     → {fx['fix']}")
    if rep.get("wasted_cost"):
        lines.append("")
        lines.append("COMPUTE IMPACT:")
        lines.append(f"  Wasted trajectories: {rep['wasted']} ({100*rep['wasted']/total:.0f}%)")
        lines.append(f"  Est. cost of dirty trajectories: ${rep['wasted_cost']}")
    return "\n".join(lines)
