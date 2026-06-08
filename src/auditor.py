from __future__ import annotations
import argparse
import json
import sys
from src.loader import load_trajectories
from src.corpus import build_corpus
from src.detectors import run_all
from src.framework.four_point_diagnostic import diagnose
from src.report.aggregate import aggregate
from src.report.format import render_terminal, diagnosis_to_dict
from src.db import DiagnosisDB


def run_audit(path: str, db_path: str | None = None):
    trajs = load_trajectories(path)
    corpus = build_corpus(trajs)
    diags = [diagnose(t, run_all(t, corpus)) for t in trajs]
    avg_cost = (sum(t.cost for t in trajs) / len(trajs)) if trajs else 0.0
    report = aggregate(diags, cost_per_traj=avg_cost)
    if db_path:
        db = DiagnosisDB(db_path)
        for d in diags:
            db.save(d)
        db.close()
    return diags, report


def _cmd_audit(args) -> int:
    print(f"[OK] Loading trajectories from {args.path} ...")
    diags, report = run_audit(args.path, db_path=args.db)
    print(f"[OK] Loaded {report['total']} trajectories")
    print("[OK] Running 6 detectors...")
    print("[OK] Generating aggregate report...\n")
    print(render_terminal(report))
    if args.json:
        with open(args.json, "w") as f:
            json.dump({"diagnoses": [diagnosis_to_dict(d) for d in diags], "report": report},
                      f, indent=2)
        print(f"\n[OK] Per-trajectory diagnoses written to {args.json}")
    return 0


def _cmd_ingest(args) -> int:
    from src.ingest_hf import ingest
    n = ingest(args.out, limit=args.limit)
    print(f"[OK] Wrote {n} normalized trajectories to {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="auditor", description="RL trajectory auditor")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="audit a directory of trajectory JSON files")
    a.add_argument("path")
    a.add_argument("--json", help="write per-trajectory diagnoses JSON here")
    a.add_argument("--db", help="SQLite path to persist diagnoses")
    a.set_defaults(func=_cmd_audit)

    g = sub.add_parser("ingest-hf", help="pull real trajectories from HuggingFace")
    g.add_argument("--out", default="trajectories", help="output dir")
    g.add_argument("--limit", type=int, default=100, help="rows to fetch")
    g.set_defaults(func=_cmd_ingest)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
