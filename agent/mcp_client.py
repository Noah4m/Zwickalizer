import json
import logging
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


logger = logging.getLogger("uvicorn.error")


def _normalize_tool_name(server_name: str, tool_name: str) -> str:
    raw = f"{server_name}_{tool_name}"
    return "".join(ch if ch.isalnum() else "_" for ch in raw)


def _read_message(stream) -> dict[str, Any]:
    while True:
        line = stream.readline()
        if not line:
            raise RuntimeError("MCP server closed stdout unexpectedly.")
        decoded = line.decode("utf-8").strip()
        if not decoded:
            continue
        if decoded.startswith("{"):
            return json.loads(decoded)

        headers: dict[str, str] = {}
        while True:
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()
            line = stream.readline()
            if not line:
                raise RuntimeError("MCP server closed stdout unexpectedly.")
            decoded = line.decode("utf-8")
            if decoded in ("\r\n", "\n"):
                break
            decoded = decoded.rstrip("\r\n")

        content_length = int(headers["content-length"])
        body = stream.read(content_length)
        if not body:
            raise RuntimeError("MCP server returned an empty message body.")
        return json.loads(body.decode("utf-8"))


def _write_message(stream, payload: dict[str, Any]) -> None:
    stream.write(json.dumps(payload).encode("utf-8"))
    stream.write(b"\n")
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
        self._stderr_thread: threading.Thread | None = None

    def start(self) -> None:
        logger.info("Starting MCP server '%s' from %s", self.server_name, self.server_path)
        self.process = subprocess.Popen(
            [sys.executable, str(self.server_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if self.process.stderr is not None:
            self._stderr_thread = threading.Thread(
                target=self._forward_stderr,
                name=f"mcp-stderr-{self.server_name}",
                daemon=True,
            )
            self._stderr_thread.start()
        try:
            self.request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "matai-agent", "version": "0.2.0"},
                },
            )
            self.notify("notifications/initialized", {})
            logger.info("MCP server '%s' initialized", self.server_name)
        except Exception:
            logger.exception("Failed to initialize MCP server '%s'", self.server_name)
            self.stop()
            raise

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=2)
        else:
            logger.info(
                "MCP server '%s' exited with code %s",
                self.server_name,
                self.process.returncode,
            )
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=0.5)

    def _forward_stderr(self) -> None:
        if self.process is None or self.process.stderr is None:
            return
        for raw_line in iter(self.process.stderr.readline, b""):
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            if line:
                logger.error("MCP server '%s' stderr: %s", self.server_name, line)

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
            try:
                message = _read_message(self.process.stdout)
            except Exception:
                logger.exception(
                    "MCP server '%s' failed while waiting for response to %s",
                    self.server_name,
                    method,
                )
                raise
            if "id" not in message:
                continue
            if message["id"] != self._request_id:
                continue
            if "error" in message:
                logger.error(
                    "MCP server '%s' returned an error for %s: %s",
                    self.server_name,
                    method,
                    message["error"],
                )
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
            logger.info(
                "Registered %d MCP tools from server '%s': %s",
                len([tool for tool in self.tools.values() if tool.server_name == server_name]),
                server_name,
                ", ".join(
                    sorted(
                        tool.public_name
                        for tool in self.tools.values()
                        if tool.server_name == server_name
                    )
                ),
            )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        for session in self.sessions.values():
            session.stop()

    def openai_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.public_name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in self.tools.values()
        ]

    def call(self, public_name: str, arguments: dict[str, Any]) -> str:
        tool = self.tools[public_name]
        session = self.sessions[tool.server_name]
        logger.info(
            "Calling MCP tool '%s' on server '%s' with arguments: %s",
            public_name,
            tool.server_name,
            json.dumps(arguments, default=str),
        )
        try:
            result = session.request(
                "tools/call",
                {
                    "name": tool.mcp_name,
                    "arguments": arguments,
                },
            )
        except Exception:
            logger.exception(
                "MCP tool '%s' on server '%s' failed",
                public_name,
                tool.server_name,
            )
            raise
        content = result.get("content", [])
        text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
        text_result = "\n".join(part for part in text_parts if part).strip()
        logger.info(
            "MCP tool '%s' on server '%s' succeeded",
            public_name,
            tool.server_name,
        )
        return text_result
