"""
Terraform Expert MCP Proxy Server
==================================
Launches the terraform-mcp-server Go binary as a subprocess (stdio mode),
discovers all tools it exposes, and re-publishes them via the Python MCP
library so that the Copilot agent can call them.

Binary resolution order:
  1. TERRAFORM_MCP_SERVER environment variable
  2. 'terraform-mcp-server' on PATH
  3. Fatal error with setup instructions
"""

import asyncio
import json
import logging
import os
import shutil
import sys
from typing import Any

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    TextContent,
    Tool,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("terraform-expert-proxy")

# ---------------------------------------------------------------------------
# Environment / config
# ---------------------------------------------------------------------------
load_dotenv()  # reads .env if present; silently ignores missing file

TFE_TOKEN = os.environ.get("TFE_TOKEN", "")
TFE_ADDRESS = os.environ.get("TFE_ADDRESS", "https://app.terraform.io")
BINARY_ENV_VAR = "TERRAFORM_MCP_SERVER"


def _resolve_binary() -> str:
    """Return the path to terraform-mcp-server, or raise RuntimeError."""
    explicit = os.environ.get(BINARY_ENV_VAR, "").strip()
    if explicit:
        if not os.path.isfile(explicit):
            raise RuntimeError(
                f"TERRAFORM_MCP_SERVER={explicit!r} does not point to a file."
            )
        log.info("Using binary from env var: %s", explicit)
        return explicit

    found = shutil.which("terraform-mcp-server")
    if found:
        log.info("Found binary on PATH: %s", found)
        return found

    raise RuntimeError(
        "terraform-mcp-server binary not found.\n"
        "  Option 1: Add it to your PATH.\n"
        "  Option 2: Set TERRAFORM_MCP_SERVER=/absolute/path in .env"
    )


# ---------------------------------------------------------------------------
# Subprocess MCP client (talks stdio JSON-RPC to the Go binary)
# ---------------------------------------------------------------------------

class TerraformSubprocess:
    """Manages a long-running terraform-mcp-server subprocess."""

    def __init__(self, binary: str) -> None:
        self.binary = binary
        self._proc: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        env = {**os.environ, "TFE_ADDRESS": TFE_ADDRESS}
        if TFE_TOKEN:
            env["TFE_TOKEN"] = TFE_TOKEN

        self._proc = await asyncio.create_subprocess_exec(
            self.binary,
            "stdio",
            "--toolsets=all",
            "--log-level=error",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        log.info("terraform-mcp-server subprocess started (pid=%d)", self._proc.pid)

        # MCP handshake — initialize
        await self._send(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "terraform-expert-proxy", "version": "1.0.0"},
            },
        )
        # Notify initialized
        await self._notify("notifications/initialized", {})

    async def _send(self, method: str, params: dict) -> dict:
        """Send a JSON-RPC request and return the response."""
        async with self._lock:
            self._request_id += 1
            req = {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": method,
                "params": params,
            }
            payload = (json.dumps(req) + "\n").encode()
            self._proc.stdin.write(payload)
            await self._proc.stdin.drain()

            raw = await self._proc.stdout.readline()
            if not raw:
                raise RuntimeError("terraform-mcp-server subprocess closed unexpectedly")
            resp = json.loads(raw)
            if "error" in resp:
                raise RuntimeError(f"MCP error from subprocess: {resp['error']}")
            return resp.get("result", {})

    async def _notify(self, method: str, params: dict) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        notif = {"jsonrpc": "2.0", "method": method, "params": params}
        payload = (json.dumps(notif) + "\n").encode()
        self._proc.stdin.write(payload)
        await self._proc.stdin.drain()

    async def list_tools(self) -> list[dict]:
        result = await self._send("tools/list", {})
        return result.get("tools", [])

    async def call_tool(self, name: str, arguments: dict) -> dict:
        return await self._send("tools/call", {"name": name, "arguments": arguments})

    async def stop(self) -> None:
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._proc.kill()
            log.info("terraform-mcp-server subprocess stopped")


# ---------------------------------------------------------------------------
# Proxy MCP server
# ---------------------------------------------------------------------------

def _sanitise_error(msg: str) -> str:
    """Strip any accidental token leakage from error strings."""
    if TFE_TOKEN:
        msg = msg.replace(TFE_TOKEN, "[REDACTED]")
    return msg


def _tool_result_to_mcp(raw: dict) -> list[TextContent]:
    """Convert a tools/call response to MCP TextContent list."""
    content = raw.get("content", [])
    results = []
    for item in content:
        if item.get("type") == "text":
            results.append(TextContent(type="text", text=item["text"]))
        else:
            results.append(TextContent(type="text", text=json.dumps(item)))
    if not results:
        results.append(TextContent(type="text", text=json.dumps(raw)))
    return results


async def run_proxy() -> None:
    binary = _resolve_binary()
    tf = TerraformSubprocess(binary)
    await tf.start()

    # Discover tools from the Go binary
    raw_tools = await tf.list_tools()
    log.info("Discovered %d tools from terraform-mcp-server", len(raw_tools))

    server = Server("terraform-expert")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        tools = []
        for t in raw_tools:
            tools.append(
                Tool(
                    name=t["name"],
                    description=t.get("description", ""),
                    inputSchema=t.get("inputSchema", {"type": "object", "properties": {}}),
                )
            )
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        log.debug("call_tool: %s %s", name, list(arguments.keys()))
        try:
            result = await tf.call_tool(name, arguments)
            return _tool_result_to_mcp(result)
        except Exception as exc:
            safe_msg = _sanitise_error(str(exc))
            log.error("Tool %s failed: %s", name, safe_msg)
            return [TextContent(type="text", text=f"Error calling {name}: {safe_msg}")]

    log.info("Proxy server ready — %d tools available", len(raw_tools))

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        await tf.stop()


if __name__ == "__main__":
    try:
        asyncio.run(run_proxy())
    except RuntimeError as err:
        log.critical("Startup failed: %s", err)
        sys.exit(1)
