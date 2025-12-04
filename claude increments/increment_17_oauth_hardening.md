# Increment 17: OAuth Provider Hardening

## Goal

Close compliance gaps in the inbound OAuth provider. Make it production-ready per architecture docs.

## Scope

**In scope:**
- `backend/core/oauth_provider/*`
- `backend/core/models.py`
- `backend/core/rate_limit.py`

**NOT in scope:**
- Outbound Google OAuth (`backend/apps/focused/routers/oauth_google_router.py`)
- MCP server authentication (already implemented in Increment 7D)

## Reference Documents

- "Priority Guardian" & Focused: Shared Backend — Architecture, Data Flow, Storage Strategy
- Data Retention Strategy__Focused_ 7.pdf
- Compliance Master_Priority Guardian_suite

---

## Part 1: Consent Persistence (CRITICAL GAP)

### Problem

Architecture specifies `core_consents` table for GDPR compliance:

> `core_consents` | Records consent per app + scope (GDPR) | `user_id`, `app_name`, `scope`, `granted_at`, `revoked_at`

**This table does not exist.** `backend/core/models.py` has no `CoreConsent` model.

Currently, `consent_ui.py` only logs to structlog:

```python
request_logger.info("oauth.consent.allowed", ...)  # No database write
```

This breaks:
- GDPR audit trail ("prove what user consented to")
- Right to access ("show me my consent history")
- Revocation tracking

### Tasks

#### 1.1 Create CoreConsent Model

Add to `backend/core/models.py`:

```python
class CoreConsent(Base):
    """
    Records user consent per app and scope (GDPR compliance).
    
    Each row represents consent for a specific scope granted by a user
    to a specific app. Consent can be revoked (revoked_at set).
    """
    __tablename__ = "core_consents"
    
    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core_users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User who granted consent"
    )
    
    app_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="SDK app name (e.g., 'focused')"
    )
    
    scope: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Individual scope consented to (e.g., 'focused.read')"
    )
    
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When consent was granted"
    )
    
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When consent was revoked (NULL if still active)"
    )
    
    __table_args__ = (
        # One active consent per user+app+scope combination
        UniqueConstraint("user_id", "app_name", "scope", name="uq_user_app_scope"),
        Index("ix_consent_user_id", "user_id"),
        Index("ix_consent_app_name", "app_name"),
    )
```

#### 1.2 Create Alembic Migration

Generate migration for the new table:

```bash
cd /Users/nadja/Desktop/Priority\ Guard\ Suite/priority-guardian
poetry run alembic revision --autogenerate -m "add core_consents table"
poetry run alembic upgrade head
```

#### 1.3 Create Consent Service Function

Add to `backend/core/oauth_provider/services/consent_service.py`:

```python
async def record_consent(
    db: AsyncSession,
    user_id: str,
    app_name: str,
    scopes: list[str],
    correlation_id: str | None = None
) -> None:
    """
    Record user consent for scopes (GDPR compliance).
    
    Creates or updates consent records for each scope.
    Uses upsert to handle re-consent after revocation.
    
    Args:
        db: Database session
        user_id: User UUID as string
        app_name: SDK app name (e.g., "focused")
        scopes: List of scopes consented to
        correlation_id: For logging
    """
    # Implementation: for each scope, upsert CoreConsent row
    # If revoked_at was set, clear it (re-consent)
```

#### 1.4 Integrate with Consent UI

In `backend/core/oauth_provider/consent_ui.py`, after user clicks Allow:

```python
# After create_authorization_code() succeeds:
await record_consent(
    db=db,
    user_id=user_id,
    app_name="focused",  # Extract from client metadata
    scopes=scope.split(),
    correlation_id=correlation_id
)
```

#### 1.5 Update Cleanup in conftest.py

Add `core_consents` to the TRUNCATE statement in `tests/conftest.py`.

---

## Part 2: Rate Limiting Verification

### Current State

Rate limiting infrastructure exists in `backend/core/rate_limit.py`. Need to verify it's applied to all OAuth endpoints.

### Tasks

#### 2.1 Verify Rate Limiting on Each Endpoint

Check these endpoints have rate limiting calls:

| Endpoint | File | Expected Limiter | Limit |
|----------|------|------------------|-------|
| `/oauth/focused/authorize` | `authorize.py` | `check_rate_limit` (IP + login_hint) | 20/min |
| `/oauth/focused/token` | `token_endpoint.py` | `rate_limit_token` | 5/min |
| `/oauth/focused/register` | `register_client.py` | `rate_limit_register` | 10/min |
| `/oauth/focused/revoke` | `revoke.py` | `rate_limit_revoke` | 10/min |

#### 2.2 Add Missing Rate Limiters

If any endpoint is missing rate limiting, add it.

#### 2.3 Add Rate Limit Tests

Create integration tests that:
1. Hit endpoint at limit → succeeds
2. Hit endpoint over limit → returns 429 with Retry-After header

---

## Part 3: Logging Hygiene Audit

### Tasks

#### 3.1 Search for Sensitive Data in Logs

Search all files in `backend/core/oauth_provider/` for log statements containing:
- `access_token`
- `refresh_token`
- `code_verifier`
- `code` (authorization code)
- `Authorization`
- `client_secret`

#### 3.2 Remediate Any Findings

If any log statement includes sensitive values:
- Remove the sensitive value entirely, OR
- Use first 6 characters + `...[redacted]` if presence must be logged

#### 3.3 Verify No Token Logging

Confirm these files never log full tokens:
- `token_service.py`
- `token_endpoint.py`
- `consent_service.py`
- `authorize.py`

---

## Part 4: Orphan User Cleanup (Documentation Only)

### Problem

Users who:
- Start OAuth but abandon before completion
- Let tokens expire and re-authorize (creating new user)

...leave orphan `core_users` rows.

Architecture specifies:
> "Accounts with no active OAuth connections or consents for ≥ 6 months are automatically anonymized or deleted."

### Task

Document this as a future increment. Create a ticket/TODO for:
- Celery task that runs weekly
- Finds `core_users` with no `oauth_access_tokens` AND no `core_consents` for 6+ months
- Either deletes or anonymizes these rows

**Do not implement in this increment.**

---

## NOT In Scope (Already Correct)

These were reviewed and found to be correctly implemented:

1. **User creation is single-sourced** in `authorize.py::_get_or_create_user()`
2. **`sub` claim is single-sourced** in `jwt/utils.py::create_access_token()`
3. **PKCE is correctly implemented** - verified in `token_service.py` and `validators/pkce.py`
4. **State handling is correct** - provider passes through state, doesn't validate it (that's the client's job)

---

## Acceptance Criteria

1. [ ] `CoreConsent` model exists in `backend/core/models.py`
2. [ ] Alembic migration creates `core_consents` table
3. [ ] `consent_service.py` has `record_consent()` function
4. [ ] `consent_ui.py` calls `record_consent()` on Allow
5. [ ] All 4 OAuth endpoints have rate limiting
6. [ ] No sensitive tokens in any log statements
7. [ ] Tests pass:
   - Consent persistence test
   - Rate limiting 429 tests
8. [ ] `tests/conftest.py` truncates `core_consents`

---

## Test Files

Tests are provided in:
- `tests/unit/oauth_provider/test_increment_17_consent.py`
- `tests/integration/oauth_provider/test_increment_17_rate_limit.py`

Run with:
```bash
poetry run pytest tests/unit/oauth_provider/test_increment_17_consent.py -v
poetry run pytest tests/integration/oauth_provider/test_increment_17_rate_limit.py -v
```
