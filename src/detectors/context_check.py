from __future__ import annotations
import re
from src.models import Trajectory, DetectorSignal, CorpusContext

NAME = "context_check"

_MISSING_PATTERNS = [
    re.compile(r"No such file or directory", re.I),
    re.compile(r"command not found", re.I),
    re.compile(r"ModuleNotFoundError", re.I),
    re.compile(r"Permission denied", re.I),
    re.compile(r"(could not|cannot|unable to) (find|locate|open|read)\b", re.I),
    re.compile(r"\bENOENT\b"),
    re.compile(r"FileNotFoundError", re.I),
    re.compile(r"missing (config|configuration|credential|environment variable|env var)", re.I),
]


def detect_context_check(traj: Trajectory, corpus: CorpusContext | None) -> DetectorSignal:
    hits: list[str] = []
    for m in traj.messages:
        if m.get("role") not in ("tool", "user"):
            continue
        content = m.get("content") or ""
        for pat in _MISSING_PATTERNS:
            found = pat.search(content)
            if found:
                snippet = content.strip().splitlines()[0][:120] if content.strip() else found.group(0)
                hits.append(f"missing-context marker: {snippet}")
                break
    if hits and not traj.resolved:
        return DetectorSignal(NAME, True, min(0.5 + 0.15 * len(hits), 0.95),
                              hits[:5], {"context_complete": False, "marker_count": len(hits)})
    return DetectorSignal(NAME, False, 0.0, [], {"context_complete": True, "marker_count": len(hits)})
