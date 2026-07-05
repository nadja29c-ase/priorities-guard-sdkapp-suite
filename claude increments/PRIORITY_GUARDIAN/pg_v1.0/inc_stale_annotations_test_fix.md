BRIEFING — Fix stale _meta["annotations"] test assertion in PG integration suite

Priority: HIGH — red test on published revenue app erodes "tests are trustworthy" invariant.
Scope: Priority Guardian ONLY (tests/integration/mcp_pg/).
Estimated effort: 1 line change.

---

Problem (discovered 2026-07-05 during inc_92 MindSort work):

`tests/integration/mcp_pg/test_inspect_adapt_integration.py:68-70` asserts:
```python
assert "annotations" in tool_meta
assert tool_meta["annotations"]["readOnlyHint"] is True
```

But PG's `mcp_server/priority_guardian/tools/__init__.py` list_tools() no longer emits `_meta["annotations"]`. It correctly uses typed `tool.annotations = mcp_types.ToolAnnotations(...)` (lines 197-202).

The test is stale — it asserts a key that PG removed when it moved to typed annotations. The test FAILS today (verified by running pytest).

---

Root cause:

When PG's list_tools was fixed to use typed ToolAnnotations (removing the raw dict from _meta), this test was not updated. The test existed to verify annotations were present, but it checked the wrong location after the fix.

---

Required fix:

Update lines 65-70 to check typed `tool.annotations` instead of `tool_meta["annotations"]`:

```python
# Check annotations at Tool level (typed ToolAnnotations object)
assert hasattr(inspect_adapt_tool, "annotations")
assert inspect_adapt_tool.annotations is not None
assert inspect_adapt_tool.annotations.readOnlyHint is True
assert inspect_adapt_tool.annotations.destructiveHint is False
```

---

Acceptance:

1. `pytest tests/integration/mcp_pg/test_inspect_adapt_integration.py::TestToolRegistration::test_tool_listed -v` passes
2. No other PG tests regress
3. Commit with hash; review verifies fix against git show

---

What NOT to do:

- Do NOT add `_meta["annotations"]` back to PG's list_tools — the typed field is correct
- Do NOT touch MindSort or Clarity code
- Do NOT expand scope — this is a one-line test fix
