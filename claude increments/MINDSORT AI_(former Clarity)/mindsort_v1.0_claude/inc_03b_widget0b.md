# Increment MindSort-Claude-Widget-0b: Result-Path Widget URI Translation

**Goal:** Stop successful widget-producing tool results from leaking the OpenAI widget URI to Claude, and make them carry the Claude widget URI instead. Widget-0 fixed the **tool-list** metadata surface; this fixes the **tool-result** metadata surface. Both must be correct or the widget points Claude at an unregistered resource.

**Severity: feature-blocking defect** (consistent with the architecture docs' vocabulary — blocker / feature blocker / submission blocker; nothing is literally shipping yet). Without this, `tools/list` advertises `ui://mindsort-claude/dashboard-v1.html` but successful tool calls return `_meta.ui.resourceUri = ui://widget/clarity-clusters.html?v=1.1.4`. The Claude resource handler only serves the Claude URI and returns empty contents for unknown URIs → widget silently fails to render or depends on ambiguous host fallback.

This is **not** Widget-0 cleanup. It is a separate increment on a different surface (result `_meta`, not list `_meta`), a different file (`tools_dupl.py` dispatcher + `response_adapter_dupl.py` adapter), and independently testable.

---

## Root cause (verified at source — all four handlers read, not assumed)

The shared `clarity/` widget-producing tool handlers each build, on their **success** path:
```python
meta = {
    "ui": {"resourceUri": WIDGET_URI},        # WIDGET_URI imported from clarity.handlers.resources (OpenAI)
    "openai/outputTemplate": WIDGET_URI,
    "openai/toolInvocation/invoking": "...",
    "openai/toolInvocation/invoked": "...",
    "openai/widgetAccessible": True,
    "openai/resultCanProduceWidget": True,
}
return mcp_types.CallToolResult(content=..., structuredContent=..., _meta=meta)
```
The OpenAI `WIDGET_URI` is `ui://widget/clarity-clusters.html?v=1.1.4` (the `?v=` is a static version cache-buster, **not** per-call state — confirmed in `clarity/handlers/resources.py`).

The dispatcher (`mcp_server/mindsort_claude/handlers/tools_dupl.py`) calls `adapt_tool_result(result)` then returns it. `adapt_tool_result` → `_clean_top_meta()` strips only keys starting with `openai/`. **`ui` does not start with `openai/`, so `ui.resourceUri` survives unchanged into the result Claude receives.**

### Leak sites — verified per handler

| Handler | Leaks on |
|---|---|
| `organize_thoughts` | success path |
| `load_saved_board` | success path **AND** persistence-error path (TWO sites — both build the OpenAI `meta`) |
| `start_prioritization_flow` | success path |
| `edit_board` | success path |

Non-widget tools (`read_board_before_editing`, `delete_my_data`) and the `isError`/provenance/`persist_failed` branches return `_meta=None` or no `_meta` — they do not leak. The fix must be harmless on those (no widget metadata injected).

---

## The rule (requirement, constraint, consequence)

**Requirement.** Claude results must not leak platform-specific widget identity from shared `clarity/` results. Widget-producing results must expose the Claude widget URI; non-widget results must expose none.

**Why `ui.resourceUri` must be treated as platform-specific here:** `ui.resourceUri` is *generic* MCP metadata, not a vendor-namespaced key like `openai/*`. It is platform-specific in this codebase only because its current value references the OpenAI widget resource (`ui://widget/clarity-clusters.html?v=1.1.4`). So it cannot be stripped by namespace-prefix matching the way `openai/*` is; it must be stripped by identity (the `ui.resourceUri` key itself) and then the correct Claude value re-supplied.

**Constraint.** The response adapter must remain tool-agnostic — it receives no tool identity and must not infer it.

**Consequence (forced by the code shape, not a design preference).** `adapt_tool_result(result)` takes only the result; it does not know the tool name. Selecting *which* results get the Claude URI requires the tool name. Therefore:

> - The adapter must strip platform-specific widget identity from shared `clarity/` results **without knowing the tool name**.
> - The dispatcher, **or a dispatcher-level helper**, must inject the Claude widget URI **only for verified widget-producing tools, AND only on result paths that carried a widget `ui.resourceUri` on entry** (before the adapter stripped it). See "Inject-by-intent" below for why the had-widget-on-entry condition matters.
> - **Do not pass `tool_name` into `adapt_tool_result()`.** (Doing so would turn the platform-agnostic adapter into a tool-aware adapter/dispatcher hybrid — the exact coupling this constraint exists to prevent.)

Within those bounds, choose the cleanest structure (helper, adapter method, dispatcher block) and preserve the adapter's current responsibilities unless a different structure demonstrably reduces complexity.

### Inject-by-intent (had widget on entry) — NOT inject-by-tool-name alone

Widget-0b is a **pure translation** of existing widget intent: it must not change *whether* any path renders a widget, only *which resource URI* a widget-bearing path points at. Rule:

```
If the shared clarity/ result entered the dispatcher WITH a ui.resourceUri:
    (adapter strips the OpenAI URI)  ->  inject the Claude URI
If the shared clarity/ result entered WITHOUT a ui.resourceUri:
    inject nothing
```

**Why tool-name-alone is wrong:** `load_saved_board` is a widget-producing tool, but its persistence-error path is a *read failure* that returns `clusters: []` and guidance explicitly saying "do NOT tell them they have no board." Today (OpenAI) that error path *does* carry a widget URI — so to preserve parity, the Claude port should too. But the OTHER three tools' error/provenance/`persist_failed` paths carry **no** `ui.resourceUri` (they return `_meta=None`). If the dispatcher injected purely by tool name, it would wrongly add a widget URI to those `_meta=None` error paths — changing behavior, not translating it. Keying injection on "had a widget URI on entry" reproduces each path's existing intent exactly, with no content-sniffing (no `clusters == []` inspection) and no UX decision made inside a metadata fix.

**Mechanic:** the dispatcher must capture whether the *pre-adapter* result carried a widget `ui.resourceUri`, then inject only if (tool is widget-producing) AND (had-widget-on-entry). The adapter stays tool-agnostic and simply strips; the had-widget flag is read in the dispatcher before/around the adapter call, not passed into it.

Net effect:
```
Before (leaked):  _meta.ui.resourceUri = ui://widget/clarity-clusters.html?v=1.1.4
After (widget tool):   _meta.ui.resourceUri = ui://mindsort-claude/dashboard-v1.html
After (non-widget tool): no ui.resourceUri at all
```

**Why strip-then-inject, not overwrite:** overwriting only the one key we know about leaves the door open if the shared handlers later add other platform-coupled `ui.*` keys whose values reference OpenAI resources — they'd leak. Stripping platform-specific widget identity at the boundary by default, and injecting only the Claude identity we control, is the same AS/RS-separation discipline applied to result metadata: platform-specific identity does not cross the boundary implicitly.

### Single source of truth — reuse, do not redefine

- The Claude `WIDGET_URI` is already defined once in `mcp_server/mindsort_claude/handlers/resources_dupl.py` (Widget-0). Import it. Do **not** define a second copy.
- The widget-producing tool set is already defined once as `_WIDGET_PRODUCING_TOOLS` in `mcp_server/mindsort_claude/tools_list_dupl.py` (Widget-0). Reuse that exact set — do not hardcode a second list in the dispatcher. (If importing it from `tools_list_dupl` is awkward, move the set to a neutral module both import; flag if so — do not duplicate it.)

---

## Implementation approach — Copy and Adjust, Never Rewrite

- The adapter change is a **surgical addition** to `_clean_top_meta` (or a sibling helper it calls): strip `ui.resourceUri`. Do not restructure `adapt_tool_result`'s existing guidance/structuredContent logic — it is correct and tested.
- The dispatcher change is a **post-adapter injection block** keyed on `name` AND on whether the pre-adapter result carried a widget `ui.resourceUri`. Do not restructure auth/dispatch.
- Decision to make explicit in the code: when stripping `ui.resourceUri`, if `ui` becomes an empty dict, drop `ui` entirely (don't leave `{"ui": {}}`). Mirror how `_clean_top_meta` already collapses to `None` when empty.
- **`_meta=None` consequence of inject-by-intent:** a result that entered with `_meta=None` (the other three tools' error/provenance/`persist_failed` paths) had **no** widget URI on entry, so it must receive **no** injection — it stays widget-less. (This is the opposite of an earlier draft of this briefing; inject-by-intent means `_meta=None` in ⇒ no widget out.) The only injection target is a path that *had* a widget `ui.resourceUri` on entry.

---

## Scope

### IN
1. `response_adapter_dupl.py` — strip `ui.resourceUri` (and collapse empty `ui`) from result `_meta`, tool-agnostic.
2. `handlers/tools_dupl.py` — capture whether the pre-adapter result carried a widget `ui.resourceUri`; after `adapt_tool_result`, inject the Claude `ui.resourceUri` only when the tool is in the verified widget-producing set AND the result had a widget URI on entry.
3. Tests (unit + integration) per below.

### OUT
- Any change to `clarity/` handlers (never modify — they are correct for OpenAI and under review).
- `tools_list_dupl.py` (Widget-0's surface — already correct).
- `resources_dupl.py`, `server_dupl.py`, discovery, auth.
- The tool-level `domain` question (PG includes it, MindSort omits it) — still parked for Widget-A live-host smoke test. Do not touch.

---

## What NOT to touch
- `mcp_server/clarity/**` — read-only reference.
- The adapter's guidance-move / structuredContent-strip / mutation-safety logic — leave intact; only add resourceUri stripping.
- The dispatcher's auth, error branches, timing — leave intact; only add the post-adapter injection.

---

## Tests

Add to `tests/unit/mcp_claude_mindsort/test_scaffold.py`. Existing tests must pass unchanged.

### Unit tests (adapter level — tool-agnostic stripping)

1. **Adapter strips `ui.resourceUri`** — build a `CallToolResult` with `_meta={"ui": {"resourceUri": "ui://widget/clarity-clusters.html?v=1.1.4"}, "saved_board_hash": "x"}`; after `adapt_tool_result`, `ui.resourceUri` is gone, `saved_board_hash` survives.
2. **Adapter collapses empty `ui`** — `_meta={"ui": {"resourceUri": "..."}}` (only key) → after adapt, `ui` is absent (not `{"ui": {}}`), and if that leaves `_meta` empty it becomes `None`, consistent with existing `_clean_top_meta` behavior.
3. **Adapter still strips `openai/*` and preserves non-platform keys** — regression guard: existing `_clean_top_meta` behavior unchanged (the existing adapter tests already cover this; confirm they still pass).
4. **Adapter is tool-agnostic** — adapter never injects a Claude URI on its own (a result with no `ui` in, has no `ui.resourceUri` out).

### Integration tests (dispatcher level — inject for widget tools only)

Mock the tool handler / auth so the dispatcher can run a tool by name without a real backend (mirror how existing Claude-02 dispatcher tests stub, if any; otherwise stub `get_tool` / `authenticate_request`). The point is the **post-adapter `_meta`**, keyed by tool name.

5. **Widget tool result carries Claude URI** — for each of `organize_thoughts`, `load_saved_board`, `start_prioritization_flow`, `edit_board`: a successful result that *entered* with the OpenAI `ui.resourceUri` *exits* the dispatcher with `_meta.ui.resourceUri == <Claude WIDGET_URI from resources_dupl>`. Parametrize across all four — do not test only one.
6. **The OpenAI URI never survives** — assert the dispatched result's `_meta.ui.resourceUri != "ui://widget/clarity-clusters.html?v=1.1.4"` and does not contain `clarity-clusters`. (Catches a regression where injection is skipped and the stale URI leaks.)
7. **Non-widget tools get no widget metadata** — `read_board_before_editing` and `delete_my_data` results have no `_meta.ui.resourceUri` after dispatch.
8. **`load_saved_board` persistence-error path (had widget on entry → gets Claude URI)** — this handler's read-error path carries a widget `ui.resourceUri` on entry (verified at source). Under inject-by-intent it therefore exits with the **Claude** URI — preserving today's OpenAI parity, just translated. Assert: dispatched error-path result's `_meta.ui.resourceUri == <Claude WIDGET_URI>` and does not contain `clarity-clusters`. (Whether this error path *should* render a widget at all is a separate, tracked UX question — NOT decided here.) *Bug this catches:* injection keyed on success/`isError` instead of had-widget-on-entry would skip this path (it has `isError` unset) and leak or drop incorrectly.
9. **`_meta=None` / no-widget-on-entry path gets NO injection** — a widget-producing tool result that entered with `_meta=None` or with no `ui.resourceUri` (e.g. the `persist_failed` path of `organize_thoughts`/`start_prioritization_flow`/`edit_board`) exits the dispatcher with **no** `ui.resourceUri`. Inject-by-intent must NOT add a widget to a path that never had one. *Bug this catches:* inject-by-tool-name-alone, which would wrongly add a Claude widget URI to these error paths.
10. **Idempotence** — applying the full dispatcher transformation (adapt + inject) twice to the same widget-tool result produces the same `_meta.ui.resourceUri` (the Claude URI), not a stripped or doubled value. *Why this matters:* strip-then-inject should be idempotent by construction (second strip removes the Claude URI it can't distinguish from any other `ui.resourceUri`, second inject re-adds the same Claude URI). But if someone later makes the strip step OpenAI-specific (e.g. only strips values containing `clarity-clusters`), idempotence silently breaks and a double-adapt would leak. *Bug this catches:* a strip step that special-cases the OpenAI value instead of stripping the key generically.

For each test, the implementer must state what bug would still pass it.

---

## Production readiness (increment scope)

- **Scalability/latency:** pure in-memory dict manipulation on the result path; no new IO. Negligible.
- **GDPR/retention:** no new persistence, no new personal-data field. Retention-doc trigger not met. No update required.
- **Correctness:** this is the increment that makes the widget actually renderable end-to-end. Without it, Widget-0 + Widget-A produce a widget that can't be fetched from a tool result.

---

## Definition of Done

- [ ] Adapter strips `ui.resourceUri` from result `_meta`, collapses empty `ui`, stays tool-agnostic (injects nothing Claude-specific).
- [ ] Dispatcher injects Claude `ui.resourceUri` (imported from `resources_dupl`, single source of truth) only when the tool is in the verified widget-producing set (reused from `tools_list_dupl`, not re-hardcoded) AND the pre-adapter result carried a widget `ui.resourceUri` (inject-by-intent).
- [ ] A result that entered with `_meta=None` / no widget URI receives NO injection (stays widget-less).
- [ ] All four widget-producing tools' results that *had* a widget URI on entry exit with the Claude URI; the OpenAI `clarity-clusters` URI never survives.
- [ ] `load_saved_board` read-error path (had widget on entry) exits with the Claude URI — parity with OpenAI, translated. The "should this path show a widget at all" UX question is tracked separately, not decided here.
- [ ] Non-widget tools carry no widget `ui.resourceUri`.
- [ ] Zero changes to `clarity/**`, `tools_list_dupl.py`, `resources_dupl.py`, `server_dupl.py`.
- [ ] **No regression in any of the surfaces this increment sits between** (it touches the exact seam between them): Widget-0, Claude-01, Claude-02, Claude-02b. All their existing tests pass unchanged.
- [ ] Full `tests/unit/ --ignore=tests/unit/mcp_focused` run: same known-5 pre-existing failures, no new ones. (Run the baseline BEFORE coding; confirm it matches before claiming no-regression.)
- [ ] Before committing: re-read `doc/OPERATIONS_PREDEPLOY.md`; confirm no additional pre-deploy task applies.

**Scope honesty:** Widget-0b makes the result path point Claude at the right resource. Combined with Widget-0 (list path + resource registration), the widget is now fetchable end-to-end. It is still not *rendered* — that's Widget-A (the actual React UI). No visual verification possible yet.

---

## Notes for the implementer (flag, don't fix)
- **Tracked-separately UX question (do NOT solve in Widget-0b):** should `load_saved_board`'s read-error path (`clusters: []`, guidance "do not tell them they have no board") render a widget at all? Today it does (OpenAI), and Widget-0b preserves that by translating the URI. Whether an empty error-state widget is the right UX is a pre-existing OpenAI-side question, not introduced by the Claude port. File it; don't decide it here.
- If the widget-producing set can't be cleanly imported from `tools_list_dupl` without a circular import (dispatcher ← tools_list ← resources), move the set to a small neutral module both import, and flag it — do NOT duplicate the set.
- If you find a fifth handler emitting `ui.resourceUri` that isn't in the verified four, STOP and report — the verified set may be wrong.
- Verify every edit persisted (re-read after writing).
