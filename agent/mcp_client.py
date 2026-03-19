import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google.genai import types


def _normalize_tool_name(server_name: str, tool_name: str) -> str:
    raw = f"{server_name}_{tool_name}"
    return "".join(ch if ch.isalnum() else "_" for ch in raw)


def _read_message(stream) -> dict[str, Any]:
    headers: dict[str, str] = {}

    while True:
        line = stream.readline()
        if not line:
            raise RuntimeError("MCP server closed stdout unexpectedly.")
        decoded = line.decode("utf-8")
        if decoded in ("\r\n", "\n"):
            break
        key, value = decoded.split(":", 1)
        headers[key.strip().lower()] = value.strip()

    content_length = int(headers["content-length"])
    body = stream.read(content_length)
    if not body:
        raise RuntimeError("MCP server returned an empty message body.")
    return json.loads(body.decode("utf-8"))


def _write_message(stream, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
    stream.write(header)
    stream.write(body)
    stream.flush()


@dataclass
class MCPToolSpec:
    public_name: str
    server_name: str
    mcp_name: str
    description: str
    input_schema: dict[str, Any]


class MCPServerSession:
    def __init__(self, server_name: str, server_path: Path):
        self.server_name = server_name
        self.server_path = server_path
        self.process: subprocess.Popen[bytes] | None = None
        self._request_id = 0

    def start(self) -> None:
        self.process = subprocess.Popen(
            ["python", str(self.server_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "matai-agent", "version": "0.2.0"},
            },
        )
        self.notify("notifications/initialized", {})

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=2)

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.process is None or self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError(f"MCP server '{self.server_name}' is not running.")

        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        _write_message(self.process.stdin, payload)

        while True:
            message = _read_message(self.process.stdout)
            if "id" not in message:
                continue
            if message["id"] != self._request_id:
                continue
            if "error" in message:
                raise RuntimeError(
                    f"MCP server '{self.server_name}' error for {method}: {message['error']}"
                )
            return message.get("result", {})

    def notify(self, method: str, params: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise RuntimeError(f"MCP server '{self.server_name}' is not running.")
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        _write_message(self.process.stdin, payload)


class MCPToolbox:
    def __init__(self, server_root: str):
        self.server_root = Path(server_root)
        self.sessions: dict[str, MCPServerSession] = {}
        self.tools: dict[str, MCPToolSpec] = {}

    def __enter__(self) -> "MCPToolbox":
        for server_path in sorted(self.server_root.glob("*/server.py")):
            server_name = server_path.parent.name
            session = MCPServerSession(server_name, server_path)
            session.start()
            self.sessions[server_name] = session

            listed = session.request("tools/list", {})
            for tool in listed.get("tools", []):
                public_name = _normalize_tool_name(server_name, tool["name"])
                self.tools[public_name] = MCPToolSpec(
                    public_name=public_name,
                    server_name=server_name,
                    mcp_name=tool["name"],
                    description=tool.get("description", ""),
                    input_schema=tool.get("inputSchema", {"type": "object", "properties": {}}),
                )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        for session in self.sessions.values():
            session.stop()

    def google_tools(self) -> list[Any]:
        declarations = [
            types.FunctionDeclaration(
                name=tool.public_name,
                description=tool.description,
                parameters_json_schema=tool.input_schema,
            )
            for tool in self.tools.values()
        ]
        if not declarations:
            return []
        return [types.Tool(function_declarations=declarations)]

    def call(self, public_name: str, arguments: dict[str, Any]) -> str:
        tool = self.tools[public_name]
        session = self.sessions[tool.server_name]
        result = session.request(
            "tools/call",
            {
                "name": tool.mcp_name,
                "arguments": arguments,
            },
        )
        content = result.get("content", [])
        text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
        return "\n".join(part for part in text_parts if part).strip()
