# Copyright (c) 2026 Dedalus Labs, Inc. and its contributors
# SPDX-License-Identifier: MIT

"""Smoke test tools for slack-mcp."""

from mcp.types import TextContent, Tool

from dedalus_mcp.types import ToolAnnotations

from dedalus_mcp import tool


@tool(
    description="Smoke test tool that echoes input",
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def smoke_echo(message: str) -> list[TextContent]:
    """Echo a message back to verify server is working."""
    return [TextContent(type="text", text=f"Echo: {message}")]


@tool(
    description="Smoke test tool that returns server info",
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def smoke_info() -> list[TextContent]:
    """Return basic server information."""
    return [
        TextContent(
            type="text",
            text="slack-mcp server v0.0.1 - Slack MCP tools via Dedalus framework",
        )
    ]


smoke_tools: list[Tool] = [smoke_echo, smoke_info]
