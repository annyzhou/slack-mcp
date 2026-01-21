# Copyright (c) 2026 Dedalus Labs, Inc. and its contributors
# SPDX-License-Identifier: MIT

"""MCP server entrypoint.

Exposes Slack tools via Dedalus MCP framework.
Uses static SLACK_BOT_TOKEN from environment for authentication.
"""

from dedalus_mcp import MCPServer
from dedalus_mcp.server import TransportSecuritySettings

from slack import slack_tools
from smoke import smoke_tools


def create_server() -> MCPServer:
    """Create MCP server with current env config."""
    return MCPServer(
        name="slack-mcp",
        connections=[],
        http_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        streamable_http_stateless=True,
    )


async def main() -> None:
    """Start MCP server."""
    server = create_server()
    server.collect(*smoke_tools, *slack_tools)
    await server.serve(port=8080)
