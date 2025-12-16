# Claude Code Briefing: Increment 10 — Clarity Historical Data Retrieval

## Context

Clarity uses a single-row-per-user persistence model with replace semantics. The database is the source of truth, NOT ChatGPT's context memory.

**Current behavior (broken):**
1. User does brain dump → ChatGPT clusters → tool persists to DB
2. User adds more thoughts in same session → ChatGPT remembers previous thoughts (context)
3. User adds more thoughts in NEW session → ChatGPT has no memory → previous data lost

**Required behavior:**
1. User does brain dump → ChatGPT clusters → tool persists (row 1)
2. User returns (same or new session)
3. ChatGPT calls `get_my_clusters` → retrieves row 1 from DB
4. ChatGPT shows user their existing clusters, asks what to add
5. User adds more thoughts
6. ChatGPT merges old + new, calls `cluster_raw_thoughts` with combined
7. Tool persists combined data (row 2, row 1 deleted)

## Critical Architectural Principle

**DB is the source of truth. ChatGPT context is a cache.**

| State Type | Owner | Reliability |
|------------|-------|-------------|
| Persistent memory | Database | 100% |
| Session working memory | ChatGPT context | Probabilistic |
| User-visible ground truth | Database | Must match DB |

**The tool supplies memory. ChatGPT does the reasoning.**

The tool MUST return historical data TO ChatGPT, NOT silently merge it internally.

| Wrong Approach | Right Approach |
|----------------|----------------|
| Tool fetches historical, merges with new input, returns combined | Separate read tool returns history, ChatGPT merges, write tool persists |
| Intelligence hardcoded in tool | Intelligence stays in model |
| Inflexible merge logic | ChatGPT decides how to merge based on context |
| Fighting the model | Leveraging the model |

**Why this matters:**
- ChatGPT understands semantic relationships between old and new thoughts
- ChatGPT can restructure clusters when new context changes meaning
- ChatGPT can ask user "should I merge these or keep separate?"
- Tool stays dumb and fast — just data in, data out

**The guarantee:**
> "Whenever ChatGPT is uncertain, it can rehydrate from the database."

This is the strongest guarantee possible in this architecture. Forcing retrieval every turn is wasteful and still imperfect.

**Implementation:**
- `get_my_clusters` retrieves and returns historical data to ChatGPT
- `cluster_raw_thoughts` validates and persists whatever ChatGPT sends
- Neither tool contains clustering/merge logic
- Retrieval is triggered by **state uncertainty**, not keywords

## Problem Statement

The `cluster_raw_thoughts` tool persists data but there's no way to retrieve it. Historical data is only accessible if ChatGPT remembers it in context. Cross-session continuity is broken.

## Success Criteria

- [ ] New `get_my_clusters` tool retrieves user's latest cluster snapshot
- [ ] Tool description triggers retrieval based on **state uncertainty**, not keywords
- [ ] ChatGPT calls `get_my_clusters` when uncertain (new session, long context, explicit ask)
- [ ] ChatGPT skips `get_my_clusters` when confident (mid-session, just persisted)
- [ ] Tool returns clusters for ChatGPT to display and merge
- [ ] Cross-session brain dumps preserve and build on previous data
- [ ] Single row per user maintained (replace semantics preserved)
- [ ] `cluster_raw_thoughts` stays write-only (no retrieval logic)

## Technical Requirements

### 1. Backend: GET Endpoint

File: `backend/apps/clarity/routers/clusters_router.py`

Add endpoint to retrieve user's latest cluster snapshot:

```
GET /api/clarity/clusters
Headers: X-User-ID, X-Internal-Secret (production)
Response: 200 with cluster data, or 404 if no snapshot exists
```

**Response model:**
```python
class GetClusterResponse(BaseModel):
    cluster_id: UUID
    cluster_data: dict  # {"clusters": [...]}
    thoughts_exhausted: bool
    correctly_clustered: bool | None
    created_at: datetime
```

**Query:** Select latest row for user (ORDER BY created_at DESC LIMIT 1)

**Security:** Same internal secret verification as POST endpoint.

### 2. MCP Server: Retrieval Function

File: `mcp_server/clarity/persistence.py`

Add function to fetch historical clusters:

```python
async def get_cluster(user_id: str) -> dict | None:
    """
    Fetch user's latest cluster snapshot from backend.
    
    Returns:
        Cluster data dict on success, None if no snapshot exists or on error.
    """
```

