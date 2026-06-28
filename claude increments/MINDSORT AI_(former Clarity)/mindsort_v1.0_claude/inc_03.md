Increment MindSort-Claude-Widget-A: Scaffold + Bridge + Theming + Inline Priority Summary
Goal: Build the Claude MindSort widget foundation and its inline display only: scaffold, @modelcontextprotocol/ext-apps bridge, host theming, and a priority-centric inline summary card.
Independently testable and reviewable at increment scope: at the end of this increment the widget renders a correct, compliant, truthful inline summary of the user's board. No fullscreen. No nested board. No half-wired controls.

Context
MindSort (clarity/) is being extended to the Anthropic MCP Directory.
Server-side Claude work is complete:


Claude-01: scaffold


Claude-02: tool wiring + response adapter


Claude-02b: discovery/resource fix


This increment begins the widget.
The existing OpenAI widget:
clarity/widget-react/
is:


built on window.openai.*


single-view


renders the entire nested board inline


It is NOT the architectural reference.
The architectural reference is:
mcp_server/priority_guardian_claude/widget-react/
which already implements:


ext-apps bridge


host theming


display mode handling


stale bridge handling


ErrorBoundary pattern


Mirror the architecture.
Do not copy PG business logic or UI.

Canonical guidance (READ FIRST)
Read before implementing:


doc/Claude_Compliance/claude_connectors_compliance_master.md


§4K Widget constraints


§4N Theming


§4O Technical requirements




doc/Claude_Compliance/structural_guideline_claude_vs_openai_MindSortAI.md


§3 Platform-specific components


§7 Obligatory vs recommended


§8.6 Widget requirements




Both documents were verified June 2026.

Pre-Implementation
Read:
doc/OPERATIONS_PREDEPLOY.md
No migrations.

Scope
IN
Widget scaffold
mcp_server/mindsort_claude/widget-react/


Vite


React


@modelcontextprotocol/ext-apps



Bridge
Use:
useApp()
from:
@modelcontextprotocol/ext-apps/react
Requirement:


widget remains inline-only in this increment


DO NOT advertise fullscreen


Verify exact capability configuration against:


PG Claude widget


installed ext-apps package types




Do not assume API shape.

Host theming


useHostStyles


transparency recipe


host CSS tokens


light mode


dark mode



Inline priority summary
See data design below.

States


loading


ErrorBoundary


stale bridge


Mirror PG.

OUT (Increment B)


fullscreen


nested board


requestDisplayMode


expand button


View board CTA


any dead controls



Inline Priority Summary
This is:
PRIORITY-CENTRIC
NOT cluster-centric.
The summary shows:

the user's explicitly prioritized entities

regardless of whether they are:


cluster


subcluster


thought item



Example
PrioritiesP1 · Email investor deck     Work › FundraisingP2 · Pricing page     Marketing › Landing pageP3 · Product narrative     Strategy7 clusters · 42 thoughts

Empty state
7 clusters · 42 thoughts · none prioritized yet

Data Rules
These are requirements.
They are NOT implementation instructions.

1. Own-level priorities only
Walk the clusters tree and collect entities whose own:
priority.rank
is set.
Priorities can exist on:
cluster.priority.ranksubcluster.priority.rankthought_item.priority.rank

2. DO NOT use effective rank
DO NOT use:
getEffectiveRank()getEffectiveSubclusterRank()
Those helpers roll child priorities up to parents.
That is explicitly the WRONG semantic.
Example:
Cluster A    Thought Item -> P1
The inline summary must show:
P1 · Thought Item
NOT:
P1 · Cluster A

3. Maximum priorities
Verified in:
clarity/tools/board_utils.py
Facts:
MAX_PRIORITIES = 3
Ranks are unique.
Therefore:
P1P2P3
each map to exactly one entity.
Render:
P1 → P2 → P3

