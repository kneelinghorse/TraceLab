"""MCP (Model Context Protocol) server for TraceLab.

Provides tools for AI agents to interact with TraceLab's mission management,
document search, and research workflows.
"""

__all__ = ["create_mcp_server"]

from app.mcp_server.server import create_mcp_server
