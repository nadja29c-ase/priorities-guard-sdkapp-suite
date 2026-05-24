# Increment #26: delete_my_data MCP Tool

## Context

**OpenAI Requirement (Compliance Master C38):**
> "Respect deletion requests promptly" — Data-deletion mechanism required for SDK app submission.

**Implementation:** MCP tool that users invoke via chat. No separate webpage or `data_deletion_url` manifest field required.

**Current State:**
- Clarity has `clarity_clusters` table storing saved boards (one per user)
- OAuth handled via `core_consents` and `core_connections`
- MCP server running on port 8001, FastAPI backend on port 8000

**Scope Decision:**
- Ship `clarity_data` scope only for OpenAI submission
- `account` scope deferred to GDPR compliance increment (before EU launch)

---

## What This Tool Does

| Scope | Deletes | User After | Ships Now? |
|-------|---------|------------|------------|
| `clarity_data` | `clarity_clusters` only | Still connected, can create new board | ✅ Yes |
| `account` | `clarity_clusters` + `core_consents` + revokes OAuth | Must re-authorize | ❌ Deferred |

---

## OpenAI Tool Annotation Requirements

**This is a submission requirement.** Missing or incorrect annotations are a common rejection cause.

### Required Annotations

```python
annotations={
    "destructiveHint": True,
    "readOnlyHint": False,
    "openWorldHint": False  # Only mutates own backend, not external systems
}
```

**Why `openWorldHint: False`?**
- `openWorldHint: True` is for tools that affect external systems (social media, email, third-party accounts)
- This tool only mutates your own database — not external from the app's perspective
- Over-declaring can trigger unnecessary review friction

### Submission Justification (Required for Review)

Reviewers will ask these questions. Answers must be defensible:

| Question | Answer |
|----------|--------|
| **Why is it destructive?** | Permanently removes user's saved Clarity board from database; cannot be undone |
| **What external state changes?** | Deletes rows in `clarity_clusters` table (PostgreSQL, owned by app) |
| **What user control exists?** | User explicitly invokes via chat; tool requires `confirm: true` input; cannot execute without explicit confirmation |

---

## Tool Specification

### Tool Name
`delete_my_data`

### Tool Description (Shown to Model)
```
Permanently deletes the user's saved Clarity board. This cannot be undone. 
Use when user explicitly requests to delete their data.
Requires confirm=true to execute.
```

### Input Schema

```python
{
    "confirm": {
        "type": "boolean",
        "description": "Must be true to confirm deletion. Required.",
        "required": True
    }
}
```

**Why require `confirm: true`?**
- Defense against model regressions
- Hard programmatic guard, not just relying on model behavior
- Reviewers see explicit user control mechanism

**Tool behavior:**
- If `confirm` is missing or `false` → reject with message "Deletion requires explicit confirmation"
- If `confirm` is `true` → proceed with deletion

### Output

**Success:**
```json
{
  "status": "deleted",
  "message": "Your saved Clarity board has been permanently deleted.",
  "deleted": {
    "clarity_clusters": 1
  }
}
```

**Nothing to delete:**
```json
{
  "status": "no_data",
  "message": "No saved board found. Nothing to delete."
}
```

**Confirmation missing:**
```json
{
  "status": "rejected",
  "message": "Deletion requires explicit confirmation. Call again with confirm=true."
}
```

**Error:**
```json
{
  "status": "error", 
  "message": "Failed to delete data. Please try again or contact support@priority-guard.com"
}
```

---

## Backend Endpoint

### Endpoint
`DELETE /api/clarity/data`

### Authentication
- JWT from MCP request (existing pattern)
- Extract `user_id` from token claims

### Request Body
```json
{
  "confirm": true
}
```

### Response Codes

| Code | Meaning |
|------|---------|
| 200 | Deleted successfully (or nothing to delete) |
| 400 | Missing or false `confirm` parameter |
| 401 | Invalid/missing JWT |
| 500 | Database error |

### Transaction Safety (CRITICAL)

**Requirement:** Delete and audit log MUST be in the same database transaction.

```python
async with session.begin():
    # 1. Delete user data
    deleted_count = await delete_clarity_clusters(session, user_id)
    
    # 2. Write audit log (same transaction)
    await write_audit_log(session, user_id, deleted_count)
    
    # 3. Commit happens automatically on context exit
    # If either fails, entire transaction rolls back
```

**Why this matters:**
- If delete succeeds but audit fails → lost compliance trail
- If audit succeeds but delete fails → false record
- Single transaction = atomic operation = consistent state

### What It Deletes

```sql
DELETE FROM clarity_clusters WHERE user_id = :user_id
```

That's it for `clarity_data` scope.

---

## MCP Server Integration

### Location
`mcp_servers/clarity/tools/delete_my_data.py` (new file)

### Tool Registration
Register in `mcp_servers/clarity/server.py` alongside existing tools

### Existing Pattern to Follow
Reference: `organize_thoughts` tool for JWT validation and backend calls

### Confirmation Check (in tool handler)

```python
# Pseudocode - actual implementation up to Claude Code
if not args.get("confirm"):
    return {
        "status": "rejected",
        "message": "Deletion requires explicit confirmation. Call again with confirm=true."
    }
# Proceed with deletion...
```

---

## Confirmation UX

**The tool has TWO layers of confirmation:**

1. **Model layer:** `destructiveHint: true` triggers ChatGPT to confirm user intent before calling
2. **Tool layer:** `confirm: true` input required — hard programmatic guard

### assistant_guidance (in structuredContent)

**After successful deletion:**
```
The user's saved Clarity board has been permanently deleted. Acknowledge this briefly and offer to help them start fresh if they want.
```