4. Breadcrumbs
Each row renders:
rankentity name/textbreadcrumb
Examples:
Cluster:
P1 · Strategy
Subcluster:
P2 · Fundraising     Work
Thought item:
P3 · Email investor deck     Work › Fundraising
The breadcrumb is derivable from tree position.
No backend change required.
The widget already receives:
structuredContent.clusters
containing the full nested tree.

5. Count line
Render:
total clusterstotal thoughts
Verify whether:


board-level total exists


or


totals must be summed from clusters


Do not assume.

6. Truncation
Long text:


single line


ellipsis


no wrapping explosion



Compliance
The inline design must satisfy:
Data density
3 priority rows+ count line= 4 data points
Within Claude guidance.

No nested scrolling
Flat list only.

No drill-ins
Single view.

Auto-fit height
Short summary.
No fixed height.

No actions
Increment A has zero actions.

Bridge Requirements
Mirror PG.
Requirements only.

useApp


connect via ext-apps


receive tool results


consume:


structuredContent.clusters
MindSort returns:
clusters
NOT PG's:
data
Verify exact path.

useHostStyles


theme


fonts


CSS vars


reapply on host context changes



Stale bridge
Mirror PG:


3 second timeout


stale overlay



ErrorBoundary
Mirror PG.

Theming
DO NOT use OpenAI tokens
Forbidden:
bg-surface-secondarytext-defaultborder-strong@openai/apps-sdk-ui
Those belong to OpenAI.

Use:
var(--color-background-*)var(--color-text-*)var(--color-border-*)
from Claude host styles.

Transparency
Required:
html, body {  margin: 0;  background: transparent;}
and:
<meta name="color-scheme" content="light dark" />
Resource:
_meta.ui.prefersBorder=false
If resource registration is missing:
STOP and report.
Do not silently add server changes.

What NOT to Touch
Do not modify:
clarity/clarity/widget-react/backend/mindsort_claude server files
Widget increment only.

Unit Tests
No host.
No network.
Test:


Own-level priority extraction


Must FAIL if:
getEffectiveRank()
is used.



Sort order


P1P2P3



Breadcrumb derivation


Thought item:
cluster › subcluster
Subcluster:
cluster



Empty state


No priorities:
count-only summary



Counts


Clusters and thoughts correct.



Truncation


Long text truncated.

For each test:
Document:
"What bug would still pass this test?"

Integration Tests
Separate from unit tests.
Mock host / ext-apps bridge.
Test:



Widget mounts.
useApp connects.
Tool result populates summary.




Theming:


light


dark






Stale bridge:
3s timeout → stale overlay.




Fullscreen is NOT advertised.
Verify the widget remains inline-only according to ext-apps capabilities.

Production Readiness
Evaluated at increment scope.
Scalability
Static bundle.
Tree walk over small in-memory board.
No issue.
Deploy note
Widget bundle updates require cache invalidation after deploy.

GDPR / Retention
No new data.
Widget renders backend-governed data.
No increment-level GDPR work.

Latency
Trivial.
No issue.

Tracked but OUT OF SCOPE
Product-level GDPR gap:
Current:


Data Retention Strategy


ROPA


are written in OpenAI/ChatGPT terms.
Missing:


Claude runtime


Anthropic as processor


Claude-specific transfer governance


This is:
Product submission blocker
but NOT:
Increment A blocker
Track it.
Do not fix here.

Definition of Done


Widget scaffold builds


ext-apps bridge works


Inline-only mode verified


Priority summary renders


Own-level priorities only


Empty state works


Anthropic theming correct


Light + dark mode correct


Loading state present


ErrorBoundary present


Stale bridge present


No fullscreen


No requestDisplayMode


No CTA


No dead controls


Unit tests pass


Integration tests pass


Full tests/unit/ suite run


Expected result:
Only the 5 known pre-existing failures remain.No new failures.


Zero changes to:


clarity/clarity/widget-react/backend/