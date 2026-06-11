from __future__ import annotations
import argparse
import sys
from src.judge.cascade import CostGuard
from src.pipeline.scale import run_audit_at_scale


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="audit-scale",
                                description="Audit N real trajectories with the judge cascade")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit", help="run the scale audit")
    a.add_argument("--limit", type=int, default=5000)
    a.add_argument("--control", type=float, default=0.1, help="control-sample ratio of clean traces")
    a.add_argument("--max-cost", type=float, default=12.0, help="hard USD ceiling")
    a.add_argument("--max-calls", type=int, default=0, help="0 = default to --limit")
    a.add_argument("--work-dir", default="trajectories")
    a.add_argument("--out-dir", default=".")
    a.add_argument("--db", default="auditor.db")
    a.add_argument("--dry-run", action="store_true", help="print cost estimate and exit")
    return p


def run_cli(args, row_source=None, client=None) -> int:
    max_calls = args.max_calls or args.limit
    guard = CostGuard(max_calls=max_calls, max_input_tokens=10**9, max_cost_usd=args.max_cost)
    if args.dry_run:
        est = run_audit_at_scale(limit=args.limit, control_ratio=args.control, guard=guard,
                                 client=client, row_source=row_source, work_dir=args.work_dir,
                                 out_dir=args.out_dir, db_path=None, dry_run=True)
        print("=== DRY RUN ===")
        print(f"  trajectories loaded : {est['n']}")
        print(f"  to judge            : {est['to_judge']}")
        print(f"  est input tokens    : {est['est_input_tokens']}")
        print(f"  est cost (USD)      : ${est['est_cost_usd']:.4f}  (ceiling ${args.max_cost})")
        print("  No API calls made. Re-run without --dry-run to execute.")
        return 0
    res = run_audit_at_scale(limit=args.limit, control_ratio=args.control, guard=guard,
                             client=client, row_source=row_source, work_dir=args.work_dir,
                             out_dir=args.out_dir, db_path=args.db, dry_run=False)
    js = res["judge_stats"]
    print(f"[OK] audited {res['n']} trajectories | judged {js['judged']}, "
          f"skipped {js['skipped']}, errors {js['errors']}")
    rh = res["validation"]["reward_hack"]
    ja = res["validation"]["judge_agreement"]
    print(f"[OK] reward-hack detector: precision={rh['precision']:.2f} recall={rh['recall']:.2f} "
          f"(n={rh['n_evaluated']})")
    print(f"[OK] heuristic-vs-judge agreement={ja['agreement']:.2f} kappa={ja['kappa']:.2f} (n={ja['n']})")
    print(f"[OK] wrote audit_run.json + validation_report.json to {args.out_dir}")
    return 0


def main(argv=None) -> int:
    return run_cli(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