**Behavior:**
- Call GET /api/clarity/clusters with X-User-ID and X-Internal-Secret headers
- Return full response dict on 200
- Return `None` on 404 (no previous data)
- Return `None` on error (log warning, don't crash)

### 3. NEW Tool: `get_my_clusters`

File: `mcp_server/clarity/tools/get_my_clusters.py` (new file)

**Purpose:** Read-only tool to retrieve user's existing clusters. ChatGPT calls this FIRST to check for existing data before doing any clustering work.

**Tool metadata:**
```python
NAME = "get_my_clusters"

DESCRIPTION = """
Retrieve the user's current persisted brain dump clusters from the database.

PURPOSE:
The database is the source of truth. Your conversation context is a cache.
Use this tool to rehydrate state whenever you're uncertain about the current state.

CALL THIS TOOL WHEN:
- This is the start of a new conversation involving brain dump / clarity / thoughts
- You are unsure whether you have the user's full previous brain dump
- The conversation may have been long enough that context could be truncated
- The user asks to see, continue, add to, or review their existing brain dump
- The user says "what do I have?", "show my clusters", "where were we?"

DO NOT CALL THIS TOOL IF:
- You already retrieved clusters earlier in the same conversation
- You just persisted clusters via cluster_raw_thoughts (you know the current state)
- You are certain the full state is present in your context

RESPONSE HANDLING:
- If has_history=true: Show user summary of their clusters, ask what to add/change
- If has_history=false: Tell user they're starting fresh, proceed to collect thoughts

The guarantee: Whenever you are uncertain, you can rehydrate from the database.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False
}

REQUIRED_SCOPES = ["clarity.write"]
```

**Handler:**
```python
async def handle(user_id: str, correlation_id: str, arguments: dict) -> CallToolResult:
    """
    Retrieve user's existing clusters.
    
    Returns:
        - clusters: List of cluster objects (empty if none)
        - has_history: Boolean indicating if user has existing data
    """
    cluster_data = await get_cluster(user_id)
    
    if cluster_data is None:
        return CallToolResult(
            content=[TextContent(
                type="text", 
                text="No existing clusters found. User is starting fresh."
            )],
            structuredContent={
                "clusters": [],
                "has_history": False
            }
        )
    
    clusters = cluster_data.get("cluster_data", {}).get("clusters", [])
    
    return CallToolResult(
        content=[TextContent(
            type="text", 
            text=f"Retrieved {len(clusters)} existing clusters."
        )],
        structuredContent={
            "clusters": clusters,
            "has_history": True,
            "last_updated": cluster_data.get("created_at")
        }
    )
```

**No widget:** This is a data retrieval tool, not a display tool. No `outputTemplate` metadata.

**Registration:** Self-register like other tools using `register_tool()`.

### 4. Update `cluster_raw_thoughts` Tool Description

File: `mcp_server/clarity/tools/cluster_raw_thoughts.py`

Update `DESCRIPTION` to clarify merge responsibility:

Add to the beginning of DESCRIPTION:
```python
"""
STATE MANAGEMENT:
- The database is the source of truth for the user's brain dump
- If you're uncertain about the current state, call get_my_clusters first
- When persisting, send ALL clusters (historical + new) in the clusters array
- Never drop historical data unless user explicitly requests it

MERGE RESPONSIBILITY:
- get_my_clusters returns user's previous clusters (if any)
- YOU (ChatGPT) merge previous clusters with new user input
- The tool persists whatever you send — you control the merge logic

... (rest of existing description unchanged)
"""
```

### 5. Response Models

File: `backend/apps/clarity/models/requests.py`

Add response model for GET endpoint:

```python
class GetClusterResponse(BaseModel):
    cluster_id: UUID
    cluster_data: dict
    thoughts_exhausted: bool
    correctly_clustered: bool | None
    created_at: datetime
```

## Files to Create

```
mcp_server/clarity/tools/get_my_clusters.py    — New read-only retrieval tool
```

## Files to Modify

```
backend/apps/clarity/routers/clusters_router.py    — Add GET endpoint
backend/apps/clarity/models/requests.py            — Add GetClusterResponse
mcp_server/clarity/persistence.py                  — Add get_cluster() function
mcp_server/clarity/tools/cluster_raw_thoughts.py   — Update DESCRIPTION with prerequisite
mcp_server/clarity/tools/__init__.py               — Import new tool for registration
```

## Files to Reference (Read-Only)

```
backend/apps/clarity/db_models.py                  — ClarityCluster model
backend/core/config.py                             — settings.INTERNAL_API_SECRET
mcp_server/clarity/http_client.py                  — HTTP client pattern
mcp_server/clarity/config.py                       — BACKEND_URL, INTERNAL_API_SECRET
mcp_server/clarity/tools/cluster_raw_thoughts.py   — Existing tool pattern
mcp_server/clarity/tools/base.py                   — ToolDefinition class
```

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CASE 1: NEW CONVERSATION                                 │
│                    (ChatGPT has no context → uncertain)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. User: "Help me organize my thoughts about Q1 planning"                 │
│                              │                                              │
│                              ▼                                              │
│  2. ChatGPT: "I'm uncertain about prior state" → calls get_my_clusters     │
│                              │                                              │
│                              ▼                                              │
│  3. Tool: GET /api/clarity/clusters → 404 (no data)                        │
│                              │                                              │
│                              ▼                                              │
│  4. Tool returns: {clusters: [], has_history: false}                       │
│                              │                                              │
│                              ▼                                              │
│  5. ChatGPT: "Starting fresh! What's on your mind?"                        │
│                              │                                              │
│                              ▼                                              │
│  6. User shares thoughts → ChatGPT clusters → calls cluster_raw_thoughts   │
│                              │                                              │
│                              ▼                                              │
│  7. Tool persists → row 1 created                                          │
│                              │                                              │
│                              ▼                                              │
│  8. Widget renders clusters                                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                    CASE 2: SAME SESSION, CONTEXT INTACT                     │
│                    (ChatGPT is confident → no retrieval needed)             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  9. User: "Actually, add 'review contracts' to the legal cluster"          │
│                              │                                              │
│                              ▼                                              │
│  10. ChatGPT: "I have context, I'm confident" → NO get_my_clusters call    │
│                              │                                              │
│                              ▼                                              │
│  11. ChatGPT merges new item into existing clusters from context           │
│                              │                                              │
│                              ▼                                              │
│  12. ChatGPT calls cluster_raw_thoughts with updated clusters              │
│                              │                                              │
│                              ▼                                              │
│  13. Tool persists → row 2 replaces row 1                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

            ═══════════ SESSION ENDS / NEW SESSION STARTS ═══════════

┌─────────────────────────────────────────────────────────────────────────────┐
│                    CASE 3: NEW SESSION WITH EXISTING DATA                   │
│                    (ChatGPT has no context → uncertain → rehydrate)         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  14. User: "I want to add more to my brain dump"                           │
│                              │                                              │
│                              ▼                                              │
│  15. ChatGPT: "I'm uncertain about prior state" → calls get_my_clusters    │
│                              │                                              │
│                              ▼                                              │
│  16. Tool: GET /api/clarity/clusters → 200 with row 2 data                 │
│                              │                                              │
│                              ▼                                              │
│  17. Tool returns: {clusters: [...], has_history: true}                    │
│                              │                                              │
│                              ▼                                              │
│  18. ChatGPT: "Here's what you had: [summary]. What else?"                 │
│       (State rehydrated from DB — context is now the cache)                │
│                              │                                              │
│                              ▼                                              │
│  19. User adds new thoughts                                                │
│                              │                                              │
│                              ▼                                              │
│  20. ChatGPT MERGES rehydrated clusters + new thoughts                     │
│                              │                                              │
│                              ▼                                              │
│  21. ChatGPT calls cluster_raw_thoughts with COMBINED data                 │
│                              │                                              │
│                              ▼                                              │
│  22. Tool persists → row 3 replaces row 2                                  │
│                              │                                              │
│                              ▼                                              │
│  23. Widget renders all clusters (history preserved!)                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                    CASE 4: LONG SESSION, CONTEXT TRUNCATION RISK            │
│                    (ChatGPT becomes uncertain → rehydrate)                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ... many turns later in same session ...                                  │
│                                                                             │
│  24. User: "Let's add more thoughts"                                       │
│                              │                                              │
│                              ▼                                              │
│  25. ChatGPT: "Context may be truncated, I'm uncertain"                    │
│                              │                                              │
│                              ▼                                              │
│  26. ChatGPT calls get_my_clusters to rehydrate from DB                    │
│                              │                                              │
│                              ▼                                              │
│  27. State confirmed/recovered → continue with confidence                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Constraints

- GET endpoint must use same security model as POST (X-Internal-Secret)
- Historical retrieval failures are non-blocking (log warning, return empty)
- Single row per user maintained (existing replace semantics unchanged)
- `cluster_raw_thoughts` stays write-only — no retrieval logic added
- No changes to widget or DB schema
- `get_my_clusters` has no widget (data retrieval only)

## Unit Tests

File: `tests/unit/mcp_clarity/test_persistence.py`

| Test | Assertion |
|------|-----------|
| `test_get_cluster_success` | Returns cluster_data when 200 response |
| `test_get_cluster_not_found` | Returns None when 404 response |
| `test_get_cluster_error_handling` | Returns None on network/server error, logs warning |

File: `tests/unit/mcp_clarity/test_get_my_clusters.py`

| Test | Assertion |
|------|-----------|
| `test_handle_with_existing_data` | Returns clusters and has_history=True |
| `test_handle_no_existing_data` | Returns empty clusters and has_history=False |
| `test_handle_persistence_error` | Returns empty clusters on error (graceful degradation) |

## Integration Tests

File: `tests/integration/clarity/test_historical_retrieval.py`

| Test | Setup | Assertion |
|------|-------|-----------|
| `test_get_clusters_returns_latest` | Create cluster for user | GET returns cluster data |
| `test_get_clusters_not_found` | No rows for user | GET returns 404 |
| `test_get_clusters_internal_secret_required` | Production mode, missing secret | 403 Forbidden |
| `test_get_clusters_internal_secret_valid` | Production mode, valid secret | 200 with data |

File: `tests/integration/clarity/test_cross_session_flow.py`

| Test | Setup | Assertion |
|------|-------|-----------|
| `test_full_cross_session_flow` | 1. Call cluster_raw_thoughts (persist) 2. Call get_my_clusters | get_my_clusters returns persisted data |
| `test_merge_preserves_all_data` | 1. Persist 3 clusters 2. Get clusters 3. Persist 5 clusters (merged) | Final row has 5 clusters, old row deleted |

## Out of Scope

- Multiple snapshots per user (history/versioning)
- Explicit "start fresh" / "clear history" tool
- Widget changes
- Schema migrations
- Undo/revert functionality
- Redis caching (see Scalability Notes — not needed for launch)

## Scalability Notes

**Current design handles thousands of concurrent users without changes.**

| Factor | Status | Why |
|--------|--------|-----|
| Query efficiency | ✅ Scalable | `WHERE user_id = ? ORDER BY created_at DESC LIMIT 1` with existing index `idx_clarity_clusters_user_created` → O(1) lookup |
| Data size per user | ✅ Bounded | Single row, replace semantics. Cluster data is finite (user's brain dump, not unbounded logs) |
| Read pattern | ✅ Infrequent | One read per session start, not per turn |
| Connection pooling | ✅ In place | Async SQLAlchemy already configured |

**Future scaling lever (tens of thousands+ active users):**

Add Redis cache in `persistence.py`:

```python
async def get_cluster(user_id: str) -> dict | None:
    # Check Redis first (cache hit = ~1ms)
    cached = await redis.get(f"clarity:clusters:{user_id}")
    if cached:
        return json.loads(cached)
    
    # Cache miss → fetch from DB (~10-50ms)
    data = await fetch_from_db(user_id)
    
    # Cache for 5 minutes (or until invalidated on write)
    if data:
        await redis.setex(f"clarity:clusters:{user_id}", 300, json.dumps(data))
    
    return data
```

Invalidate on write in `persist_cluster()`:
```python
async def persist_cluster(...):
    # ... persist to DB ...
    await redis.delete(f"clarity:clusters:{user_id}")
```

**When to add caching:**
- P95 latency on GET endpoint exceeds 100ms
- DB connection pool saturation observed
- Cost optimization needed for read-heavy workload

**Not needed for launch.** Database with indexed query is sufficient. Add caching as a performance optimization when metrics justify it.

## Verification

After implementation:

**Case 1: New session, no prior data**
1. Start new ChatGPT conversation
2. Mention "brain dump" → verify ChatGPT calls `get_my_clusters` (uncertain)
3. Verify response shows `has_history: false`
4. Add thoughts → verify ChatGPT calls `cluster_raw_thoughts`
5. Verify DB has one row

**Case 2: Same session, context intact**
1. Continue in same conversation
2. Ask to add more thoughts
3. Verify ChatGPT does NOT call `get_my_clusters` (confident)
4. Verify ChatGPT calls `cluster_raw_thoughts` with merged data

**Case 3: New session, prior data exists**
1. Start new ChatGPT conversation
2. Mention "continue brain dump" → verify ChatGPT calls `get_my_clusters` (uncertain)
3. Verify response shows existing clusters, `has_history: true`
4. Verify ChatGPT shows user their previous clusters
5. Add new thoughts → verify merged data persisted
6. Verify DB has single row with all data (old row replaced)