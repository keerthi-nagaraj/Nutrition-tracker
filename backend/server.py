"""Nutrition Tracker MCP Server entrypoint: wires mcp_app + controllers/views/nutrition_tracker and runs the server."""

from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

import controllers  # noqa: F401 -- importing registers every tool as a side effect
from mcp_app import mcp

# Origins allowed to call this server from a browser (the Svelte dev server,
# plus the built frontend's preview port). Add production origins here too.
FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://192.168.0.25:5173",
]

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8000,
        path="/mcp",
        allowed_origins=FRONTEND_ORIGINS,
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=FRONTEND_ORIGINS,
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["*"],
                expose_headers=["mcp-session-id"],
            ),
        ],
    )
