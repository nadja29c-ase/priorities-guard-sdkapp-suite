Goal:
Refactor the repository so that the FastAPI backend and the Focused MCP server are cleanly separated into two independent top-level services:

backend/ → FastAPI backend (OAuth provider, Google, DB, Redis, Celery, API)

mcp/ → standalone MCP servers (one folder per SDK app)

This reflects the two-server architecture.

1. Create the new folder layout

Move the existing Focused MCP server code out of backend/apps/focused/ and into a new top-level folder:

mcp/
  focused/
    server.py
    tools.py


Do NOT change import paths inside the MCP code yet — just move the files.

2. Update the backend folder to contain only backend code

Ensure the backend structure becomes:

backend/
  core/
  apps/
    focused/
      models.py
      routes.py
      logic.py
  main.py


If the MCP server or MCP-specific code exists inside backend/apps/focused/, remove it from there after moving to mcp/focused/.

Only backend code remains inside backend/apps/focused/.

3. Fix imports inside the MCP server

Inside mcp/focused/server.py and mcp/focused/tools.py:

Update imports so the MCP server imports backend modules as:

from backend.apps.focused.logic import ...
from backend.core.config import settings


Remove any accidental imports that reference FastAPI routers or backend-specific endpoints.

4. Ensure both services can run independently
For the MCP server:

Make sure server.py exposes a FastMCP HTTP server using mcp.run(transport="http", port=8001).

For the backend:

Keep uvicorn backend.main:app unchanged (port 8000).

5. Adjust any absolute or relative paths

If the MCP server needs access to shared utilities (e.g., config, logging utils), ensure it imports them from backend.core, not via relative paths like ...

Example:

from backend.core.config import settings

6. Update project-level README and documentation references

Add a short explanation:

“Focused MCP server runs in mcp/focused/ as a standalone FastMCP service (port 8001).
Backend remains under backend/ (port 8000).
Both are deployed separately and routed via reverse proxy.”

7. Do NOT modify the database schema, Celery config, or FastAPI backend code

Only the folder structure and MCP imports must change.
Backend responsibilities remain unchanged.

✔ Expected result

Final repo structure:

priority-guardian/
  backend/
    core/
    apps/
      focused/
        models.py
        logic.py
        routes.py
    main.py

  mcp/
    focused/
      server.py
      tools.py

  pyproject.toml
  README.md


Both services:

Can be started independently

Are cleanly separated

Match the two-server architecture

Keep the Focused MCP server inside the Focused app, just properly located under mcp/