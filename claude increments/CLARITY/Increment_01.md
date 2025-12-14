Claude Code Briefing: Clarity Increment - User Confirmations + Subclusters
Context
Clarity is a stateless MCP tool that formats ChatGPT-clustered thoughts into a widget. ChatGPT does all AI reasoning; the MCP server only validates/formats.
Current state: Working prototype with cluster_raw_thoughts tool + widget. No tests. Basic logging (not aligned with shared backend patterns).
Data Model
ClusterRequest (top-level):
├── thoughts_exhausted: boolean       # Required. Gate for tool call.
├── correctly_clustered: boolean|null # Optional. null on first call, true/false on re-cluster.
└── clusters: ClusterInput[]

ClusterInput (per cluster):
├── cluster_name: string
├── thought_items: string[]           # Direct items (flat structure)
└── subclusters: SubclusterInput[]    # Optional groupings

SubclusterInput:
├── subcluster_name: string
└── thought_items: string[]
Validation rules:

thoughts_exhausted required
correctly_clustered optional (null allowed)
Per cluster: EITHER thought_items has content OR subclusters has content (not both)
Empty cluster (both empty) = validation error

Widget Rendering Logic
Flat cluster (subclusters empty):
┌─────────────────────────────────────┐
│ Cluster Name                   [5]  │
│ • thought 1                         │
│ • thought 2                         │
│ • thought 3                         │
└─────────────────────────────────────┘
Nested cluster (subclusters populated):
┌─────────────────────────────────────┐
│ CLUSTER NAME                   [12] │
│                                     │
│  ┌─────────────────────────────┐    │
│  │ Subcluster A           [3]  │    │
│  │ • thought 1                 │    │
│  │ • thought 2                 │    │
│  └─────────────────────────────┘    │
│                                     │
│  ┌─────────────────────────────┐    │
│  │ Subcluster B           [2]  │    │
│  │ • thought 4                 │    │
│  │ • thought 5                 │    │
│  └─────────────────────────────┘    │
└─────────────────────────────────────┘
Files to Modify
mcp_server/clarity/
├── server.py              # Schema, Pydantic models, tool description
├── tools.py               # Validation logic, passthrough
└── clarity-clusters.html  # Conditional flat/nested rendering

tests/unit/mcp/
└── test_clarity_tools.py  # NEW
Tool Description Update
Instruct ChatGPT:

Only call when user confirms thoughts are exhausted (thoughts_exhausted: true)
Decide subclustering based on cluster complexity (many items → subcluster)
On first call: correctly_clustered: null
On re-cluster after user says "no": correctly_clustered: false

Logging Requirements
Align with backend/core/logging.py patterns:

Use structlog.get_logger(__name__)
Structured event names: clarity.tool.validation_success, clarity.tool.validation_failed, clarity.tool.subcluster_detected
Context fields: cluster_count, subcluster_count, thoughts_exhausted, correctly_clustered

Testing Requirements
Create tests/unit/mcp/test_clarity_tools.py:
Test CaseInputExpectedValid flat clusterthought_items: [...], subclusters: []SuccessValid nested clusterthought_items: [], subclusters: [...]SuccessMissing thoughts_exhaustedField absentValidation errorBoth populatedthought_items AND subclusters have contentValidation errorBoth emptythought_items: [], subclusters: []Validation errorcorrectly_clustered nullFirst callValidcorrectly_clustered falseRe-cluster callValidMalformed subclustersMissing subcluster_nameValidation error
Success Criteria

 Pydantic models: ClusterRequest, ClusterInput, SubclusterInput
 JSON schema updated for ChatGPT discovery
 Validation: either/or logic for thought_items vs subclusters
 Tool description guides ChatGPT on confirmation flow
 Widget conditionally renders flat or nested layout
 Subcluster cards visually nested inside parent cluster
 Logging follows structlog patterns
 All unit tests pass: pytest tests/unit/mcp/test_clarity_tools.py