**After no data found:**
```
No saved board was found to delete. Let the user know their data is already clear.
```

**After rejection (confirm missing):**
```
Deletion was not confirmed. Ask the user if they're sure they want to permanently delete their saved board.
```

---

## Privacy Policy Update

Add to privacy policy (priority-guard.com/privacy):

> **Deleting Your Data**
> 
> To delete your saved Clarity board, simply ask "delete my data" in your ChatGPT conversation. Your data will be permanently removed immediately.
>
> For complete account deletion including all Priority Guardian apps, email support@priority-guard.com.

---

## File Locations

| Component | Location |
|-----------|----------|
| MCP tool | `mcp_servers/clarity/tools/delete_my_data.py` (new) |
| Backend endpoint | `backend/apps/clarity/routes/data.py` (new or add to existing) |
| Persistence function | `backend/apps/clarity/persistence/clusters.py` (add `delete_cluster`) |
| Tool registration | `mcp_servers/clarity/server.py` (modify) |

---

## Audit Logging

**Table:** `core_tool_audit_log` (existing)

**CRITICAL:** Audit log write MUST be in same transaction as delete.

```python
{
    "user_id": "<UUID>",
    "app_name": "clarity",
    "action": "delete_my_data",
    "result_status": "success" | "no_data" | "rejected" | "error",
    "details": {
        "scope": "clarity_data",
        "rows_deleted": {
            "clarity_clusters": N
        },
        "confirm_provided": True | False,
        "trigger": "user_request"
    }
}
```

---

## Error Handling

| Failure | Tool Response |
|---------|---------------|
| `confirm` missing/false | Return rejected status, prompt for confirmation |
| JWT invalid/expired | Return error with "session expired" message |
| Database unreachable | Return error with "try again" message |
| Delete fails | Return error, log full exception server-side, rollback transaction |
| Audit log fails | Rollback entire transaction (delete not persisted) |
| No data exists | Return success with `no_data` status (not an error) |

---

## Unit Tests

**Location:** `tests/unit/apps/clarity/test_delete_data.py`

| Test Case | Validates |
|-----------|-----------|
| User has saved board, confirm=true → deleted | Returns deleted count = 1 |
| User has saved board, confirm=false → rejected | Returns rejected status |
| User has saved board, confirm missing → rejected | Returns rejected status |
| User has no saved board, confirm=true | Returns no_data status |
| Delete called twice with confirm=true | Second call returns no_data (idempotent) |
| Invalid user_id format | Appropriate error handling |
| Database error during delete | Transaction rolls back, error returned |
| Audit log write fails | Transaction rolls back, delete not persisted |

**Location:** `tests/unit/mcp_servers/clarity/test_delete_my_data_tool.py`

| Test Case | Validates |
|-----------|-----------|
| Tool has correct annotations | destructiveHint=True, readOnlyHint=False, openWorldHint=False |
| Tool input schema requires confirm | confirm is required boolean |
| Tool description accurate | Contains "permanently deletes" and "confirm" |
| Tool returns structuredContent | Has status, message, assistant_guidance |
| JWT extracted correctly | User ID passed to backend |
| Confirm check happens before backend call | Rejected if confirm not true |

---

## Integration Tests

**Location:** `tests/integration/apps/clarity/test_delete_data.py`

| Test Case | Validates |
|-----------|-----------|
| Create board → delete with confirm=true → verify gone | Full flow, board not retrievable after |
| Create board → delete with confirm=false → board still exists | Rejection doesn't delete |
| Delete with confirm=true → try to load board | Returns empty/null, not error |
| Delete → create new board | User can start fresh after deletion |
| Audit log written in same transaction | Entry exists, timestamps match |
| Simulated audit failure → delete rolled back | Board still exists after failed audit |
| JWT validation | Rejects invalid tokens |

**Location:** `tests/integration/mcp_servers/clarity/test_delete_my_data_tool.py`

| Test Case | Validates |
|-----------|-----------|
| MCP tool → backend → database | End-to-end deletion works |
| Tool response format | Matches expected schema |
| Confirmation flow | Tool rejects without confirm, succeeds with confirm |

---

## Acceptance Criteria

1. MCP tool `delete_my_data` registered with correct annotations
2. Tool requires `confirm: true` input to execute deletion
3. Tool rejects with clear message if confirm missing or false
4. Tool deletes `clarity_clusters` row for authenticated user
5. Delete and audit log in SAME database transaction
6. Transaction rolls back if either delete or audit fails
7. Tool returns appropriate status (deleted, no_data, rejected, error)
8. Tool includes `assistant_guidance` in structuredContent
9. Backend endpoint validates JWT
10. Idempotent: calling twice with confirm=true doesn't error
11. All unit and integration tests pass
12. Tool annotations correct: destructiveHint=True, readOnlyHint=False, openWorldHint=False

---

## NOT in Scope (Deferred)

- `account` scope (full erasure) — GDPR increment before EU launch
- Widget UI for deletion — MCP tool only
- Email notification after deletion
- Data export before deletion
- 6-month inactivity cleanup (separate Celery task)

---

## Dependencies

- Clarity MCP server (Increment 12+) — exists
- `clarity_clusters` table — exists
- JWT validation in MCP — exists (Increment 19)
- `core_tool_audit_log` — exists
- Backend routing pattern — exists

---

## Production Checklist

- [ ] Privacy policy updated with deletion instructions
- [ ] Tool annotations reviewed against submission requirements
- [ ] Submission justification document prepared (why destructive, what changes, user control)
- [ ] Transaction wrapping delete + audit log verified in code review
- [ ] Support email (support@priority-guard.com) inbox exists and is monitored
- [ ] Test deletion flow end-to-end in staging before production deploy