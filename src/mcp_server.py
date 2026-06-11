"""MCP stdio server exposing the trajectory auditor as a tool.

Speaks newline-delimited JSON-RPC 2.0 on stdin/stdout (MCP stdio transport).
Stdlib only. Register with: claude mcp add rl-audit -- python3 -m src.mcp_server
"""
from __future__ import annotations

import json
import sys

from src.models import Trajectory
from src.detectors import run_all
from src.framework.four_point_diagnostic import diagnose
from src.report.format import diagnosis_to_dict

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "rl-trajectory-auditor", "version": "0.2.0"}

TOOLS = [
    {
        "name": "audit_trajectory",
        "description": (
            "Audit one RL agent trajectory and classify the failure as "
            "HARNESS / TRAINING / PRODUCT / BOTH / CLEAN with evidence and a "
            "fix recommendation. Accepts OpenAI-style flat trajectory JSON or "
            "an HF SWE-rebench row."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "trajectory_json": {
                    "type": "string",
                    "description": "The trajectory as a JSON string",
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Path to a trajectory .json file "
                        "(alternative to trajectory_json)"
                    ),
                },
            },
        },
    }
]


def _result(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _audit(arguments: dict) -> dict:
    """Run the audit tool; returns an MCP tool-call result payload."""
    try:
        if arguments.get("trajectory_json") is not None:
            data = json.loads(arguments["trajectory_json"])
        elif arguments.get("file_path") is not None:
            with open(arguments["file_path"]) as f:
                data = json.load(f)
        else:
            raise ValueError("provide trajectory_json or file_path")
        traj = Trajectory.from_dict(data)
        d = diagnose(traj, run_all(traj, None))
        text = json.dumps(diagnosis_to_dict(d), indent=2)
        return {"content": [{"type": "text", "text": text}]}
    except Exception as e:  # noqa: BLE001 - report any failure to the client
        return {
            "content": [{"type": "text", "text": f"error: {e}"}],
            "isError": True,
        }


def handle(msg: dict) -> dict | None:
    """Dispatch one JSON-RPC message; returns a response dict or None."""
    method = msg.get("method")
    msg_id = msg.get("id")

    if method == "initialize":
        return _result(msg_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })

    if method == "tools/list":
        return _result(msg_id, {"tools": TOOLS})

    if method == "tools/call":
        params = msg.get("params") or {}
        if params.get("name") == "audit_trajectory":
            return _result(msg_id, _audit(params.get("arguments") or {}))
        return _result(msg_id, {
            "content": [{"type": "text",
                         "text": f"error: unknown tool {params.get('name')!r}"}],
            "isError": True,
        })

    if msg_id is None:
        # Notification (e.g. notifications/initialized): never respond.
        return None

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": "method not found"},
    }


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(msg)
        if resp is not None:
            print(json.dumps(resp), flush=True)


if __name__ == "__main__":
    main()
