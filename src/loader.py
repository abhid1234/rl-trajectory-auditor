from __future__ import annotations
import json
from pathlib import Path
from src.models import Trajectory


def load_trajectories(path: str) -> list[Trajectory]:
    """Load every .json/.jsonl file under `path`. A .json file may hold a
    single object or a JSON array. A .jsonl file holds one object per line."""
    p = Path(path)
    files = [p] if p.is_file() else sorted([*p.glob("*.json"), *p.glob("*.jsonl")])
    out: list[Trajectory] = []
    for f in files:
        text = f.read_text()
        if f.suffix == ".jsonl":
            for line in text.splitlines():
                line = line.strip()
                if line:
                    out.append(Trajectory.from_dict(json.loads(line)))
        else:
            data = json.loads(text)
            records = data if isinstance(data, list) else [data]
            out.extend(Trajectory.from_dict(r) for r in records)
    return out
