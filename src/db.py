from __future__ import annotations
import json
import sqlite3
from src.models import Diagnosis

_SCHEMA = """
CREATE TABLE IF NOT EXISTS diagnoses (
    trajectory_id TEXT,
    diagnosis TEXT,
    failure_category TEXT,
    confidence REAL,
    evidence TEXT,
    fix_recommendation TEXT,
    signals TEXT
);
"""


class DiagnosisDB:
    def __init__(self, path: str = "auditor.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    def save(self, d: Diagnosis) -> None:
        self.conn.execute(
            "INSERT INTO diagnoses VALUES (?,?,?,?,?,?,?)",
            (d.trajectory_id, d.diagnosis, d.failure_category, d.confidence,
             json.dumps(d.evidence), d.fix_recommendation, json.dumps(d.signals)),
        )
        self.conn.commit()

    def all(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM diagnoses")]

    def category_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT failure_category, COUNT(*) c FROM diagnoses GROUP BY failure_category")
        return {r["failure_category"]: r["c"] for r in rows}

    def close(self) -> None:
        self.conn.close()
