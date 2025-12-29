# Fulfilling Productivity — Repo Setup Guide

## Step 1: Create GitHub Repo

1. Go to [github.com/new](https://github.com/new)
2. **Repository name:** `fulfilling-productivity`
3. **Description:** "Productivity tools for thinking clearly"
4. **Visibility:** Private (for now)
5. **Initialize:** Check "Add a README file"
6. **Add .gitignore:** Select "Python"
7. Click **Create repository**

---

## Step 2: Clone Locally

```bash
cd ~/Desktop
git clone git@github.com:YOUR_USERNAME/fulfilling-productivity.git
cd fulfilling-productivity
```

---

## Step 3: Create Directory Structure

```bash
# Create the structure
mkdir -p apps/unpack/{handlers,tools,tests}
mkdir -p docs
touch apps/__init__.py
touch apps/unpack/__init__.py
touch apps/unpack/handlers/__init__.py
touch apps/unpack/tools/__init__.py
touch apps/unpack/tests/__init__.py
```

**Target structure:**
```
fulfilling-productivity/
├── .github/
│   └── workflows/
│       └── test.yml              # CI for tests
├── apps/
│   └── unpack/                   # First app
│       ├── __init__.py
│       ├── server.py
│       ├── config.py
│       ├── tool_logic.py
│       ├── handlers/
│       │   ├── __init__.py
│       │   └── tools.py
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   └── formulate_problem.py
│       └── tests/
│           ├── __init__.py
│           └── test_formulate_problem.py
├── docs/
│   ├── unpack-north-star.md
│   └── unpack-compliance.md
├── .env.example
├── .gitignore
├── pyproject.toml
├── requirements.txt
├── README.md
└── render.yaml                   # Render deployment config
```

---

## Step 4: Copy Unpack Files

Copy from `priority-guardian/mcp_server/unpack/` to `fulfilling-productivity/apps/unpack/`:

```bash
# From priority-guardian repo
cp -r "/Users/nadja/Desktop/Priority Guard Suite/priority-guardian/mcp_server/unpack/"* \
      ~/Desktop/fulfilling-productivity/apps/unpack/
```

---

## Step 5: Fix Import Paths

After copying, update imports in all Python files.

**Change FROM:**
```python
from mcp_server.unpack.config import ...
from mcp_server.unpack.tools import ...
from ..tools import get_tool
```

**Change TO:**
```python
from apps.unpack.config import ...
from apps.unpack.tools import ...
from ..tools import get_tool  # Relative imports stay the same
```

**Files to update:**
- `apps/unpack/server.py` — change absolute imports
- `apps/unpack/handlers/tools.py` — relative imports OK
- `apps/unpack/tools/__init__.py` — relative imports OK
- `apps/unpack/tools/formulate_problem.py` — relative imports OK
- `apps/unpack/tests/test_formulate_problem.py` — change to `apps.unpack.*`

---

## Step 6: Create Root pyproject.toml

```toml
[tool.poetry]
name = "fulfilling-productivity"
version = "0.1.0"
description = "Productivity tools for thinking clearly"
authors = ["Your Name <you@example.com>"]
readme = "README.md"
packages = [{include = "apps"}]

[tool.poetry.dependencies]
python = "^3.11"
mcp = {version = "^1.3.1", extras = ["cli"]}
pydantic = "^2.6.0"
uvicorn = {extras = ["standard"], version = "^0.27.0"}
starlette = "^0.36.0"
structlog = "^24.1.0"

[tool.poetry.group.dev.dependencies]
pytest = "^7.4.4"
pytest-asyncio = "^0.23.3"
ruff = "^0.1.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["apps"]
python_files = "test_*.py"

[tool.ruff]
line-length = 100
target-version = "py311"
```

---

## Step 7: Create requirements.txt

```bash
# Generate from poetry
poetry export -f requirements.txt --output requirements.txt --without-hashes
```

Or create manually:
```
mcp>=1.3.1
pydantic>=2.6.0
uvicorn[standard]>=0.27.0
starlette>=0.36.0
structlog>=24.1.0
```

---

## Step 8: Create .env.example

```bash
# Environment
ENV=dev

# Server
PORT=8003

# CORS (required in production)
# CORS_ALLOWED_ORIGINS=https://web-sandbox.oaiusercontent.com,https://chatgpt.com

# Logging
LOG_LEVEL=INFO
```

---

## Step 9: Create render.yaml

```yaml
services:
  - type: web
    name: unpack-mcp
    env: python
    region: frankfurt
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn apps.unpack.server:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: ENV
        value: production
      - key: CORS_ALLOWED_ORIGINS
        value: https://web-sandbox.oaiusercontent.com,https://chatgpt.com
      - key: LOG_LEVEL
        value: INFO
      - key: PYTHON_VERSION
        value: 3.11.0
```

---

## Step 10: Create README.md

```markdown
# Fulfilling Productivity

Productivity tools for thinking clearly.

## Apps

### Unpack

A question-first sensemaking tool. Helps you clarify problems before solving them.

**Status:** In development

## Development

```bash
# Install dependencies
poetry install

# Run Unpack locally
poetry run uvicorn apps.unpack.server:app --reload --port 8003

# Run tests
poetry run pytest
```

## Deployment

Apps are deployed on Render. See `render.yaml` for configuration.

| App | URL |
|-----|-----|
| Unpack | https://unpack-mcp.onrender.com |
```

---

## Step 11: Update .gitignore

Make sure `.gitignore` includes:
```
# Python
__pycache__/
*.py[cod]
*$py.class
.venv/
venv/
.env

# IDE
.vscode/
.idea/

# Testing
.pytest_cache/
.coverage

# OS
.DS_Store
```

---

## Step 12: Commit and Push

```bash
cd ~/Desktop/fulfilling-productivity
git add .
git commit -m "Initial setup: Unpack MCP server"
git push origin main
```

---

## Step 13: Deploy on Render

### Option A: Using render.yaml (Blueprint)
1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **New** → **Blueprint**
3. Connect your `fulfilling-productivity` repo
4. Render will auto-detect `render.yaml` and create the service

### Option B: Manual Setup
1. Go to Render Dashboard
2. Click **New** → **Web Service**
3. Connect `fulfilling-productivity` repo
4. Configure:
   - **Name:** `unpack-mcp`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn apps.unpack.server:app --host 0.0.0.0 --port $PORT`
5. Add environment variables (see Step 9)
6. Deploy

---

## Step 14: Connect Custom Domain (Optional)

If you want `unpack.fulfilling-productivity.com`:

1. In Render, go to your service → Settings → Custom Domains
2. Add `unpack.fulfilling-productivity.com`
3. In your DNS provider, add CNAME record:
   - **Name:** `unpack`
   - **Value:** `unpack-mcp.onrender.com`

---

## Step 15: Test in ChatGPT

1. Open ChatGPT
2. Add MCP connector with URL: `https://unpack-mcp.onrender.com/mcp`
3. Test: "I'm feeling stuck at work but I don't know why"

---

## Future Apps

When adding more apps to the suite:

```
apps/
├── unpack/          # Question-first sensemaking
├── done/            # Calendar scheduling (future)
└── someday/         # Someday/maybe list (future)
```

Each app gets its own Render service via `render.yaml`.