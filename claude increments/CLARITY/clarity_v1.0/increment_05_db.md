# Increment 05: Clarity DB Persistence

## Context

Increment 04 completed OAuth integration. MCP now has authenticated `user_id` available in `_call_tool_request`. This increment adds database persistence for cluster results.

**Prerequisites confirmed:**
- `user_id` extracted from JWT via `auth_context["user_id"]`
- Auth runs before validation/tool logic

## Architecture Constraint

**MCP servers do NOT access the database directly. All persistence happens through backend REST API.**

Pattern: `ChatGPT → MCP (auth + validate) → Backend API (persist) → PostgreSQL`

Reference: `Shared_Backend_Architecture_Design.pdf` — "MCP servers are stateless; no DB or Redis interaction."

---

## Deliverables

### 1. Database Model

**File:** `backend/apps/clarity/db_models.py` (new)

```
clarity_clusters table:
├── id: UUID PK (gen_random_uuid())
├── user_id: UUID FK → core_users.id (ON DELETE CASCADE)
├── cluster_data: JSONB NOT NULL
├── thoughts_exhausted: boolean NOT NULL
├── correctly_clustered: boolean (nullable)
├── cluster_count: int NOT NULL
├── created_at: timestamp with timezone (server_default=now())
└── updated_at: timestamp with timezone (server_default=now(), onupdate=now())

Index:
- idx_clarity_clusters_user_created (user_id, created_at DESC)

Constraints:
- cluster_data IS NOT NULL
- cluster_count >= 0
```

**cluster_data specification:**
- Stores **logical clustering output only**: `{"clusters": [...]}`
- NO UI metadata, widget hints, or rendering instructions
- Each cluster object contains: `cluster_name`, `thought_items`, `subclusters`, `tags`

**cluster_count derivation:**
- `cluster_count = len(cluster_data["clusters"])`
- Top-level clusters only, excludes subclusters

**Reference:** `backend/apps/focused/db_models.py` for patterns (Base import, validate() method, UUID FK pattern, CheckConstraint usage)

---

### 2. Alembic Migration

**File:** `backend/alembic/versions/xxx_add_clarity_clusters.py`

- Create `clarity_clusters` table with all columns
- Create index `idx_clarity_clusters_user_created`
- No ENUMs needed (simpler than Focused)

---

### 3. Backend Router

**File:** `backend/apps/clarity/routers/clusters_router.py` (new)

```
POST /api/clarity/clusters
├── Header: X-User-ID (required)
├── Body: { cluster_data, thoughts_exhausted, correctly_clustered }
├── Returns: 201 + { cluster_id, created_at }
└── Validates:
    ├── X-User-ID header present
    ├── User exists in core_users
    ├── cluster_data is valid dict with "clusters" array
    └── cluster_count derived from cluster_data
```

**Semantics:**
- POST always creates a new cluster snapshot (append-only)
- Each tool call = new row. No update semantics.
- Returns `201 Created` on success

**Security:**
- `X-User-ID` header required
- Backend assumes request originates from trusted MCP (internal network)
- **TODO before public deployment:** Add `X-Internal-Token` shared secret validation

**Reference:** `backend/apps/focused/routers/tools_router.py` for X-User-ID extraction using `extract_user_id()`

**Request Model:** `backend/apps/clarity/models/requests.py` (new)

```python
class CreateClusterRequest(BaseModel):
    cluster_data: dict  # Must contain "clusters" key
    thoughts_exhausted: bool
    correctly_clustered: bool | None = None
    
    @model_validator(mode="after")
    def validate_cluster_data(self):
        if "clusters" not in self.cluster_data:
            raise ValueError("cluster_data must contain 'clusters' key")
        if not isinstance(self.cluster_data["clusters"], list):
            raise ValueError("cluster_data['clusters'] must be a list")
        return self
```

---

### 4. Backend App Registration

**File:** `backend/apps/clarity/__init__.py` (new)

```python
from backend.apps.clarity.routers.clusters_router import router as clusters_router

__all__ = ["clusters_router"]
```

**Update:** `backend/main.py`

```python
from backend.apps.clarity import clusters_router

app.include_router(clusters_router, prefix="/api/clarity")
```

---

### 5. MCP Server Update

**File:** `mcp_server/clarity/server.py`

In `_call_tool_request`, after successful validation/clustering, add backend persistence call:

