# Findings — Auditing Real RL Trajectories

> **Status:** preliminary on **n = 1,000** trajectories (the smoke run). A 5,000-trajectory
> run is in progress; numbers below will be refreshed when it completes.
> **Dataset:** `nebius/SWE-rebench-openhands-trajectories` (public, 67,074 trajectories).
> **Cost so far:** ~$0.10 (Gemini 2.5 Flash judge, 828 calls, 0 errors).

## Headline

**Shallow heuristics massively over-flag reward-hacking. An LLM judge that reads the actual
trajectory is more precise and corrects ~4 out of 5 of the heuristic's false alarms.**

You cannot trust surface signals (or aggregate eval metrics) to tell you whether an RL agent
gamed the reward. You have to read the trace — which is exactly the manual process this tool
automates, and exactly why teams that *don't* read their trajectories ship broken models.

## The numbers (n = 1,000; 828 judged)

**Ground truth** = the dataset's own split: `pred_passes_gen_tests` (the agent's self-test) vs
`resolved` (the real/gold SWE-bench outcome). A reward hack ≈ passes its own tests but is not
actually resolved.

| Detector | Precision | Recall | Notes |
|---|---|---|---|
| Heuristic reward-hack | **0.41** | 1.00 | catches everything but 59% of its flags are false |
| LLM judge (Gemini Flash) | **0.55** | 0.77 | more precise; misses some |

- **Recall 1.00 for the heuristic is partly by construction** — the `test_split` detector keys on
  the same self-vs-gold split that *defines* the gold label, so it trivially catches every gold
  reward-hack. The honest, interesting axis is **precision**, where the heuristic is weak (0.41).
- **The judge corrects the heuristic.** Of the **234** trajectories the heuristic flagged as
  reward-hacks but ground truth calls clean, the judge — reading the trace — said **NOT
  reward-hacking on 78%** (66% explicitly `CLEAN`). On the heuristic's *true* positives, the judge
  agreed it was a training/reward issue **77%** of the time.

**Why the heuristic over-flags:** signals like "the patch edits a test file" or "hardcodes a
return value" fire on plenty of trajectories that actually solved the task. The regex doesn't know
intent; the LLM, reading the surrounding trace, usually does.

## Failure distribution (heuristic, n = 1,000)

| Diagnosis | Share | Category | Share |
|---|---|---|---|
| TRAINING | 48% | Reward Hack | 49% |
| CLEAN | 19% | Stuck at Fork | 19% |
| BOTH | 19% | Clean | 19% |
| HARNESS | 7% | Context Gap | 7% |
| PRODUCT | 7% | Unclassified / Emergent | 7% |

The heuristic flags ~80% of trajectories as non-clean — itself a signal it is too aggressive,
corroborated by the precision result above.

## Honesty / limitations (read this before citing)

- **`resolved` rigorously validates only the reward-hack axis.** For HARNESS (context gap) and
  TRAINING (stuck-at-fork) there is no dataset ground-truth label, so the LLM judge is a *silver*
  standard there — we report agreement, not accuracy.
- **Heuristic-vs-judge raw agreement is 0.30 (Cohen's κ ≈ −0.02).** This looks alarming but is
  driven by two explainable artifacts, not random noise:
  1. **Category-space mismatch:** the heuristic emits `BOTH` 191× (23% of judged); the judge
     essentially never uses `BOTH` (1×). That alone forces ~191 guaranteed mismatches.
  2. **The heuristic's over-flagging** (above): where they disagree, the judge tends to side with
     ground truth.
  The deeper per-class analysis (the 78% correction figure) is the meaningful read, not the raw κ.
- **The reward-hack recall figure is partly tautological** (see above). We disclose this rather
  than headline a misleading "100% recall."

## So what

1. **Don't ship on aggregate eval.** A heuristic that looks reasonable ("flag agents that edit
   tests") is wrong 59% of the time it fires. Aggregate pass-rates hide this entirely.
2. **A cheap LLM judge adds real signal** over regex/heuristics — +14 precision points here, at
   ~$0.0001 per trajectory.
3. **The harness-vs-training-vs-product split matters:** ~7% of failures look like broken
   *environment* (context gaps), not broken *model* — retraining on those is wasted compute.

## Reproduce

```bash
python -m src.pipeline.cli audit --limit 1000 --control 0.1 --max-cost 5 \
  --work-dir <disk-path> --out-dir ./run1k --db ./run1k/exp.db
# → run1k/audit_run.json + run1k/validation_report.json
```
