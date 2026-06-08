from __future__ import annotations
from collections import Counter
from src.models import Diagnosis

# top fix templates keyed by category
_TOP_FIXES = {
    "Reward Hack": "Add adversarial test variants; strengthen rubric to check real correctness.",
    "Stuck at Fork": "Add training coverage for the repeated failing decision point.",
    "Context Gap": "Fix the harness/env to supply missing context before the next run.",
    "Emergent/Unknown": "Inspect product routing / action policy for anomalous behavior.",
}


def aggregate(diags: list[Diagnosis], cost_per_traj: float = 0.0) -> dict:
    cats = Counter(d.failure_category for d in diags)
    splits = Counter(d.diagnosis for d in diags)
    total = len(diags)
    wasted = sum(1 for d in diags if d.diagnosis != "CLEAN")
    ranked = [c for c, _ in cats.most_common() if c not in ("Clean",)]
    top_fixes = [{"category": c, "count": cats[c], "fix": _TOP_FIXES.get(c, "Manual review.")}
                 for c in ranked[:3]]
    return {
        "total": total,
        "categories": dict(cats),
        "splits": dict(splits),
        "clean": cats.get("Clean", 0),
        "wasted": wasted,
        "wasted_cost": round(wasted * cost_per_traj, 2),
        "top_fixes": top_fixes,
    }
