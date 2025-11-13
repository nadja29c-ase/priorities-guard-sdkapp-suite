# Priority Guardian Backend Skeleton — Core Brief

**Goal:** Build minimal production-ready FastAPI backend with `GET /api/focused/health`.

No OAuth, no DB, no extra modules.

**Note:** The repository contains placeholder files (e.g., `oauth_provider.py`, `google_client.py`, `redis_client.py`, `celery_app.py`, `db.py`) for future increments. These files should be **ignored** for this skeleton implementation. They are not part of the minimal foundation and will be implemented in later phases.

---

## 1. Requirements

* FastAPI + uvicorn
* Single endpoint: `/api/focused/health`
* Fully async
* Structured JSON logging (no `print()`)
* Stateless

---

## 2. Directory Structure

```
backend/
├── main.py
├── core/
│   ├── __init__.py          # empty
│   ├── config.py
│   ├── logging.py
│   └── middleware.py
└── apps/
    └── focused/
        ├── __init__.py      # empty
        └── focused_router.py
```

---

## 3. Technical Constraints

* All endpoints: `async def`
* No blocking calls
* Never log sensitive data
* Response format:
  - Success: `{"success": true, "data": {...}}`
  - Error: `{"success": false, "error": {"code": "...", "message": "..."}}`
* No HTML/templates - JSON only
* Stateless: no caching, no in-memory state

---

## 4. Health Endpoint

**`GET /api/focused/health`**

Returns:
```json
{
  "success": true,
  "data": {
    "status": "ok",
    "service": "focused-backend",
    "version": "0.1.0"
  }
}
```

Must:
* Log request received + completed (INFO)
* Include `request_id` in every log
* Wrap in try/except, return error format on failure

---

## 5. Config (core/config.py)

* Use Pydantic Settings
* Load from `.env`
* Fields: `APP_NAME`, `ENV`, `LOG_LEVEL`, `HOST`, `PORT`
* Export `settings` instance

---

## 6. Logging (core/logging.py)

* JSON formatter with fields: timestamp, level, app_name, request_id, message
* Configure root logger from `settings.LOG_LEVEL`
* Suppress uvicorn access logs
* Export `init_logging()` function

---

## 7. Middleware (core/middleware.py)

**RequestIDMiddleware:**
* Generate UUID4 per request
* Store in `request.state.request_id`
* Make accessible to all endpoints

---

## 8. main.py

Must:
* Initialize logging first
* Create FastAPI app
* Add RequestIDMiddleware
* Include focused router with prefix `/api/focused`
* Add root `GET /` returning: `{"success": true, "data": {"message": "Priority Guardian Backend"}}`
* Startup event logging app_name + env

**Critical routing:**
* main.py adds prefix: `app.include_router(focused_router, prefix="/api/focused")`
* router.py has NO prefix
* Result: `/api/focused/health` ✓

---

## 9. apps/focused/focused_router.py

* APIRouter with tags, NO prefix
* Implement `/health` as specified in section 4
* Access `request.state.request_id` for logging

---

## 10. Dependencies

```toml
fastapi = "^0.115.0"
uvicorn = {extras = ["standard"], version = "^0.32.0"}
pydantic = "^2.10.3"
pydantic-settings = "^2.7.0"
python-json-logger = "^2.0.7"
```

**Do NOT add:** SQLAlchemy, Alembic, httpx, cryptography, Redis, Celery, Google libs

---

## 11. .env

```
APP_NAME=priority-guardian
ENV=dev
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8000
```

---

## 12. Run & Test

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
curl http://localhost:8000/
curl http://localhost:8000/api/focused/health
```

Logs must be JSON format with request_id.

---

## 13. What NOT to Implement

No DB, OAuth, MCP, encryption, Google/Apple APIs, webhooks, CORS, rate limiting, or validation beyond basics.

---

## 14. Success Criteria

✅ Server runs without errors  
✅ Both endpoints return correct JSON  
✅ Logs are JSON with request_id  
✅ No print() statements  
✅ All endpoints async  
✅ Error handling in place  

---

**Foundation only. Increment 1 adds OAuth + DB + MCP.**