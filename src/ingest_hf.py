"""Pull real trajectories from nebius/SWE-rebench-openhands-trajectories using only
the standard library, via the HF datasets-server /rows REST API (JSON, no parquet)."""
from __future__ import annotations
import json
import os
import urllib.parse
import urllib.request

DATASET = "nebius/SWE-rebench-openhands-trajectories"
BASE = "https://datasets-server.huggingface.co/rows"
PAGE = 100  # API max per request


def _f(value, default: float) -> float:
    """Coerce a possibly-null/missing numeric field to float."""
    return float(value) if value is not None else default


def normalize_row(api_row: dict) -> dict:
    """Map one datasets-server row into the spec's flat input format."""
    r = api_row.get("row", api_row)
    resolved = bool(r.get("resolved") or 0)
    return {
        "trajectory_id": r.get("trajectory_id") or r.get("instance_id") or "unknown",
        "task_id": r.get("instance_id") or r.get("trajectory_id") or "unknown",
        "task_description": "",
        "repo": r.get("repo") or "",
        "messages": r.get("trajectory") or [],
        "patch": r.get("model_patch") or "",
        "test_results": {
            "pred_passes_gen_tests": _f(r.get("pred_passes_gen_tests"), 0.0),
            "pred_passes_gold_tests": float(resolved),
            "gen_tests_correct": _f(r.get("gen_tests_correct"), 1.0),
        },
        "resolved": resolved,
        "model": "openhands-agent",
        "cost": 0.0,
    }


def _fetch_page(offset: int, length: int) -> list[dict]:
    qs = urllib.parse.urlencode(
        {"dataset": DATASET, "config": "default", "split": "train",
         "offset": offset, "length": length})
    req = urllib.request.Request(f"{BASE}?{qs}", headers={"User-Agent": "rl-traj-auditor"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read()).get("rows", [])


def ingest(out_dir: str, limit: int = 100) -> int:
    os.makedirs(out_dir, exist_ok=True)
    written = 0
    offset = 0
    while written < limit:
        batch = _fetch_page(offset, min(PAGE, limit - written))
        if not batch:
            break
        for row in batch:
            norm = normalize_row(row)
            path = os.path.join(out_dir, f"{norm['task_id'].replace('/', '__')}_{written}.json")
            with open(path, "w") as f:
                json.dump(norm, f)
            written += 1
        offset += len(batch)
    return written
