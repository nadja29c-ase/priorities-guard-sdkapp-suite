Claude Code Briefing: Clarity Increment 03 - Behavioral Tags
Context
Clarity clusters user thoughts. Tags add behavioral hints signaling "this cluster requires a different mental mode than just execute."
Feature Spec
Tags:

Fixed list only: decide, experiment, research, validate, unblock, delegate, automate, learn, align
Optional - LLM picks only when user intent is clear and dominant
Max 3 per cluster/subcluster
Applied to clusters AND subclusters (not thought items)

Purpose: Behavioral heuristic - helps user know HOW to approach the cluster, not what it contains.
Data Model Changes
pythonALLOWED_TAGS = ["decide", "experiment", "research", "validate", "unblock", "delegate", "automate", "learn", "align"]

class SubclusterInput(BaseModel):
    subcluster_name: str
    thought_items: List[str]
    tags: List[str] = []  # Optional, max 3, from ALLOWED_TAGS

class ClusterInput(BaseModel):
    cluster_name: str
    thought_items: List[str] = []
    subclusters: List[SubclusterInput] = []
    tags: List[str] = []  # Optional, max 3, from ALLOWED_TAGS
```

### Validation Rules
- `tags` optional (empty list valid)
- Max 3 tags per cluster/subcluster
- Each tag must be in `ALLOWED_TAGS`
- Invalid tag → validation error

### Files to Modify
```
mcp_server/clarity/
├── server.py              # Models, schema, tool description
├── tools.py               # Pass through tags
└── clarity-clusters.html  # Render tag pills

tests/unit/mcp/
└── test_clarity_tools.py  # Tag validation tests
```

### Tool Description Addition
```
BEHAVIORAL TAGS (optional, max 3 per cluster/subcluster):

Tags signal the cluster requires a different mental mode than normal execute-and-done work.
Only tag when user intent is clear and dominant in the cluster.

Available tags:
- "decide" → contains choices/tradeoffs needing resolution
- "experiment" → contains ideas/hypotheses to test
- "research" → contains unknowns needing investigation
- "validate" → contains assumptions to verify
- "unblock" → contains dependencies or blockers
- "delegate" → contains work for others
- "automate" → contains repetitive work to systematize
- "learn" → contains skill gaps requiring knowledge acquisition
- "align" → contains items needing discussion/agreement with others

No tag is better than a forced tag. Only use when genuinely helpful.
JSON Schema Addition
python"tags": {
    "type": "array",
    "items": {
        "type": "string",
        "enum": ["decide", "experiment", "research", "validate", "unblock", "delegate", "automate", "learn", "align"]
    },
    "maxItems": 3,
    "description": "Optional behavioral tags (max 3). Only use when intent is clear and dominant."
}
```

### Widget Rendering

Tag pills at bottom of cluster/subcluster card:
```
┌─────────────────────────────────────┐
│ Cluster Name                   [5]  │
│ • thought 1                         │
│ • thought 2                         │
│                                     │
│ ┌────────┐ ┌──────────┐             │
│ │ decide │ │ delegate │             │
│ └────────┘ └──────────┘             │
└─────────────────────────────────────┘
Styling:

Pills at bottom of container
Neutral color (use existing --pill-bg, --pill-text)
Same styling for cluster and subcluster tags
Lowercase text

Test Cases
TestInputExpectedNo tagstags: []ValidValid single tagtags: ["decide"]ValidValid max tagstags: ["decide", "learn", "align"]ValidToo many tagstags: ["a", "b", "c", "d"]Validation errorInvalid tag valuetags: ["urgent"]Validation errorTags on clustercluster with tagsTags in outputTags on subclustersubcluster with tagsTags in output
Logging
Add to existing log events:
pythonlogger.info("clarity.tool.validation_success",
            cluster_count=...,
            subcluster_count=...,
            tag_count=total_tags,  # NEW
            ...)
Success Criteria

 ALLOWED_TAGS constant defined
 Pydantic models validate tags (max 3, allowed values only)
 JSON schema includes tags with enum constraint
 Tool description explains tag purpose and usage
 Widget renders tag pills at bottom of cluster/subcluster
 Tags use neutral styling aligned with OpenAI SDK
 All tests pass