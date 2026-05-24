# Increment: Board Persistence (Explicit Save)

## Summary

Refactor Clarity persistence model from "auto-save on every clustering" to "explicit user-initiated save". User controls when a board becomes the canonical saved version. Only one saved board per user globally.

---

## Architectural Decisions

### Thinking (Ephemeral)
- Different chats can have different boards
- Multiple board iterations within one chat
- `organize_thoughts` no longer persists to DB
- `organize_thoughts` does NOT read from DB (pure computation)
- Board state lives in widget/conversation context only

### Deciding (Explicit Save)
- User clicks [Save] button on widget
- Widget shows confirmation modal FIRST
- Widget calls `save_board` MCP tool via `window.openai.callTool()`
- Confirmation modal: "This will overwrite your previously saved board. Continue?"
- One saved board per user (overwrite semantics)

### Remembering (Retrieval)
- User asks ChatGPT: "Show my saved board" / "Load my saved board"
- `load_saved_board` tool fetches from DB and renders widget
- Same widget used for both tools

---

## Content Hash for Saved State

Widget must know if current board = saved board (for visual indicator).

### Canonical Hash Specification

**Algorithm:** SHA256, full 64 hex characters (no truncation)

**Canonical serialization (MUST be identical on backend and widget):**

1. **Cluster ordering:** Sort clusters alphabetically by `cluster_name`
2. **Item ordering:** Sort `thought_items` arrays lexicographically (case-sensitive)
3. **Subcluster ordering:** Sort subclusters alphabetically by `subcluster_name`
4. **Tag ordering:** Sort `tags` arrays lexicographically
5. **String normalization:** 
   - Trim leading/trailing whitespace
   - NFC Unicode normalization
6. **JSON serialization:** 
   - No whitespace between tokens
   - Keys in explicit fixed order (not alphabetical sort)

**Key order (authoritative, both sides MUST use this order):**
- Cluster object: `cluster_name`, `subclusters`, `tags`, `thought_items`
- Subcluster object: `subcluster_name`, `tags`, `thought_items`
- Root object: `clusters`

Both Python and JS construct objects with keys in this exact order. Neither side uses automatic key sorting (`sort_keys=True` is NOT used).

**Example canonical form:**
```json
{"clusters":[{"cluster_name":"Home","subclusters":[],"tags":[],"thought_items":["buy groceries","call dentist"]},{"cluster_name":"Work","subclusters":[],"tags":["align"],"thought_items":["finish report"]}]}
```

**Implementation:**
```python
# Backend (Python)
import hashlib
import json
import unicodedata

def canonical_hash(clusters: list) -> str:
    def normalize_string(s: str) -> str:
        return unicodedata.normalize('NFC', s.strip())
    
    def normalize_subcluster(s):
        # Key order: subcluster_name, tags, thought_items
        return {
            "subcluster_name": normalize_string(s["subcluster_name"]),
            "tags": sorted([normalize_string(t) for t in s.get("tags", [])]),
            "thought_items": sorted([normalize_string(i) for i in s.get("thought_items", [])]),
        }
    
    def normalize_cluster(c):
        # Key order: cluster_name, subclusters, tags, thought_items
        return {
            "cluster_name": normalize_string(c["cluster_name"]),
            "subclusters": sorted(
                [normalize_subcluster(s) for s in c.get("subclusters", [])],
                key=lambda x: x["subcluster_name"]
            ),
            "tags": sorted([normalize_string(t) for t in c.get("tags", [])]),
            "thought_items": sorted([normalize_string(i) for i in c.get("thought_items", [])]),
        }
    
    normalized = sorted([normalize_cluster(c) for c in clusters], key=lambda x: x["cluster_name"])
    # NO sort_keys=True - key order is determined by dict construction above
    canonical = json.dumps({"clusters": normalized}, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
```

