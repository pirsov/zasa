"""Клиент MCP: серверы из mcp_config.json и вызов их инструментов."""

from __future__ import annotations

import json
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import Client as SdkClient
from mcp import StdioServerParameters
from pydantic import BaseModel, ConfigDict, Field


class McpClientError(RuntimeError):
    """Сервер не настроен или инструмент вернул ошибку."""


class McpServerConfig(BaseModel):
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None


class McpConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mcp_servers: dict[str, McpServerConfig] = Field(default_factory=dict, alias="mcpServers")


class McpTool(BaseModel):
    server: str
    name: str
    description: str = ""


class McpClient:
    """Держит stdio-сессии к серверам из конфигурации."""

    def __init__(self, config_path: str | Path = "mcp_config.json") -> None:
        self.config_path = Path(config_path)
        self._stack: AsyncExitStack | None = None
        self._sessions: dict[str, SdkClient] = {}

    def load_config(self) -> McpConfig:
        if not self.config_path.is_file():
            return McpConfig()
        return McpConfig.model_validate_json(self.config_path.read_text(encoding="utf-8"))

    async def list_tools(self, server: str | None = None) -> list[McpTool]:
        config = self.load_config()
        names = [server] if server is not None else list(config.mcp_servers)
        found: list[McpTool] = []
        for name in names:
            session = await self._session(name)
            listed = await session.list_tools()
            for tool in listed.tools:
                found.append(
                    McpTool(
                        server=name,
                        name=tool.name,
                        description=tool.description or "",
                    )
                )
        return found

    async def call_tool(
        self,
        server: str,
        tool: str,
        arguments: dict[str, Any] | None = None,
    ) -> str:
        session = await self._session(server)
        result = await session.call_tool(tool, arguments or {})
        text = _content_text(result.content, result.structured_content)
        if result.is_error:
            raise McpClientError(text or f"Tool {server}/{tool} failed")
        return text

    async def close(self) -> None:
        stack = self._stack
        self._stack = None
        self._sessions.clear()
        if stack is not None:
            await stack.aclose()

    async def _session(self, server: str) -> SdkClient:
        existing = self._sessions.get(server)
        if existing is not None:
            return existing
        config = self.load_config()
        spec = config.mcp_servers.get(server)
        if spec is None:
            raise McpClientError(f"MCP server is not configured: {server}")
        if self._stack is None:
            self._stack = AsyncExitStack()
            await self._stack.__aenter__()
        params = StdioServerParameters(command=spec.command, args=list(spec.args), env=spec.env)
        # Playwright и другие серверы 2025 говорят через initialize.
        session = SdkClient(params, mode="legacy")
        try:
            await self._stack.enter_async_context(session)
        except Exception:
            self._sessions.pop(server, None)
            raise
        self._sessions[server] = session
        return session


def _content_text(content: list[Any], structured: Any) -> str:
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    if parts:
        return "\n".join(parts)
    if structured is None:
        return ""
    return json.dumps(structured, ensure_ascii=False)
