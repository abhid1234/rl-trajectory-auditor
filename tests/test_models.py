import json
from pathlib import Path
from src.models import Trajectory, extract_tool_calls
from src.loader import load_trajectories

SPEC_FORMAT = {
    "task_id": "sdf-xarray-34",
    "task_description": "Fix ValueError...",
    "messages": [
        {"role": "system", "content": "..."},
        {"role": "user", "content": "Fix ValueError..."},
        {"role": "assistant", "content": "execute_bash: ls"},
        {"role": "tool", "content": "setup.py tests/ ..."},
    ],
    "patch": "diff --git a/...",
    "test_results": {"pred_passes_gen_tests": 1.0, "pred_passes_gold_tests": 0.0},
    "resolved": False,
    "model": "openhands-agent",
    "total_messages": 185,
    "cost": 0.42,
}

HF_FORMAT = {
    "trajectory_id": "chatcmpl-27dd",
    "instance_id": "PlasmaFAIR__sdf-xarray-24",
    "repo": "PlasmaFAIR/sdf-xarray",
    "trajectory": [
        {"role": "user", "content": "Fix it", "name": None, "tool_call_id": None, "tool_calls": []},
        {"role": "assistant", "content": "", "name": None, "tool_call_id": None,
         "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "execute_bash", "arguments": '{"command": "ls"}'}}]},
        {"role": "tool", "content": "setup.py", "name": "execute_bash", "tool_call_id": "c1", "tool_calls": []},
    ],
    "model_patch": "diff --git a/...",
    "exit_status": "submitted",
    "resolved": 0,
    "gen_tests_correct": 0.0,
    "pred_passes_gen_tests": 1.0,
}


def test_from_spec_format():
    t = Trajectory.from_dict(SPEC_FORMAT)
    assert t.task_id == "sdf-xarray-34"
    assert t.pred_passes_gen_tests == 1.0
    assert t.pred_passes_gold_tests == 0.0
    assert t.resolved is False
    assert len(t.messages) == 4


def test_from_hf_format():
    t = Trajectory.from_dict(HF_FORMAT)
    assert t.task_id == "PlasmaFAIR__sdf-xarray-24"
    assert t.pred_passes_gen_tests == 1.0
    assert t.pred_passes_gold_tests == 0.0   # from resolved=0
    assert t.resolved is False
    assert t.gen_tests_correct == 0.0


def test_extract_tool_calls_both_shapes():
    assert extract_tool_calls(Trajectory.from_dict(SPEC_FORMAT)) == ["execute_bash"]
    assert extract_tool_calls(Trajectory.from_dict(HF_FORMAT)) == ["execute_bash"]


def test_load_dir(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps(SPEC_FORMAT))
    (tmp_path / "b.jsonl").write_text(json.dumps(HF_FORMAT) + "\n")
    trajs = load_trajectories(str(tmp_path))
    assert len(trajs) == 2
    ids = sorted(t.task_id for t in trajs)
    assert ids == ["PlasmaFAIR__sdf-xarray-24", "sdf-xarray-34"]


def test_load_json_array(tmp_path):
    (tmp_path / "many.json").write_text(json.dumps([SPEC_FORMAT, SPEC_FORMAT]))
    assert len(load_trajectories(str(tmp_path))) == 2
