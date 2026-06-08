"""Run the auditor against the bundled fixtures and print the report."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.auditor import run_audit
from src.report.format import render_terminal

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures"
    diags, report = run_audit(target)
    print(f"[OK] Loaded {report['total']} trajectories")
    print("[OK] Running 6 detectors...")
    print("[OK] Generating aggregate report...\n")
    print(render_terminal(report))
    print("\nPER-TRAJECTORY:")
    for d in diags:
        print(f"  {d.trajectory_id:<24} {d.diagnosis:<8} {d.failure_category} ({d.confidence})")
