"""Минимальный stdio-сервер MCP для тестов клиента."""

from mcp.server.mcpserver import MCPServer

server = MCPServer("echo")


@server.tool()
def echo(text: str) -> str:
    """Return the given text."""
    return text


@server.tool()
def fail() -> str:
    """Always fail."""
    raise RuntimeError("tool failed")


if __name__ == "__main__":
    server.run("stdio")
