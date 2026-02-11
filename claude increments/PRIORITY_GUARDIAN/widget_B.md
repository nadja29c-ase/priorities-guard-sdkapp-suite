# PG Widget Increment B: CRUD Operations

## Objective

Add all priority and deliverable mutation operations to the Priority Guardian dashboard widget. After this increment: users can create, edit, and delete priorities and deliverables entirely from within the widget via private MCP tools. No LLM round-trip, no token cost for any CRUD action.

---

## Prerequisite: React + Vite Migration Complete

Inc A shipped PG widget as React + Vite (aligned with Clarity). Inc B builds on that foundation. No migration required.

## What Exists (from Widget Inc A)

### Widget (React + Vite)
- `mcp_server/priority_guardian/widget-react/` — Full React project with SDK UI integration
- `src/App.tsx` — Main widget: loads via `getToolOutput()`, refreshes via `callTool("get_priorities")`, renders priority cards + connection status
- `src/components/DeadlineCard.tsx` — Read-only deadline priority card
- `src/components/FlexibleCard.tsx` — Read-only flexible priority card
- `src/components/ConnectionStatus.tsx` — Google connect/disconnect with callTool + openExternal
- `src/types.ts` — Full TypeScript types (Priority, Deliverable, ToolOutputData, window.openai API)
- `src/utils.ts` — `extractStructuredContent()`, `getToolOutput()`, `sortPrioritiesByKeyword()`, `daysUntil()`, `formatDate()`
- `src/main.css` — SDK UI CSS imports (`@import "tailwindcss"`, `@import "@openai/apps-sdk-ui/css"`)
- Build output: `mcp_server/priority_guardian/widgets/pg-dashboard.html` (single compiled HTML)

### MCP Server
- `mcp_server/priority_guardian/tools/__init__.py` — TOOL_REGISTRY with: `connect_google_calendar`, `disconnect_google_calendar`, `create_priority` (public, LLM onboarding), `get_priorities` (public, widget + LLM)
- `mcp_server/priority_guardian/tools/base.py` — ToolDefinition dataclass with `widget_accessible: bool` field
- `mcp_server/priority_guardian/handlers/tools.py` — Dispatcher following MCP Server Implementation Standard
- `mcp_server/priority_guardian/http_client.py` — `backend_get`/`backend_post` helpers
- `mcp_server/priority_guardian/server.py` — Widget resource registration, `_meta` with CSP, embedded resource pattern (copied from Clarity)

### Backend
- `backend/apps/priority_guardian/routers/priorities_router.py` — `GET /priorities` + `POST /priorities` (with keyword auto-assignment, FOR UPDATE locking, IntegrityError fallback)
- `backend/apps/priority_guardian/db_models.py` — `PgPriority` + `PgDeliverable` SQLAlchemy models
- `backend/apps/priority_guardian/models/requests.py` — `CreatePriorityRequest` Pydantic model
- DB tables: `pg_priorities`, `pg_deliverables` with `updated_at` triggers, partial unique index on active keyword

### Existing Patterns to Reuse
- Clarity's `callTool` from widget → `extractStructuredContent()` → re-render pattern (already implemented in PG App.tsx `refreshData()`)
- Clarity's `Button` component import from `@openai/apps-sdk-ui/components/Button`
- PG's `notifyIntrinsicHeight()` call after state changes (already wired)
- PG's badge color constants: `BADGE_COLORS` in DeadlineCard/FlexibleCard (P1 muted blue, P2 muted purple, P3 muted teal)

---

## Architecture: Widget CRUD Data Flow

This is the core pattern for ALL mutations in this increment. Every CRUD action follows the same cycle:

1. User interacts with widget UI (click edit, toggle checkbox, submit form, confirm delete)
2. Widget calls private MCP tool via `window.openai.callTool("tool_name", { args })`
3. MCP tool handler validates args → forwards to backend REST endpoint → returns fresh data
4. Widget receives response via `extractStructuredContent()` → updates local state → re-renders
5. Widget calls `notifyIntrinsicHeight()` to adjust iframe size

