"""MCP server for TraceLab.

This module provides the main MCP server entry point that can be run
as a standalone process or imported for testing.

Usage:
    python -m app.mcp_server.server

Or via the CLI:
    tracelab mcp-server
"""

from __future__ import annotations

import asyncio
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server

from app.mcp_server.tools.missions import register_mission_tools

logger = logging.getLogger(__name__)


def create_mcp_server(name: str = "tracelab") -> Server:
    """Create and configure the TraceLab MCP server.

    Args:
        name: The server name to use for identification.

    Returns:
        Configured MCP Server instance with all tools registered.
    """
    server = Server(name)

    # Register tool modules
    register_mission_tools(server)

    logger.info(f"TraceLab MCP server '{name}' initialized with mission tools")
    return server


async def run_server(server: Server | None = None) -> None:
    """Run the MCP server using stdio transport.

    Args:
        server: Optional pre-configured server. If None, creates a new one.
    """
    if server is None:
        server = create_mcp_server()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """Main entry point for running the MCP server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting TraceLab MCP server...")
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
