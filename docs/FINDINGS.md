# Findings — Auditing 5,000 Real RL Trajectories

> **Scale:** 5,000 trajectories audited; **4,453 judged** by the LLM (flagged + control), 3 errors.
> **Dataset:** `nebius/SWE-rebench-openhands-trajectories` (public, 67,074 trajectories).
> **Judge:** Gemini 2.5 Flash, via stdlib REST.

## Headline

**Shallow heuristics massively over-flag reward-hacking. An LLM judge that reads the actual
trajectory overturns ~3 of every 4 of those false alarms — toward ground truth.**

You cannot trust surface signals (or aggregate eval metrics) to tell you whether an RL agent
gamed the reward. You have to read the trace — the manual process this tool automates, and the
reason teams that *don't* read their trajectories ship broken models. And even the LLM judge is
no silver bullet: trajectory auditing is genuinely hard.

## The numbers (n = 5,000; 4,453 judged)

**Ground truth** = the dataset's own split: `pred_passes_gen_tests` (the agent's self-test) vs
`resolved` (the real/gold SWE-bench outcome). A reward hack ≈ passes its own tests but is not
actually resolved.

- **Heuristic reward-hack detector: precision 0.43, recall 1.00** (n = 3,285 evaluable).
  Recall 1.00 is **partly by construction** — the `test_split` detector keys on the same
  self-vs-gold split that *defines* the gold label, so it trivially catches every gold reward-hack.
  The honest, interesting axis is **precision: 0.43**, i.e. **57% of its reward-hack flags are
  false** (1,119 trajectories flagged as hacks that ground truth calls clean).
- **The judge corrects the heuristic.** Of those **1,119 false positives**, the judge — reading
  the trace — sided with ground truth (NOT reward-hacking) on **75%**. That is the robust,
  defensible result, stable from the 1k smoke (78%) to the full 5k (75%).
- **The judge is not magic.** On the same reward-hack axis its own precision is only ~0.46 —
  better than the heuristic, but modest. The lesson is not "LLM judge = truth"; it's "surface
  signals are unreliable, and reading the trace helps."

## Failure distribution (heuristic, n = 5,000)

| Category | Share |
|---|---|
| Reward Hack | 48% |
| Stuck at Fork | 36% |
| Clean | 12% |
| Context Gap | 2% |
| Unclassified / Emergent | 2% |

**Scale changes the picture.** At 1,000 trajectories, *Stuck at Fork* was 19%; at 5,000 it is
**36%**. The reason is mechanical and worth knowing: the fork detector only fires when the *same*
failing tool sequence appears in **≥2 traces from the same repo**, so a denser corpus surfaces far
more repeated forks. It's a reminder that some "failure rates" are artifacts of corpus size, not
the model — exactly the kind of thing you only catch by auditing at scale.

## Honesty / limitations (read before citing)

- **`resolved` rigorously validates only the reward-hack axis.** HARNESS (context gap) and the
  fork axis have no dataset ground-truth label, so the LLM judge is a *silver* standard there —
  we report agreement, not accuracy.
- **Heuristic-vs-judge raw agreement is 0.33 (Cohen's κ ≈ −0.03).** This looks alarming but is
  driven by explainable artifacts, not noise: (1) a **category-space mismatch** — the heuristic
  emits `BOTH` often, the judge essentially never; (2) the heuristic's **over-flagging**, where
  the judge tends to side with ground truth. The per-class read (the 75% correction) is the
  meaningful number, not the raw κ.
- **Reward-hack recall is partly tautological** (see above) — disclosed rather than headlined.

## So what

1. **Don't ship on aggregate eval.** A reasonable-sounding heuristic ("flag agents that edit
   tests") is wrong 57% of the time it fires. Aggregate pass-rates hide this entirely.
2. **A cheap LLM judge adds real signal** over regex/heuristics — but it is a second opinion, not
   an oracle. Use it to *triage* what a human should read, not to replace reading.
3. **Audit at scale or be fooled by artifacts** — the 19%→36% fork swing is invisible at small N.

## Reproduce

```bash
python -m src.pipeline.cli audit --limit 5000 --control 0.1 \
  --work-dir <disk-path> --out-dir ./run5k --db ./run5k/exp.db
python -m src.pipeline.export_explorer --full run5k/audit_run.json <disk-path> explorer/data
# → run5k/{audit_run,validation_report}.json + the interactive explorer dataset
```
