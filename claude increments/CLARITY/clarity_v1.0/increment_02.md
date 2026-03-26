Claude Code Briefing: Clarity Hotfix - Remove Incorrect XOR Constraint
Problem
Current implementation enforces XOR validation: cluster must have thought_items OR subclusters, not both. This is wrong.
Correct Behavior
A cluster can have:

✅ thought_items only (flat)
✅ subclusters only (nested)
✅ Both thought_items AND subclusters (mixed: some items grouped, some ungrouped)
❌ Both empty (invalid)

Example Valid Mixed Cluster
{
  "cluster_name": "Marketing",
  "thought_items": ["Review Q1 budget", "Call agency"],
  "subclusters": [
    {"subcluster_name": "Social Media", "thought_items": ["Post schedule", "Analytics"]},
    {"subcluster_name": "Events", "thought_items": ["Conference booth"]}
  ]
}
```

### Files to Modify

**`server.py`:**
- Update `ClusterInput.validate_xor` → rename to `validate_not_empty`
- Only reject if BOTH `thought_items` AND `subclusters` are empty
- Update JSON schema description to reflect correct behavior
- Update tool description

**`tools.py`:**
- Update `cluster_raw_thoughts()` to handle mixed case
- `sum_thought_items` = direct items + all subcluster items

**`clarity-clusters.html`:**
- Render both: ungrouped items first, then subclusters below
- Remove item truncation limits (show all items)

**`tests/unit/mcp/test_clarity_tools.py`:**
- Remove `test_both_populated_raises_validation_error`
- Add `test_mixed_cluster_valid` (both populated = valid)
- Add `test_mixed_cluster_output` (formatting test)
- Update test docstrings

### Widget Rendering for Mixed Cluster
```
┌─────────────────────────────────────┐
│ CLUSTER NAME                   [7]  │
│                                     │
│ • ungrouped item 1                  │
│ • ungrouped item 2                  │
│                                     │
│  ┌─────────────────────────────┐    │
│  │ Subcluster A           [3]  │    │
│  │ • grouped item 1            │    │
│  │ • grouped item 2            │    │
│  │ • grouped item 3            │    │
│  └─────────────────────────────┘    │
│                                     │
│  ┌─────────────────────────────┐    │
│  │ Subcluster B           [2]  │    │
│  │ • grouped item 4            │    │
│  │ • grouped item 5            │    │
│  └─────────────────────────────┘    │
└─────────────────────────────────────┘
Success Criteria

 Mixed clusters (both populated) pass validation
 Empty clusters (both empty) fail validation
 Widget renders ungrouped items + subclusters together
 No item truncation - show all items
 sum_thought_items counts all items correctly
 Tests updated and passing
 Subcluster = container. Must have items. ✓