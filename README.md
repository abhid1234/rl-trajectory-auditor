# RL Trajectory Auditor

Audit RL training trajectories and automatically classify each failure as a
**harness bug, reward hack, training gap, or product issue** — turning a manual
~90-minute expert review into seconds per trajectory.

> Teams ship broken models because nobody reads their trajectories. This reads them.

**🔬 Live demo — The Inspector:** https://abhid1234-rl-trajectory-auditor.static.hf.space
— step through 200 fully-loaded real trajectories from a **5,000-trajectory audit**, watch the
detectors fire live, or drop in your own trajectory JSON (it never leaves your browser).

**📊 The finding:** heuristics over-flag reward-hacking (precision **0.43**); an LLM judge that
reads the trace overturns **75%** of those false alarms. Full numbers, method, and caveats in
[`docs/FINDINGS.md`](docs/FINDINGS.md).

## Quickstart

```bash
git clone https://github.com/abhid1234/rl-trajectory-auditor && cd rl-trajectory-auditor
python demo/sample_run.py                 # run against bundled fixtures
python -m src.auditor audit tests/fixtures --json out.json
```

Pull real trajectories (stdlib only, via HF datasets-server REST API):

```bash
python -m src.auditor ingest-hf --out trajectories --limit 100
python -m src.auditor audit trajectories
```

## What it does

1. Loads trajectory JSON (spec flat format **or** HF `nebius/SWE-rebench-openhands-trajectories`).
2. Runs 6 detectors (see below).
3. Fuses signals through a 4-point diagnostic into HARNESS / TRAINING / PRODUCT / BOTH / CLEAN.
4. Prints an aggregate priority-fix report and writes per-trajectory diagnoses.

## The 6 detectors

| # | Detector | Catches |
|---|----------|---------|
| 1 | reward_hack | hardcoded returns, test-file edits, self-pass/gold-fail |
| 2 | fork_pattern | same failing tool sequence repeated across traces |
| 3 | context_check | missing files/config/env the harness never supplied |
| 4 | test_split | model self-eval = 1.0 but gold = 0.0 |
| 5 | tool_volume | anomalously high/low tool-call count |
| 6 | emergent | statistical outlier in action patterns (stretch) |

## The 4-point diagnostic

1. Could a human solve this with the same context? **No → HARNESS** (fix env).
2. Did it earn the score via a shortcut? **Yes → TRAINING** (fix rubric).
3. Does it fail at the same fork across traces? **Yes → TRAINING** (add coverage).
4. Otherwise → PRODUCT / BOTH / CLEAN.

## Auriel's 10-point eyeballing checklist (codified)

Each item maps to the detector that automates it (see `src/framework/checklist.py`):

| # | Question | Implemented by |
|---|----------|----------------|
| 1 | Does the model's self-eval disagree with the gold outcome? | `test_split` |
| 2 | Did it earn the score via a shortcut (hardcode / edit tests)? | `reward_hack` |
| 3 | Could a human solve this with only the provided context? | `context_check` |
| 4 | Is the tool-call volume anomalous for the task? | `tool_volume` |
| 5 | Does it fail at the same fork across similar traces? | `fork_pattern` |
| 6 | Are there statistically anomalous (emergent) action patterns? | `emergent` |
| 7 | Did the harness present stale or inconsistent state? | `context_check` |
| 8 | Is the produced patch trivially small vs the claimed work? | `reward_hack` |
| 9 | Did the model give up early (under-uses tools)? | `tool_volume` |
| 10 | Is the failure product-routing rather than model error? | `manual` |

## Output

Per-trajectory JSON matches the spec schema (`trajectory_id`, `diagnosis`,
`failure_category`, `confidence`, `evidence`, `fix_recommendation`, `signals`).
The aggregate report shows failure distribution, harness-vs-training split, and
the top-3 priority fixes.

```
FAILURE DISTRIBUTION (6 trajectories audited):
  Stuck at Fork        ██████░░░░░░░░░░░░ 2 (33%)
  Reward Hack          ███░░░░░░░░░░░░░░░ 1 (17%)
  Context Gap          ███░░░░░░░░░░░░░░░ 1 (17%)
  ...

HARNESS vs TRAINING SPLIT:
  Harness problems     1 (17%)  → fix env before retrain
  Training problems    3 (50%)  → fix reward + add coverage
  ...
```

## Requirements

Python 3.12+. Standard library only — nothing to `pip install` to run. `pytest`
for the test suite (`python -m pytest`).

## MCP server

The auditor ships as an MCP stdio server (`src/mcp_server.py`, stdlib only).
Register it with Claude Code from the repo directory:

    claude mcp add rl-audit -- python3 -m src.mcp_server

It exposes one tool, `audit_trajectory`, which takes a trajectory as a JSON
string (`trajectory_json`) or a path to a `.json` file (`file_path`), runs all
detectors plus the 4-point diagnostic, and returns the HARNESS / TRAINING /
PRODUCT / BOTH / CLEAN verdict with evidence and a fix recommendation.

## CI gate (GitHub Action)

Fail CI when a trajectory batch shows too many harness failures or reward
hacks — so you never retrain on dirty data.

```yaml
- uses: abhid1234/rl-trajectory-auditor@main
  with:
    path: trajectories/
    max-harness-pct: "20"
    max-reward-hack-pct: "30"
```

## References

- Auriel Wright — https://aurielws.github.io/posts/rl-pet-peeves-part-1/
- Trajectory data — `nebius/SWE-rebench-openhands-trajectories` on HuggingFace
