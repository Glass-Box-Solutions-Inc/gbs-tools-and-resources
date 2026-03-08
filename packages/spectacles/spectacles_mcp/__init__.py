# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""
Spectacles MCP Server -- Thin HTTP Client

Pure HTTP client that exposes the deployed Spectacles Cloud Run service
(https://spectacles-gc2qovgs7q-uc.a.run.app) as MCP tools for AI agents.

No internal Spectacles modules are imported.  Run with:

    python3 -m spectacles_mcp
"""

from .server import create_mcp_server
from .tools import SpectaclesTools

__all__ = [
    "create_mcp_server",
    "SpectaclesTools",
]
