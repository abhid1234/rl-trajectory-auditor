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

**Inspect your own:** the **⬆ Inspect yours** button takes your trajectory JSON
(OpenAI-style messages or an HF SWE-rebench row) and runs the heuristic audit,
narration, and step-through **entirely in your browser** — nothing is uploaded.
The LLM-judge second opinion runs via the project CLI.

**Static Space** — all data is pre-baked into `data/summary.json` + `data/index.json`
+ `data/traj/`; there is no backend and no API key. Regenerate the data with the
project's `python -m src.pipeline.export_explorer --full <audit_run.json> <staged-dir> data`.

Code, method, and the full validation numbers: https://github.com/abhid1234/rl-trajectory-auditor
