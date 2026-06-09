---
title: RL Trajectory Auditor
emoji: 🔬
colorFrom: red
colorTo: gray
sdk: static
app_file: index.html
pinned: false
---

# RL Trajectory Auditor — Explorer

Browse real RL agent trajectories audited for failure mode. Each card shows where a
cheap heuristic and an LLM judge disagree on *why* a run failed — and the judge,
reading the trace, is usually closer to ground truth.

Built on the public `nebius/SWE-rebench-openhands-trajectories` dataset; judged with
Gemini 2.5 Flash. The headline: heuristics over-flag reward-hacking (precision 0.41);
the judge is more precise (0.55) and corrects ~4 of 5 of the heuristic's false alarms.

**Static Space** — all data is pre-baked into `data/summary.json` + `data/cards.json`;
there is no backend and no API key. Regenerate the data with the project's
`python -m src.pipeline.export_explorer <audit_run.json> <staged-trajectory-dir> data`.

Method, detectors, and the full validation numbers are in the project README.
