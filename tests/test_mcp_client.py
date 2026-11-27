"""Конфиг MCP и вызов инструмента по stdio."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent.mcp_client import McpClient, McpClientError
from agent.schema import ActionType, EditCommand

_FIXTURE = Path(__file__).parent / "fixtures" / "echo_mcp_server.py"


def test_load_playwright_config() -> None:
    config = McpClient(Path("mcp_config.json")).load_config()
    playwright = config.mcp_servers["playwright"]
    assert playwright.command == "npx"
    assert playwright.args == ["-y", "@modelcontextprotocol/server-playwright"]


def test_call_mcp_requires_server_and_tool() -> None:
    with pytest.raises(ValidationError):
        EditCommand(
            action=ActionType.call_mcp,
            path=".",
            reason="нет имени инструмента",
        )


def test_mcp_fields_rejected_for_other_actions() -> None:
    with pytest.raises(ValidationError):
        EditCommand(
            action=ActionType.read_symbol,
            path="agent/schema.py",
            symbol="Plan",
            mcp_server="playwright",
            tool_name="navigate",
            reason="чужие поля",
        )


def test_list_and_call_tool(tmp_path: Path) -> None:
    config_path = _write_echo_config(tmp_path)
    client = McpClient(config_path)

    async def scenario() -> None:
        tools = await client.list_tools("echo")
        names = {tool.name for tool in tools}
        assert "echo" in names
        assert await client.call_tool("echo", "echo", {"text": "hello"}) == "hello"
        await client.close()

    asyncio.run(scenario())


def test_unknown_server(tmp_path: Path) -> None:
    client = McpClient(_write_echo_config(tmp_path))

    async def scenario() -> None:
        with pytest.raises(McpClientError, match="not configured"):
            await client.call_tool("missing", "echo", {})
        await client.close()

    asyncio.run(scenario())


def test_tool_error(tmp_path: Path) -> None:
    client = McpClient(_write_echo_config(tmp_path))

    async def scenario() -> None:
        with pytest.raises(McpClientError):
            await client.call_tool("echo", "fail", {})
        await client.close()

    asyncio.run(scenario())


def _write_echo_config(tmp_path: Path) -> Path:
    path = tmp_path / "mcp_config.json"
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "echo": {
                        "command": sys.executable,
                        "args": [str(_FIXTURE)],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return path