```javascript
// Widget (JavaScript)
async function canonicalHash(clusters) {
    const normalizeSubcluster = (s) => ({
        // Key order: subcluster_name, tags, thought_items
        subcluster_name: (s.subcluster_name || '').trim().normalize('NFC'),
        tags: (s.tags || []).map(t => t.trim().normalize('NFC')).sort(),
        thought_items: (s.thought_items || []).map(i => i.trim().normalize('NFC')).sort(),
    });

    const normalizeCluster = (c) => ({
        // Key order: cluster_name, subclusters, tags, thought_items
        cluster_name: (c.cluster_name || '').trim().normalize('NFC'),
        subclusters: (c.subclusters || [])
            .map(normalizeSubcluster)
            .sort((a, b) => a.subcluster_name.localeCompare(b.subcluster_name)),
        tags: (c.tags || []).map(t => t.trim().normalize('NFC')).sort(),
        thought_items: (c.thought_items || []).map(i => i.trim().normalize('NFC')).sort(),
    });
    
    const normalized = clusters.map(normalizeCluster)
        .sort((a, b) => a.cluster_name.localeCompare(b.cluster_name));
    
    // Key order is determined by object literal construction above
    // JSON.stringify preserves insertion order in modern JS engines
    const canonical = JSON.stringify({ clusters: normalized });
    const encoded = new TextEncoder().encode(canonical);
    const hashBuffer = await crypto.subtle.digest('SHA-256', encoded);
    return Array.from(new Uint8Array(hashBuffer))
        .map(b => b.toString(16).padStart(2, '0')).join('');
}
```

### Hash flow

| Tool | Returns hash? | Source |
|------|---------------|--------|
| `organize_thoughts` | ❌ No | N/A (pure, no DB) |
| `load_saved_board` | ✅ Yes | From DB |
| `save_board` | ✅ Yes | Just computed |

Widget stores `saved_board_hash` locally after `load_saved_board` or `save_board`.

---

## Current State

### Database
- `clarity_clusters` table exists with single-row-per-user (UNIQUE on user_id)
- Columns: id, user_id, cluster_data (JSONB), thoughts_exhausted, correctly_clustered, created_at, updated_at
- Missing: `content_hash` column

### MCP Tools
- `cluster_raw_thoughts` — currently auto-persists on every call
- `get_my_clusters` — retrieves saved board, no widget

### Widget
- `clarity-clusters.html` — renders clusters, no save button, no saved indicator

### Backend Router
- `POST /api/clarity/clusters` — upsert
- `GET /api/clarity/clusters` — retrieve

---

## Required Changes

### 1. Database Migration