**No LLM involvement for any CRUD operation.** The LLM never sees private tools in its tool list.

**Fresh data on every mutation response:** Every mutation tool returns the full updated priority list (same shape as `get_priorities` response). This eliminates stale state issues. Widget replaces its entire data state on each successful mutation — no client-side state diffing.

---

## Backend Endpoints Needed

The existing `priorities_router.py` has GET and POST. This increment adds:

### Priority Mutations

**PUT `/priorities/{priority_id}`** — Update priority fields
- Accepts partial updates (only fields present in body are updated)
- Validates: priority belongs to user, priority exists, field types correct
- For deadline type: name, deadline
- For flexible type: name, weekly_hour_target, checkpoint_date, desired_result
- Type and calendar_keyword are immutable after creation
- Returns: updated priority + fresh full priority list (same shape as GET /priorities)
- 404 if priority not found or wrong user
- 422 for validation failures

**DELETE `/priorities/{priority_id}`** — Hard delete a priority
- Cascading delete of associated deliverables (DB cascade should handle this via relationship config)
- Validates: priority belongs to user, priority exists
- Returns: fresh full priority list (without deleted priority)
- 404 if priority not found or wrong user

### Deliverable Mutations

**POST `/priorities/{priority_id}/deliverables`** — Add deliverable
- Validates: parent priority belongs to user, priority exists
- Required: name (string, max 200 chars)
- Returns: updated priority with new deliverable + fresh full priority list
- 404 if parent priority not found

**PUT `/deliverables/{deliverable_id}`** — Update deliverable
- Accepts partial updates: name, done (boolean)
- Validates: deliverable exists, parent priority belongs to user
- Returns: updated priority + fresh full priority list
- 404 if deliverable not found or wrong user

**DELETE `/deliverables/{deliverable_id}`** — Delete deliverable
- Validates: deliverable exists, parent priority belongs to user
- Returns: fresh full priority list
- 404 if deliverable not found or wrong user

### Response Shape Consistency

All mutation endpoints return the same top-level shape as GET /priorities so the widget can replace its entire state:
```json
{
  "success": true,
  "data": {
    "priorities": [...],
    "google_connection": {...},
    "available_keywords": [...]
  }
}
```

This is a deliberate design choice: one response shape, one widget refresh path, zero special-case handling.

The widget must treat `available_keywords` as authoritative and never compute remaining priority slots client-side. Only the backend knows the true state.

### Trust Boundary

Same as existing endpoints: X-User-ID header trusted because only PG MCP server calls these endpoints after JWT validation. If this assumption changes, add backend-side JWT validation.

### DRY: Extract Response Builder

The GET /priorities endpoint already builds the full response shape (priorities + google_connection + available_keywords). All 5 new mutation endpoints need to return the same shape after their mutation. Extract a shared helper function (e.g., `build_priorities_response(session, user_id)`) that both GET and the mutation endpoints call. Do not duplicate the query + serialization logic across 6 endpoints.

---

## MCP Tools: 6 Private Widget-Only Tools

All 6 new tools follow the MCP Server Implementation Standard:
- One file per tool in `mcp_server/priority_guardian/tools/`
- ToolDefinition with: `widget_accessible = True`, `required_scopes = ["pg.access"]`
- Handler signature: `async def handle(user_id: str, correlation_id: str, arguments: dict) -> CallToolResult`
- All return `structuredContent` with the full refreshed priority list + `assistant_guidance`
- All include `_meta.openai/outputTemplate` pointing to widget URI

### Tool Visibility Enforcement

These tools must appear in TOOL_REGISTRY and list_tools() with:
- `"openai/widgetAccessible": true` — widget can call them
- `"openai/visibility": "private"` — LLM cannot see or call them

