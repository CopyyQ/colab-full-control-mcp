from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .settings import Settings
from .tools import build_tool_bundle, register_tools


SERVER_INSTRUCTIONS = """
This MCP server exposes controlled file, code, notebook, runtime, job, training,
Git, Drive, and artifact operations for a Google Colab runtime. It does not run
autonomous research loops. Write and execute tools require token validation and
destructive operations require confirm=true.
""".strip()


def create_mcp_server(settings: Settings | None = None) -> FastMCP:
    resolved_settings = settings or Settings()
    bundle = build_tool_bundle(resolved_settings)
    server = FastMCP(
        "Colab Full Control MCP",
        instructions=SERVER_INSTRUCTIONS,
        host=resolved_settings.host,
        port=resolved_settings.port,
        streamable_http_path=resolved_settings.mount_path,
        json_response=True,
    )
    register_tools(server, bundle)
    server._colab_bundle = bundle  # type: ignore[attr-defined]
    return server


def create_app(settings: Settings | None = None) -> Any:
    server = create_mcp_server(settings)
    return server.streamable_http_app()