Add `content_hash` column to `clarity_clusters`:
- Type: VARCHAR(64)
- Nullable: true (existing rows won't have it)
- Purpose: Compare widget state to saved state

### 2. Tool Renames

| Current | New |
|---------|-----|
| `cluster_raw_thoughts` | `organize_thoughts` |
| `get_my_clusters` | `load_saved_board` |

Update: file names, tool names, descriptions, all references.

**⚠️ Breaking change:** This rename is breaking. No backward compatibility with previous tool names is maintained. All clients must use new tool names after deployment.

### 3. `organize_thoughts` Tool Changes

**Remove:**
- All `persist_cluster()` calls
- Any DB interaction (read or write)

**Response:**
- Returns clustered data only
- Does NOT include `saved_board_hash` (no DB access)
- Widget treats result as unsaved state

**Purpose:** Pure clustering, no persistence, no DB dependency. Fully ephemeral.

### 4. `load_saved_board` Tool Changes

**Add:**
- Widget metadata (`_meta.openai/outputTemplate`) — same widget URI as organize_thoughts
- `saved_board_hash` in response

**Purpose:** Fetch saved board from DB, render widget.

### 5. New `save_board` MCP Tool

**Input schema:**
```json
{
  "clusters": [...],
  "confirmed": true
}
```

**Behavior:**
- If `confirmed !== true` → reject with error message: "Save must be initiated from the widget's Save button"
- If total thought items > 100 → reject with error message: "Board exceeds maximum size (100 items). Remove some items before saving."
- If cluster count > 20 → reject with error message: "Board has too many clusters (max 20 top-level). Consolidate some clusters before saving."
- If any thought item > 500 chars → reject with error message: "One or more items exceed 500 characters. Shorten them before saving."
- If board is empty (0 items) → reject with error message: "Cannot save an empty board. Add some thoughts first."
- If all validations pass → compute hash, upsert to DB, return success
- Return on success: `{ success: true, saved_board_hash: "..." }`
- Return on error: `{ success: false, error: "..." }`

**Item count calculation:**
- Sum all `thought_items` across all clusters
- Sum all `thought_items` in all subclusters
- Total must be ≤ 100

**Logging (for debugging stale saves):**
```python
# In save_board handler
logger.info(
    "clarity.board.saved",
    user_id=user_id,
    new_hash=new_hash,
    previous_hash=existing_hash,  # Fetch before overwrite
    overwrite=existing_hash is not None,
    source="widget",  # Future-proofs if other save sources added
)
```

**Error codes and messages (standardized):**

| Code | Message | When |
|------|---------|------|
| `WIDGET_ONLY` | "Save must be initiated from the widget's Save button" | `confirmed !== true` |
| `TOO_MANY_ITEMS` | "Board exceeds maximum size (100 items). Remove some items before saving." | items > 100 |
| `TOO_MANY_CLUSTERS` | "Board has too many clusters (max 20 top-level). Consolidate some clusters before saving." | clusters > 20 |
| `ITEM_TOO_LONG` | "One or more items exceed 500 characters. Shorten them before saving." | any item > 500 chars |
| `EMPTY_BOARD` | "Cannot save an empty board. Add some thoughts first." | 0 items |
| `NETWORK_ERROR` | "Save failed. Check your connection and try again." | network failure |
| `SERVER_ERROR` | "Save failed. Please try again later." | 5xx response |

Response format on error:
```json
{
  "success": false,
  "error_code": "TOO_MANY_ITEMS",
  "error": "Board exceeds maximum size (100 items). Remove some items before saving."
}
```

**Chat-based save attempts:**
- User says "save my board" → ChatGPT should NOT call this tool
- ChatGPT should respond: "Click the [Save] button on your Clarity board to save it"
- Tool description explicitly forbids direct invocation from chat

**Security:**
- Same auth as other tools (JWT validation)
- `confirmed` flag ensures widget showed modal before calling

**Tool metadata:**
- `openai/widgetAccessible: true` — allows widget to call it via `window.openai.callTool()`

### 6. Backend Router Changes

**POST /api/clarity/clusters:**
- Accept optional `content_hash` in request body
- If not provided, compute server-side
- Store in DB

**GET /api/clarity/clusters:**
- Include `content_hash` in response

### 7. Widget Changes

**Add [Save] button:**
- Position: Header area, next to title
- On click: Show confirmation modal FIRST (do not call tool yet)
- Modal must be dismissed or confirmed before any tool call

**Confirmation modal (REQUIRED before tool call):**
- Text: "This will overwrite your previously saved Clarity board. Continue?"
- Buttons: [Cancel] [Save]
- [Cancel]: Close modal, do nothing
- [Save]: Call `window.openai.callTool("save_board", { clusters, confirmed: true })`

**Flow:**
```
User clicks [Save]
    ↓
Widget shows modal (no tool call yet)
    ↓
User clicks [Cancel] → close modal, done
    OR
User clicks [Save] → call tool with confirmed: true
    ↓
Tool succeeds → update widget to show "✓ Saved"
```

**Add "✓ Saved" indicator:**

Saved state logic (widget-local):
- After `organize_thoughts` → Always unsaved (new clustering)
- After `load_saved_board` → Saved (it IS the saved board), store returned `saved_board_hash`
- After `save_board` → Saved, update stored `saved_board_hash`
- If widget receives new `organize_thoughts` response → unsaved (hash changed)

Visual:
- Saved: Show "✓ Saved" badge near title (green, subtle)
- Unsaved: No badge (default state)

**Hash computation (JavaScript):**
- Used to detect local modifications after load/save
- Must match backend algorithm exactly (see Canonical Hash Specification above)

---

## Tool Descriptions (Updated)

### organize_thoughts
Do not touch this tool description.

### load_saved_board
```
Load your previously saved Clarity board from the database.

WHEN TO CALL:
- User asks to see/show/load/retrieve their saved board
- Start of new conversation when user wants to continue from saved state

Returns the saved board with widget. If no saved board exists, returns empty state.

EMPTY STATE RESPONSE:
When no saved board exists:
{
  "clusters": [],
  "saved_board_hash": null,
  "has_saved_board": false
}

Widget behavior for empty state:
- Show empty state message: "No saved board yet. Create a board and click Save."
- [Save] button disabled (nothing to save)
- No "✓ Saved" indicator

SAVED STATE RESPONSE:
When saved board exists:
{
  "clusters": [...],
  "saved_board_hash": "abc123...",
  "has_saved_board": true
}
```

### save_board
```
Save the current board to database. Overwrites any previously saved board.

WIDGET-ONLY TOOL:
This tool is triggered EXCLUSIVELY by the widget's [Save] button.
The widget MUST show a confirmation modal BEFORE calling this tool.
Do not call this tool directly from conversation.

If user asks to save via chat (e.g., "save my board", "save this"):
→ Direct them to click the [Save] button on the board widget.
→ Do NOT call this tool on behalf of the user.

Input:
- clusters: The board state to save
- confirmed: Must be true (widget shows confirmation modal first)

Behavior:
- If confirmed !== true → reject with error
- If confirmed === true → save to DB, return success + hash
```

---

## Testing Requirements

### Unit Tests

**Backend:**
- Hash computation is deterministic
- Same clusters = same hash
- Different clusters = different hash
- Hash stored and retrieved correctly
- Canonical serialization handles edge cases (empty arrays, unicode, whitespace)
- Unicode normalization: composed and decomposed forms hash identically (NFC)
- Python and JS implementations produce identical hashes for same input

**MCP Tools:**
- `organize_thoughts` does NOT call persist_cluster
- `organize_thoughts` does NOT read from DB
- `organize_thoughts` does NOT return `saved_board_hash`
- `load_saved_board` includes widget metadata
- `load_saved_board` returns `saved_board_hash`
- `load_saved_board` returns `has_saved_board: false` and empty clusters when no saved board
- `load_saved_board` returns `has_saved_board: true` when saved board exists
- `save_board` rejects if `confirmed !== true` with error_code `WIDGET_ONLY`
- `save_board` rejects if `confirmed` is missing
- `save_board` rejects if total items > 100 with error_code `TOO_MANY_ITEMS`
- `save_board` rejects if top-level clusters > 20 with error_code `TOO_MANY_CLUSTERS`
- `save_board` rejects if any item > 500 chars with error_code `ITEM_TOO_LONG`
- `save_board` rejects if board is empty (0 items) with error_code `EMPTY_BOARD`
- `save_board` computes and stores hash when all validations pass
- `save_board` returns `saved_board_hash` on success

Decision:  Removed redundant has_saved_board. Widget derives state from saved_board_hash !== null.

### Integration Tests

**Save flow:**
1. Call `organize_thoughts` with clusters
2. Call `save_board` with same clusters, `confirmed: true`
3. Verify DB has clusters + hash
4. Call `load_saved_board`
5. Verify returned hash matches

**Hash comparison:**
1. Save board A
2. Call `load_saved_board`
3. Verify `saved_board_hash` matches computed hash of A
4. Call `organize_thoughts` with board B
5. Verify response does NOT include `saved_board_hash`

**Overwrite:**
1. Save board A
2. Save board B
3. Load saved board
4. Verify returns B, not A
5. Verify logs show overwrite with previous hash

### Widget Tests (Manual)

- [Save] button visible
- Clicking [Save] shows modal
- Canceling modal does not save
- Confirming modal calls tool
- Success shows "✓ Saved" indicator
- New organize_thoughts result clears saved indicator
- Loading saved board shows "✓ Saved" indicator
- Button disabled during save (no double-click)
- Error toast shown on save failure
- Button re-enabled after error
- Empty state (no saved board): shows message, [Save] disabled

---

## Error Handling & UX

### Save failures

| Error | User message | Widget behavior |
|-------|--------------|-----------------|
| `confirmed !== true` | "Save must be initiated from the widget's Save button" | N/A (shouldn't happen) |
| Items > 100 | "Board exceeds maximum size (100 items). Remove some items before saving." | Re-enable button, close modal |
| Clusters > 20 | "Board has too many clusters (max 20 top-level). Consolidate some clusters before saving." | Re-enable button, close modal |
| Item too long | "One or more items exceed 500 characters. Shorten them before saving." | Re-enable button, close modal |
| Empty board | "Cannot save an empty board. Add some thoughts first." | Re-enable button, close modal |
| Network error | "Save failed. Check your connection and try again." | Re-enable button, show retry |
| Backend error (5xx) | "Save failed. Please try again later." | Re-enable button, show retry |

### Button states

| State | Appearance |
|-------|------------|
| Default | [Save] enabled |
| Saving in progress | [Saving...] disabled, spinner |
| Save succeeded | [Save] enabled, "✓ Saved" badge appears |
| Save failed | [Save] enabled, error toast shown |

### Double-click protection

- Disable button immediately on click
- Re-enable only after response (success or error)
- Prevent modal from being dismissed during save

---

## File Locations

| Component | Path |
|-----------|------|
| Tool: organize_thoughts | `mcp_server/clarity/tools/organize_thoughts.py` (rename from cluster_raw_thoughts.py) |
| Tool: load_saved_board | `mcp_server/clarity/tools/load_saved_board.py` (rename from get_my_clusters.py) |
| Tool: save_board | `mcp_server/clarity/tools/save_board.py` (new) |
| Widget | `mcp_server/clarity/widgets/clarity-clusters.html` |
| Backend router | `backend/apps/clarity/routers/clusters_router.py` |
| DB model | `backend/apps/clarity/db_models.py` |
| Migration | `backend/alembic/versions/xxx_add_content_hash.py` (new) |
| Persistence | `mcp_server/clarity/persistence.py` |

---

## Constraints

- Max 100 total thought items per board (validate in save_board)
- Max 20 clusters per board (top-level only; subclusters do NOT count toward this limit)
- Max 500 characters per thought item string
- Empty boards (0 items) cannot be saved
- Hash algorithm: SHA256, full 64 hex characters
- One saved board per user (existing UNIQUE constraint)
- Widget must work in both light and dark themes
- Last-write-wins for concurrent saves (explicit MVP decision, logged for debugging)

---

## Explicit Design Decisions (MVP)

These are conscious trade-offs, not oversights:

| Decision | Rationale |
|----------|-----------|
| Last-write-wins for concurrent saves | Simple, predictable. Log overwrites for debugging. No optimistic locking complexity. |
| No board history/versioning | MVP scope. User has one canonical board. |
| No merge conflict resolution | User controls when to save. If they save older board, that's their choice. |
| `organize_thoughts` is pure (no DB) | Clean separation. Clustering = computation. Persistence = explicit user action. |
| Full SHA256 (64 chars) | No collision risk. Storage is cheap. |
| Overwrite logs are INFO, not WARN | Expected MVP behavior. Not an error condition. |

**Deprecated DB columns (unused in this increment):**

The following columns exist in `clarity_clusters` but are NOT used by `save_board`:
- `thoughts_exhausted` — Originally for progressive clustering flow. Now unused; may be repurposed for analytics later.
- `correctly_clustered` — Originally for user confirmation. Now unused; explicit save replaces this pattern.

These columns remain in the schema for backward compatibility. They are set to default values (`false`, `null`) on save. Future increments may remove or repurpose them.

---

## Out of Scope

- Multiple named boards
- Board history / versioning
- Merge with saved board button (future increment)
- Shared boards between users