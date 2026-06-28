# Widget-0 — Post-Review Follow-Up (small, non-blocking)

Review verdict: implementation is correct and faithful to the briefing. Tests pass legitimately. These are hardenings, not bug fixes. Items 1 and 2 are worth doing; item 3 is optional/cosmetic. None changes production behavior.

Each item below was checked against the **installed SDK** (`.venv/.../mcp/types.py`), not assumed.

---

## 1. (DO) `test_read_resource_serves_widget` can pass on the FALLBACK html — tighten it

**Problem:** the test asserts:
```python
assert "<!DOCTYPE html>" in content.text or "<html" in content.text
```
But `WIDGET_FALLBACK_HTML` in `resources_dupl.py` *also* begins with `<!DOCTYPE html>`. So if the placeholder file ever fails to load (path wrong, file deleted, permission error), `_load_widget_html()` returns the fallback "Widget failed to load" page, and **this test still passes green** — silently serving the error page as if it were the widget. That is exactly the kind of silent-degradation failure the briefing's widget-bundle section warns about.

**Fix:** assert on a string unique to the *real* placeholder, not the DOCTYPE both share. The placeholder (`widgets/mindsort-dashboard-claude.html`) contains `MindSort Widget (placeholder)`. The fallback does not.

```python
assert "MindSort Widget (placeholder)" in content.text
```
Keep the existing non-empty / DOCTYPE assertions if you like, but add the unique-marker assertion so the test fails when the fallback is served. *What bug this now catches that it didn't before:* placeholder file not found at the resolved `WIDGET_PATH` → fallback served → test now red instead of green.

**Optional companion (cheap):** add one direct assertion that the real load path works — i.e. that `WIDGET_HTML` (the module-level loaded value) is NOT equal to `WIDGET_FALLBACK_HTML`. That guards the load itself, independent of `read_resource`:
```python
from mcp_server.mindsort_claude.handlers.resources_dupl import WIDGET_HTML, WIDGET_FALLBACK_HTML
assert WIDGET_HTML != WIDGET_FALLBACK_HTML
```

---

## 2. (DO) Add a smoke test for `list_resource_templates()` — currently zero tests call it

**Status checked:** I verified against the installed SDK that `ResourceTemplate` accepts `_meta` (it declares `meta: ... = Field(alias="_meta")` + `extra="allow"`), so this function will **not** raise. This is NOT a latent crash. But no test calls `list_resource_templates()` at all, so a future edit that breaks it (e.g. malformed `_meta`, wrong field name) would go uncaught.

**Fix:** one minimal behavior test, mirroring the `list_resources` test:
```python
@pytest.mark.asyncio
async def test_list_resource_templates_returns_template(set_dev_env):
    """list_resource_templates() returns one template with matching URI and metadata split."""
    from mcp_server.mindsort_claude.handlers.resources_dupl import (
        list_resource_templates, WIDGET_URI, WIDGET_MIME_TYPE,
    )
    templates = await list_resource_templates()
    assert len(templates) == 1
    t = templates[0]
    assert t.uriTemplate == WIDGET_URI
    assert t.mimeType == WIDGET_MIME_TYPE
    # same metadata-split rule as the resource
    assert "domain" in t.meta["ui"]
    assert "resourceUri" not in t.meta["ui"]
```
Note: `uriTemplate` is a plain `str` in the SDK (not `AnyUrl`), so no `str(...)` coercion needed here — unlike `Resource.uri`.

---

## 3. (OPTIONAL / cosmetic) Align the annotations assignment to PG's unconditional form

**Status checked:** the current code does:
```python
if hasattr(tool, "annotations"):
    tool.annotations = annotations
```
I verified `Tool.annotations` is a declared field on the installed SDK (`annotations: ToolAnnotations | None = None`), so `hasattr(...)` is **always True** on every `Tool` instance — the guard can never skip the assignment in this SDK version. So this is **not a bug and not a risk** right now; it's a carried-over OpenAI-era defensive pattern. PG (the proven Claude reference) does it unconditionally:
```python
tool.annotations = mcp_types.ToolAnnotations(...)
```
If you want consistency with PG, drop the `hasattr` guard. If you'd rather not touch working code before Widget-A, leave it — it does no harm. Your call; I lean "align, because divergence from the proven reference is a future-confusion cost for zero benefit."

---

## NOT changing (verified, leave alone)

- **`str(resource.uri)` comparisons in tests** — correct. `Resource.uri` is `AnyUrl` in the SDK; the `str(...)` coercion the tests use is right. The "AnyUrl to string" fixes Claude Code already applied were necessary and correct.
- **Unknown-URI test passing a bare string `"ui://does-not-exist"`** — fine. `ReadResourceRequestParams.uri` is `AnyUrl`; Pydantic coerces the string on construction. Test is valid.
- **Tool-level `domain` omission** — MindSort ships `{"ui": {"resourceUri": ...}}`; PG ships `{"ui": {"resourceUri": ..., "domain": ...}}`. MindSort follows the briefing's metadata-split rule. **Do NOT add `domain` to tool `_meta` now.** This is an empirical question for the Widget-A live-host smoke test (does Claude's host use tool-level `domain` for prefetch?), tracked separately. Leave as-is until smoke-tested.

---

## Still REQUIRED before "done" (process, not code)

- **Establish the pre-existing test baseline by actually running `pytest tests/unit/ -q`.** pytest was not installed in the implementation environment, so "35 pass / no regressions" is currently **unconfirmed by anyone**. The "no new failures vs. the known-5 baseline" gate in the Widget-0 DoD has not been verified. Run it (locally or wherever pytest is available); confirm the failing-test IDs match the inherited `clarity` resource-URL set and that count is 5. If different, STOP and report.

After items 1 and 2 land and the baseline run is confirmed, Widget-0 is done and Widget-A can be re-scoped against the real shapes this increment produced.
