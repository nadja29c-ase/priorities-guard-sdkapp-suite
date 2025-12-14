"""
Clarity SDK App.

Cluster persistence and retrieval for the Clarity MCP server.
"""

from backend.apps.clarity.routers.clusters_router import router as clusters_router

__all__ = ["clusters_router"]
