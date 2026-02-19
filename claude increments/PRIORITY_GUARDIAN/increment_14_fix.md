# Briefing: Increment 14 Fixes — Logging Consistency

## Context

Increment 14 (Startup Schema Validation) is complete. Three small fixes needed for logging consistency and observability.

## Scope

All changes in `backend/main.py`. No new files, no new tests.

## Fix 1: Add validation error logging

The `validation_exception_handler` returns 422 but logs nothing. Add a structured log line for observability.

Inside `validation_exception_handler`, before the `return JSONResponse(...)`:

```python
correlation_id = getattr(_.state, 'correlation_id', 'system')
logger.warning(
    "http.validation_error",
    path=_.url.path,
    correlation_id=correlation_id,
    field_count=len(details),
)
```

Note: The request parameter is currently named `_`. Either rename it to `request` or use `_` directly — just make it work.

## Fix 2: Structured startup log

Replace:
```python
logger.info(f"Starting {settings.APP_NAME} in {settings.ENV} environment")
```

With:
```python
logger.info("app.startup", app=settings.APP_NAME, environment=settings.ENV)
```

## Fix 3: Verify middleware order

Confirm that `CorrelationIDMiddleware` runs before `SecurityHeadersMiddleware` (outermost first). In Starlette, middleware registered last runs first. Current order:

```python
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CorrelationIDMiddleware)
```

This means `CorrelationIDMiddleware` runs first — correct. Add a comment confirming this:

```python
# Middleware runs in reverse registration order (last registered = outermost = runs first)
# CorrelationIDMiddleware must be outermost so correlation_id is available to all inner middleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CorrelationIDMiddleware)
```

## Acceptance Criteria

- [ ] 422 responses logged as `http.validation_error` with path, correlation_id, field_count
- [ ] Startup log uses structured format (`app.startup` event name, no f-string)
- [ ] Middleware order has explanatory comment
- [ ] All existing tests still pass