The existing `list_tools()` in `__init__.py` already has conditional `_meta` building based on `widget_uri` and `widget_accessible`. It needs a third path for private tools: `widget_accessible = True` but no `resultCanProduceWidget` (they don't spawn new widget instances, they mutate data in the existing one).

Private mutation tools need `outputTemplate` in their tool-call response `_meta` (so the widget receives the structuredContent correctly), but should NOT have `resultCanProduceWidget` in list_tools() `_meta`. Review how the existing `list_tools()` handles this and ensure private tools get `widgetAccessible: true` and `visibility: private` without `resultCanProduceWidget`.

### Tool Definitions

**`add_priority`** — Widget-only priority creation (post-onboarding)
- Private, widgetAccessible
- Accepts: name, type, deadline (if deadline), weekly_hour_target + checkpoint_date + desired_result (if flexible)
- Calls: POST /priorities (same endpoint as create_priority, same backend validation)
- Returns: fresh priority list with assistant_guidance about the new keyword assignment
- Note: This is a separate tool from `create_priority` (which is public/LLM-callable for onboarding). Same backend endpoint, different tool visibility.

**`update_priority`** — Edit priority fields
- Private, widgetAccessible
- Accepts: priority_id (required), partial field object (name, deadline, weekly_hour_target, checkpoint_date, desired_result)
- Calls: PUT /priorities/{priority_id}
- Returns: fresh priority list

**`delete_priority`** — Remove a priority
- Private, widgetAccessible, destructive_hint = True
- Accepts: priority_id (required), confirm (boolean, required, must be true)
- Calls: DELETE /priorities/{priority_id}
- Widget must send confirm=true (enforced by tool handler, not just UI)
- Backend endpoints do NOT need confirm flags — confirmation is purely an MCP tool-level guardrail. The backend just deletes what it's told to delete.
- Returns: fresh priority list

**`add_deliverable`** — Add deliverable to a priority
- Private, widgetAccessible
- Accepts: priority_id (required), name (required, max 200 chars)
- Calls: POST /priorities/{priority_id}/deliverables
- Returns: fresh priority list

**`update_deliverable`** — Toggle done or rename
- Private, widgetAccessible
- Accepts: deliverable_id (required), partial: name, done
- Calls: PUT /deliverables/{deliverable_id}
- Returns: fresh priority list

**`delete_deliverable`** — Remove a deliverable
- Private, widgetAccessible, destructive_hint = True
- Accepts: deliverable_id (required), confirm (boolean, required, must be true)
- Calls: DELETE /deliverables/{deliverable_id}
- Returns: fresh priority list

### MCP Tool Response Pattern

Every mutation tool returns structuredContent in this shape:
```json
{
  "structuredContent": {
    "success": true,
    "data": { "...same as get_priorities response..." },
    "assistant_guidance": "Priority updated. The dashboard reflects the changes."
  },
  "_meta": {
    "openai/outputTemplate": "ui://widget/pg-dashboard.html"
  }
}
```

### http_client.py Extension

Currently has `backend_get` and `backend_post`. Needs:
- `backend_put(path, user_id, correlation_id, data)` 
- `backend_delete(path, user_id, correlation_id)`

Follow the same pattern as existing helpers: construct URL, set X-User-ID header, handle httpx errors, log timing.

---

## Widget UI Changes

### Add Priority Form

**Trigger:** Dashed border button with "+" icon and "Add a new priority" text. Only visible when fewer than 3 active priorities exist. The `available_keywords` array from the backend response tells the widget how many slots remain.

**Form behavior:**
- Opens inline within the widget (not a modal, not a separate page)
- Step 1: Type selection — two cards/buttons: "Deadline" and "Flexible". User picks one.
- Step 2: Fields based on type:
  - Deadline: name (required), deadline date (required)
  - Flexible: name (required), weekly hour target (required), checkpoint date (required), desired result (required)
- Submit button calls `callTool("add_priority", { ...fields })`
- Cancel button closes form, resets state
- Loading state on submit button while callTool is in flight
- Error display below form if tool returns error (e.g., MAX_PRIORITIES_REACHED)

**No HTML `<form>` elements** (compliance A12). Use `onClick` handlers on buttons. Use controlled React state for input values.

**Input components:** Use SDK UI components if available (`Input`, `TextArea`). If not available in `@openai/apps-sdk-ui`, use standard HTML `<input>` and `<textarea>` styled with SDK design tokens.

**Required field enforcement:** Disable submit button until all required fields are filled. Show inline validation messages (e.g., "Name is required") for empty required fields when user attempts to submit.

**Calendar keyword:** Auto-assigned by backend. Do NOT show keyword selection in the form. After successful creation, the new priority card appears with its assigned keyword.

### Priority Card Editing

**Edit button:** Each priority card gets a small edit icon button (pencil icon) in the header row, next to the priority name. Same position referenced in the locked widget spec.

**Inline edit mode:**
- Clicking edit toggles the card into edit mode
- Editable fields become input fields (pre-filled with current values)
- Deadline card: name, deadline date
- Flexible card: name, weekly_hour_target, checkpoint_date, desired_result
- Type and calendar_keyword are NOT editable (shown as read-only)
- "Save" and "Cancel" buttons appear at the bottom of the card
- Save calls `callTool("update_priority", { priority_id, ...changed_fields })`
- Cancel reverts to read-only display

**widgetState for edit mode:** Use `window.openai.setWidgetState()` to persist which card is in edit mode (by priority ID). This survives widget re-renders. Only one card editable at a time.

### Priority Deletion

**Delete button:** Trash icon button in the header row of each priority card (top-right per spec).

**Confirmation flow:**
- Click trash → card shows inline confirmation: "Delete [priority name]? This cannot be undone." with "Delete" (danger) and "Cancel" buttons
- Delete button calls `callTool("delete_priority", { priority_id, confirm: true })`
- Cancel dismisses confirmation
- No browser `confirm()` or `alert()` — inline UI only

### Deliverable CRUD

**Toggle done:** Clicking the checkbox toggles the deliverable's done state via `callTool("update_deliverable", { deliverable_id, done: !current })`. No optimistic UI updates — wait for the server response and re-render from fresh data, same as every other mutation. Consistency across all CRUD operations matters more than saving ~200ms on one action.

**Add deliverable:** "+ Add deliverable" button at bottom of deliverables section. Clicking shows an inline text input with "Add" and "Cancel" buttons. Input is focused automatically. Enter key triggers add. Calls `callTool("add_deliverable", { priority_id, name })`.

**Edit deliverable name:** Double-click on deliverable name (or small edit icon) turns it into an inline text input. Enter or blur saves via `callTool("update_deliverable", { deliverable_id, name: newName })`. Escape cancels.

**Delete deliverable:** Small trash/X icon on each deliverable row. Click → inline confirmation (smaller than priority delete — just "Remove?" with Yes/No). Calls `callTool("delete_deliverable", { deliverable_id, confirm: true })`.

### Loading/Error States per Action

Each mutation should show localized loading state (not a full-widget spinner):
- Button that triggered action shows spinner/disabled state
- Rest of widget remains interactive
- On error: show error message near the action that failed, auto-dismiss after 5 seconds or on next action
- On success: widget re-renders with fresh data from tool response

---

## Design Requirements

### OpenAI Design Tokens (mandatory)

Carried forward from Widget Inc A. All additions must use the same token system.

**New interactive elements:**
- Edit/delete icon buttons: `text-tertiary` default, `text-default` on hover. Use subtle SVG icons (pencil, trash). Size: 16-20px.
- Form inputs: `border-default`, `rounded-md`, `bg-surface`, `text-default`. Focus ring: `ring-2 ring-info` or system default.
- Submit/save buttons: Use SDK `Button` component with `color="primary"` `variant="solid"`.
- Cancel buttons: SDK `Button` with `color="secondary"` `variant="ghost"`.
- Delete confirmation button: SDK `Button` with `color="danger"` `variant="outline"`.
- Inline error text: `text-danger` `text-xs`.
- Add priority dashed button: `border-dashed border-default rounded-xl`, `text-secondary`, hover: `border-strong`.

**Typography continuity:** Same font scale as Inc A. Form labels: `text-xs font-medium text-secondary`. Input text: `text-sm text-default`.

### Dark Mode
All new elements must work in both themes. Semantic tokens auto-switch. Test both modes.

### Accessibility
- All form inputs: associated `<label>` elements (use `htmlFor` + `id`)
- Edit/delete buttons: descriptive `aria-label` (e.g., "Edit priority: Ship v1", "Delete deliverable: Design doc")
- Form validation errors: `aria-describedby` linking input to error message, `role="alert"` on error containers
- Delete confirmations: `aria-live="polite"` for confirmation prompts
- Keyboard: Tab navigates through all interactive elements. Enter submits forms. Escape cancels editing.
- Checkbox toggles: proper `role="checkbox"` with `aria-checked` state

### Responsive
- Form inputs stack vertically on mobile
- Edit mode doesn't cause horizontal overflow
- Delete confirmation fits within card width

---

## SDK Constraints (compliance, carried forward)

- **A11:** No localStorage/sessionStorage. UI state in `widgetState`. Priority data always from server.
- **A12:** No HTML `<form>` elements. onClick handlers only.
- **11b:** No browser cookies.
- **A10:** All errors caught with readable messages.
- Compliance ref 12: No custom fonts.

---

## Reuse from Clarity

### callTool → re-render pattern
Clarity's save_board: `callTool("save_board", data)` → `extractStructuredContent()` → update state. PG uses the same pattern in `refreshData()`. For mutations, follow the same shape but update the full priority list from the response.

### Button component
Clarity imports `Button` from `@openai/apps-sdk-ui/components/Button`. Already used in PG's ConnectionStatus. Use the same import for all new buttons.

### widgetState persistence
Clarity uses `window.openai.setWidgetState()` for scroll position. PG should use it for edit mode state (which card is being edited, form open/closed state).

### NOT reusable from Clarity
- Clarity has no CRUD forms (only save button). PG's add/edit forms are new UI.
- Clarity has no inline editing. This is new for PG.
- Clarity has no delete confirmations. This is new for PG.

---

## Files to Create

| File | Purpose |
|------|---------|
| `mcp_server/priority_guardian/tools/add_priority.py` | Private widget-only priority creation |
| `mcp_server/priority_guardian/tools/update_priority.py` | Private priority field updates |
| `mcp_server/priority_guardian/tools/delete_priority.py` | Private priority deletion |
| `mcp_server/priority_guardian/tools/add_deliverable.py` | Private deliverable creation |
| `mcp_server/priority_guardian/tools/update_deliverable.py` | Private deliverable updates (toggle done, rename) |
| `mcp_server/priority_guardian/tools/delete_deliverable.py` | Private deliverable deletion |
| `mcp_server/priority_guardian/widget-react/src/components/AddPriorityForm.tsx` | Priority creation form |
| `mcp_server/priority_guardian/widget-react/src/components/EditableDeadlineCard.tsx` | Deadline card with edit/delete |
| `mcp_server/priority_guardian/widget-react/src/components/EditableFlexibleCard.tsx` | Flexible card with edit/delete |
| `mcp_server/priority_guardian/widget-react/src/components/DeliverableItem.tsx` | Single deliverable with toggle/edit/delete |
| `mcp_server/priority_guardian/widget-react/src/components/AddDeliverableInput.tsx` | Inline deliverable creation |
| `mcp_server/priority_guardian/widget-react/src/components/DeleteConfirmation.tsx` | Reusable inline delete confirmation |
| `backend/apps/priority_guardian/models/requests.py` | Add UpdatePriorityRequest, CreateDeliverableRequest, UpdateDeliverableRequest |

## Files to Modify

| File | Change |
|------|--------|
| `backend/apps/priority_guardian/routers/priorities_router.py` | Add PUT/DELETE priority + POST/PUT/DELETE deliverable endpoints. Extract `build_priorities_response()` helper. |
| `mcp_server/priority_guardian/tools/__init__.py` | Add 6 new tools to TOOL_REGISTRY, update list_tools() _meta for private tools |
| `mcp_server/priority_guardian/http_client.py` | Add `backend_put` and `backend_delete` helpers |
| `mcp_server/priority_guardian/widget-react/src/App.tsx` | Wire CRUD into cards, add form, pass mutation callbacks |
| `mcp_server/priority_guardian/widget-react/src/types.ts` | Add form state types, edit mode types if needed |
| `mcp_server/priority_guardian/widget-react/src/components/DeadlineCard.tsx` | Replace with EditableDeadlineCard or add edit mode props |
| `mcp_server/priority_guardian/widget-react/src/components/FlexibleCard.tsx` | Replace with EditableFlexibleCard or add edit mode props |

**Decision for Claude Code:** Whether to extend existing DeadlineCard/FlexibleCard with edit mode props or create new Editable* wrapper components is an implementation choice. Either approach is fine as long as read-only rendering from Inc A is not broken and the component structure stays clean. The existing cards are well-structured and could accept edit mode as a prop.

---

## Unit Tests

### Backend Endpoint Tests (Python — pytest)

Test each new endpoint in isolation with a test database session:

**PUT /priorities/{priority_id}:**
- Updates name successfully, returns fresh priority list
- Updates deadline for deadline type
- Updates weekly_hour_target, checkpoint_date, desired_result for flexible type
- Rejects update to type field (immutable)
- Rejects update to calendar_keyword field (immutable)
- Returns 404 for non-existent priority_id
- Returns 404 when priority belongs to different user
- Returns 422 for invalid field types
- Partial update: only changes fields present in request body

**DELETE /priorities/{priority_id}:**
- Deletes priority and cascading deliverables, returns fresh list
- Returns 404 for non-existent priority_id
- Returns 404 when priority belongs to different user
- After deletion: available_keywords includes the freed keyword
- Deleting last active priority returns empty priorities array

**POST /priorities/{priority_id}/deliverables:**
- Creates deliverable, returns fresh priority list with new deliverable
- Returns 404 for non-existent parent priority
- Returns 404 when parent priority belongs to different user
- Returns 422 for missing name
- Returns 422 for name exceeding 200 chars

**PUT /deliverables/{deliverable_id}:**
- Toggles done to true, returns fresh list
- Toggles done to false, returns fresh list
- Updates name, returns fresh list
- Returns 404 for non-existent deliverable_id
- Returns 404 when parent priority belongs to different user

**DELETE /deliverables/{deliverable_id}:**
- Deletes deliverable, returns fresh list
- Returns 404 for non-existent deliverable_id
- Returns 404 when parent priority belongs to different user

### MCP Tool Handler Tests (Python — pytest)

Test each tool handler with mocked backend responses:

**All 6 tools:**
- Returns correct structuredContent shape on success
- Returns `_meta.openai/outputTemplate` in response
- Returns isError=True with readable message on backend 404
- Returns isError=True with generic message on backend 500
- Raises ToolUsageError for missing required arguments
- Validates argument types (e.g., confirm must be boolean, priority_id must be string)

**Tool-specific:**
- `delete_priority`: rejects when confirm is false or missing
- `delete_deliverable`: rejects when confirm is false or missing
- `add_priority`: passes correct fields for deadline vs flexible type
- `update_priority`: sends only provided fields (partial update)

### Tool Registry Tests (Python — pytest)

- All 6 new tools present in TOOL_REGISTRY
- Private tools have `"openai/widgetAccessible": true` in list_tools() _meta
- Private tools have `"openai/visibility": "private"` in list_tools() _meta
- Private tools do NOT have `"openai/resultCanProduceWidget"` in _meta
- Destructive tools (delete_priority, delete_deliverable) have `destructiveHint: true` in annotations

### http_client Tests (Python — pytest)

- `backend_put` sends PUT with correct path, headers, body
- `backend_delete` sends DELETE with correct path, headers
- Both handle httpx timeout/connection errors gracefully

### Widget Component Tests (React — Vitest + React Testing Library)

**AddPriorityForm:**
- Renders dashed "Add" button when available_keywords is non-empty
- Does NOT render when available_keywords is empty (3 active priorities)
- Clicking "Add" button shows type selection (deadline/flexible)
- Selecting type shows appropriate form fields
- Deadline form requires: name, deadline
- Flexible form requires: name, weekly_hour_target, checkpoint_date, desired_result
- Submit button disabled when required fields empty
- Submit calls `window.openai.callTool("add_priority", { correct args })`
- Cancel closes form and resets state
- Shows error message when callTool fails
- Shows loading state on submit button during callTool

**EditableDeadlineCard / EditableFlexibleCard:**
- Edit button click toggles card into edit mode
- Edit mode shows pre-filled input fields
- Save calls `callTool("update_priority", { priority_id, changed fields })` 
- Cancel reverts to read-only display
- Delete button shows inline confirmation
- Confirming delete calls `callTool("delete_priority", { priority_id, confirm: true })`
- Cancelling delete dismisses confirmation

**DeliverableItem:**
- Checkbox click calls `callTool("update_deliverable", { deliverable_id, done: toggled })`
- Double-click on name enters inline edit mode
- Enter key in edit input calls `callTool("update_deliverable", { deliverable_id, name })`
- Escape key cancels inline edit
- Delete icon click shows confirmation
- Confirming delete calls `callTool("delete_deliverable", { deliverable_id, confirm: true })`

**AddDeliverableInput:**
- "+ Add deliverable" button shows inline text input
- Enter key or "Add" button calls `callTool("add_deliverable", { priority_id, name })`
- Empty name shows validation error
- Cancel closes input

---

## Integration Tests

### Backend Integration (Python — pytest with test DB)

- Full CRUD cycle: create priority → update fields → add deliverables → toggle deliverable → delete deliverable → delete priority. Verify each response returns consistent full priority list.
- Concurrent creation: two simultaneous create requests don't assign same keyword (existing FOR UPDATE lock + partial unique index should handle this)
- Cascade delete: deleting a priority with 3 deliverables returns clean list without those deliverables

### MCP Tool Dispatch Integration (Python — pytest)

- Full dispatch chain for each mutation tool: request → dispatcher auth check → handler → mocked backend → response with correct structuredContent shape
- Private tool dispatch: verify dispatcher correctly handles tools that are widget-accessible but not LLM-visible
- Error propagation: backend 409 (MAX_PRIORITIES_REACHED) flows through tool handler and returns readable structuredContent error to widget

---

## What This Increment Does NOT Include

Explicitly deferred:
- Time allocation bar (Inc C — requires calendar data)
- Weekly report link (Inc C)
- Drag-and-drop reordering
- Priority retirement (distinct from deletion — future feature)
- Deliverable reordering
- sendFollowUpMessage bridges
- Fullscreen/PiP display modes
- Coaching moments for any CRUD action (per locked spec: "No coaching for CRUD in v1")

---

## Validation Criteria (Definition of Done)

1. All 6 mutation tools registered and callable from widget via callTool
2. Add priority form works for both deadline and flexible types with required field enforcement
3. Inline editing works for all editable fields on both card types
4. Delete confirmation UI works for both priorities and deliverables
5. Deliverable toggle (done/not done) works with immediate visual feedback
6. Add deliverable inline input works
7. All mutations return fresh full priority list — no stale state
8. Dark mode works for all new UI elements
9. Keyboard navigation works for all new interactive elements
10. All tests pass (backend endpoints, MCP tools, widget components)
11. Widget builds to single HTML file and renders in ChatGPT
12. Deployed to Render and testable in ChatGPT developer mode