```python
# After: result = cluster_raw_thoughts(clusters)
# Add: Persist to backend

import httpx
from mcp_server.clarity.config import BACKEND_URL

# Build logical cluster data (NO UI metadata)
cluster_data_to_store = {
    "clusters": [c.model_dump() for c in validated_request.clusters]
}

try:
    async with httpx.AsyncClient() as client:
        persist_response = await client.post(
            f"{BACKEND_URL}/api/clarity/clusters",
            headers={"X-User-ID": user_id},
            json={
                "cluster_data": cluster_data_to_store,
                "thoughts_exhausted": validated_request.thoughts_exhausted,
                "correctly_clustered": validated_request.correctly_clustered,
            },
            timeout=10.0,
        )
        
    if persist_response.status_code == 201:
        cluster_id = persist_response.json()["cluster_id"]
        logger.info("clarity.tool.persisted", cluster_id=cluster_id, user_id=user_id)
    else:
        logger.warning("clarity.tool.persist_failed", 
                      status=persist_response.status_code,
                      user_id=user_id)

except Exception as e:
    # Persistence failure should NOT fail the tool call
    logger.warning("clarity.tool.persist_error", error=str(e), user_id=user_id)
```

**Critical:** Persistence failure must NOT fail the tool response. User still sees their clusters.

---

### 6. Config Verification

**File:** `mcp_server/clarity/config.py`

Already has `BACKEND_URL`. Verify it's exported and used:

```python
BACKEND_URL = get_env(
    "CLARITY_BACKEND_URL",
    default="http://localhost:8000"
).rstrip("/")
```

---

## Tests

### Unit Tests

**File:** `tests/unit/apps/clarity/test_db_models.py`

```python
class TestClarityClusterModel:
    def test_cluster_data_required(self):
        """cluster_data cannot be None."""
        
    def test_user_id_required(self):
        """user_id FK is required."""
        
    def test_cluster_count_derived_correctly(self):
        """cluster_count matches len(cluster_data['clusters'])."""
        
    def test_validate_method(self):
        """validate() checks cluster_data structure."""
```

### Integration Tests

**File:** `tests/integration/clarity/test_clusters_persistence.py`

```python
class TestClustersPersistence:
    async def test_create_cluster_success(self):
        """POST with valid data returns 201 + cluster_id."""
        
    async def test_missing_user_id_header_returns_401(self):
        """POST without X-User-ID returns 401."""
        
    async def test_nonexistent_user_returns_404(self):
        """POST with unknown user_id returns 404."""
        
    async def test_malformed_cluster_data_returns_400(self):
        """POST with invalid cluster_data structure returns 400."""
        # e.g., cluster_data="not-a-dict" or missing "clusters" key
        
    async def test_cluster_persisted_to_db(self):
        """Verify cluster retrievable from DB after POST."""
```

---

## Data Retention

Per `Data_Retention_Strategy_Shared_Backend.pdf`:
- App-specific data follows app retention rules
- Clarity clusters: Retain until user deletion (CASCADE on core_users FK)
- **Future increment:** Add cleanup job if row accumulation becomes concern (append-only model)

---

## Out of Scope

- Cluster retrieval endpoint (GET /api/clarity/clusters)
- Cluster history/versioning UI
- Widget displaying cluster_id
- Cleanup/retention jobs
- X-Internal-Token shared secret (documented as TODO)

---

## Success Criteria

1. ✅ `clarity_clusters` table created via Alembic migration
2. ✅ `POST /api/clarity/clusters` validates input and persists
3. ✅ Returns `201` + `cluster_id` on success
4. ✅ Returns `400` for malformed cluster_data
5. ✅ Returns `401` for missing X-User-ID
6. ✅ Returns `404` for non-existent user
7. ✅ MCP calls backend after successful clustering
8. ✅ Persistence failure does NOT break tool response (graceful degradation)
9. ✅ cluster_data contains only logical data (no UI metadata)
10. ✅ All tests pass

---

## Files to Create/Modify

```
NEW:
  backend/apps/clarity/__init__.py
  backend/apps/clarity/db_models.py
  backend/apps/clarity/models/__init__.py
  backend/apps/clarity/models/requests.py
  backend/apps/clarity/routers/__init__.py
  backend/apps/clarity/routers/clusters_router.py
  backend/alembic/versions/xxx_add_clarity_clusters.py
  tests/unit/apps/clarity/__init__.py
  tests/unit/apps/clarity/test_db_models.py
  tests/integration/clarity/__init__.py
  tests/integration/clarity/test_clusters_persistence.py

MODIFY:
  backend/main.py (mount clarity router)
  mcp_server/clarity/server.py (add backend persistence call)
```

---

## Reference Files

| Purpose | File |
|---------|------|
| DB model patterns | `backend/apps/focused/db_models.py` |
| Router patterns | `backend/apps/focused/routers/tools_router.py` |
| X-User-ID extraction | `backend/apps/focused/utils/user_id_extraction.py` |
| Request validation | `backend/apps/focused/models/requests.py` |
| Core models (Base, CoreUser) | `backend/core/models.py` |
