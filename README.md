# Priority Guardian

A backend service for managing Focus Mode sessions with Google Calendar integration.

## Overview

Priority Guardian helps users manage their focus time by:
- Syncing focus blocks from Google Calendar
- Activating/deactivating Apple Focus Mode via iOS Shortcuts
- Auto-scheduling focus session deactivation

## Tech Stack

- **FastAPI** - REST API backend
- **MCP Server** - Model Context Protocol for ChatGPT integration
- **Celery** - Background task processing
- **PostgreSQL** - Database
- **Redis** - Task queue and caching
- **SQLAlchemy** - ORM

## Running Locally

### Prerequisites

- Python 3.11+
- PostgreSQL
- Redis

### Start Services

```bash
# FastAPI server (port 8000)
uvicorn backend.main:app --reload --port 8000

# Celery worker with beat scheduler
celery -A backend.core.celery_app.celery_app worker --beat --loglevel=info -Q focused

# MCP server (port 8001)
python -m mcp_server.focused.server
```

### Run Tests

```bash
pytest tests/unit -v
pytest tests/integration -v
```

## API Endpoints

- `POST /focused/tools/run_focus_mode` - Activate/deactivate Focus Mode
- `POST /focused/tools/check_calendar` - Scan calendar for focus blocks
- `POST /focused/tools/sync_calendar` - Manual calendar sync
- `POST /focused/tools/watch_calendar` - Register webhook for calendar changes

## License

Proprietary
