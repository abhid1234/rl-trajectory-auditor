"""Tests for the MCP stdio server (src/mcp_server.py)."""
import json
import subprocess
import sys
from pathlib import Path

from src.mcp_server import handle

FIXTURES = Path(__file__).parent / "fixtures"


def test_initialize():
    resp = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    result = resp["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "rl-trajectory-auditor"


def test_tools_list():
    resp = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tools = resp["result"]["tools"]
    assert len(tools) == 1
    tool = tools[0]
    assert tool["name"] == "audit_trajectory"
    assert "inputSchema" in tool


def test_tools_call_trajectory_json_reward_hack():
    traj_str = (FIXTURES / "reward_hack.json").read_text()
    resp = handle({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "audit_trajectory",
                   "arguments": {"trajectory_json": traj_str}},
    })
    content = resp["result"]["content"]
    payload = json.loads(content[0]["text"])
    assert payload["diagnosis"] == "TRAINING"
    assert payload["failure_category"] == "Reward Hack"


def test_tools_call_file_path_context_gap():
    resp = handle({
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "audit_trajectory",
                   "arguments": {"file_path": str(FIXTURES / "context_gap.json")}},
    })
    content = resp["result"]["content"]
    payload = json.loads(content[0]["text"])
    assert payload["diagnosis"] == "HARNESS"


def test_tools_call_invalid_json_is_error():
    resp = handle({
        "jsonrpc": "2.0", "id": 5, "method": "tools/call",
        "params": {"name": "audit_trajectory",
                   "arguments": {"trajectory_json": "not json"}},
    })
    assert resp["result"]["isError"] is True
    assert resp["result"]["content"][0]["text"].startswith("error:")


def test_initialized_notification_returns_none():
    resp = handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp is None


def test_unknown_method_with_id():
    resp = handle({"jsonrpc": "2.0", "id": 6, "method": "bogus/method", "params": {}})
    assert resp["error"]["code"] == -32601
    assert resp["id"] == 6


def test_subprocess_smoke():
    lines = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
    ]) + "\n"
    proc = subprocess.run(
        [sys.executable, "-m", "src.mcp_server"],
        input=lines, capture_output=True, text=True, timeout=20,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    out_lines = [l for l in proc.stdout.splitlines() if l.strip()]
    assert len(out_lines) == 2
    first = json.loads(out_lines[0])
    second = json.loads(out_lines[1])
    assert first["result"]["serverInfo"]["name"] == "rl-trajectory-auditor"
    assert "audit_trajectory" in out_lines[1]
    assert second["result"]["tools"][0]["name"] == "audit_trajectory"
