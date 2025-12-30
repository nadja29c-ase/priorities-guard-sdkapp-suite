# Unpack — Increment 3 Briefing

## Clusters Widget (Reuse Clarity Patterns)

**Objective:** Add visual widget to `cluster_questions` tool that displays problem statement + clustered questions.

**Depends on:** Increment 2.1 complete (semantic clustering with themes).

**Produces:** Widget renders after `cluster_questions` call, showing problem statement at top and cluster cards below.

---

## What This Increment Delivers

1. **Unpack widget** — React widget displaying clusters as cards
2. **Widget registration** — Resource handlers for widget serving
3. **Tool integration** — `cluster_questions` returns widget metadata
4. **Copy Summary** — Button to copy markdown summary to clipboard

---

## Reuse from Clarity

| Clarity Component | Reuse in Unpack | Changes |
|-------------------|-----------------|---------|
| `widget-react/` structure | Copy entire scaffold | Rename to `unpack-widget/` |
| `package.json` | Copy, rename package | Change name to `unpack-widget` |
| `main.css` | Copy as-is | None |
| `App.tsx` | Adapt | Remove Save button, add Header with problem statement, add Copy Summary |
| `ClusterCard.tsx` | Adapt | Simplify: theme + questions + insight only (no priority, no tags, no subclusters) |
| `Header.tsx` | Adapt | Show problem statement instead of "Your Clarity Board" |
| `types.ts` | Rewrite | Simpler types for Unpack clusters |
| `utils.ts` | Simplify | Remove priority sorting, keep `getToolOutput` and `truncateText` |
| `handlers/resources.py` | Copy pattern | New WIDGET_URI for unpack |

---

## Widget Layout

```
┌─────────────────────────────────────────────────────┐
│  YOUR UNPACK SUMMARY                                │
│  ─────────────────────────────────────────────────  │
│  Problem: I am trying to get promoted, but my       │
│  manager doesn't notice my work, which costs me     │
│  motivation and I'm thinking about leaving.         │
│                                                     │
│  ┌─────────────────┐  ┌─────────────────┐          │
│  │ Understanding   │  │ How to respond  │          │
│  │ the behavior    │  │                 │          │
│  │ ─────────────── │  │ ─────────────── │          │
│  │ • Why does the  │  │ • Should I talk │          │
│  │   team interrupt│  │   to my manager?│          │
│  │ • Is this       │  │ • Should I      │          │
│  │   intentional?  │  │   address it    │          │
│  │                 │  │   directly?     │          │
│  │ These questions │  │                 │          │
│  │ explore under-  │  │ These questions │          │
│  │ standing the    │  │ explore how to  │          │
│  │ behavior.       │  │ respond.        │          │
│  └─────────────────┘  └─────────────────┘          │
│                                                     │
│  ┌─────────────────┐                               │
│  │ Other Questions │  (if unclustered exists)      │
│  │ ─────────────── │                               │
│  │ • Random Q      │                               │
│  └─────────────────┘                               │
│                                                     │
│  [ Copy Summary ]                                   │
└─────────────────────────────────────────────────────┘
```

---

## File Structure

```
mcp_server/unpack/
├── widget-react/                    # NEW - copy from clarity/widget-react
│   ├── src/
│   │   ├── App.tsx                  # Adapted
│   │   ├── main.tsx                 # Copy as-is
│   │   ├── main.css                 # Copy as-is
│   │   ├── types.ts                 # Rewritten (simpler)
│   │   ├── utils.ts                 # Simplified
│   │   └── components/
│   │       ├── Header.tsx           # Adapted (problem statement)
│   │       ├── ClusterCard.tsx      # Adapted (theme + questions + insight)
│   │       └── QuestionItem.tsx     # NEW (simple list item)
│   ├── package.json                 # Renamed
│   ├── vite.config.ts               # Copy, update output path
│   └── tsconfig.json                # Copy as-is
├── widgets/
│   └── unpack-clusters.html         # Built widget (vite output)
├── handlers/
│   └── resources.py                 # NEW - widget serving
└── tools/
    └── cluster_questions.py         # Updated with widget_uri
```

---

## Types (`types.ts`)

```typescript
// Simplified data contract for Unpack

export interface QuestionCluster {
  id: string
  theme: string
  questions: string[]
  insight: string
}

export interface UnpackData {
  problem_statement: string
  clusters: QuestionCluster[]
  unclustered: string[]
  summary_markdown: string
}

// window.openai API types (copy from Clarity, simplified)
declare global {
  interface Window {
    openai?: {
      theme?: 'light' | 'dark'
      toolOutput?: {
        structuredContent?: UnpackData
        result?: { structuredContent?: UnpackData }
      }
      notifyIntrinsicHeight?: () => void
      widgetState?: Record<string, unknown>
      setWidgetState?: (state: Record<string, unknown>) => void
    }
  }
}

export {}
```

---

## Utils (`utils.ts`)

```typescript
import type { UnpackData, QuestionCluster } from './types'

/**
 * Get unpack data from window.openai.toolOutput
 * Includes defensive mapping for theme/label compatibility
 */
export function getToolOutput(): UnpackData | null {
  const t = window.openai?.toolOutput
  if (!t) return null

  // Try paths (same as Clarity pattern)
  const data = t.result?.structuredContent ?? t.structuredContent
  if (!data) return null

  // Defensive mapping: handle both "theme" and "label" field names
  const clusters: QuestionCluster[] = (data.clusters ?? []).map((c: any) => ({
    id: c.id ?? '',
    theme: c.theme ?? c.label ?? 'Untitled',  // Fallback to label if theme missing
    questions: c.questions ?? [],
    insight: c.insight ?? '',
  }))

  return {
    problem_statement: data.problem_statement ?? '',
    clusters,
    unclustered: data.unclustered ?? [],
    summary_markdown: data.summary_markdown ?? '',
  }
}

/**
 * Truncate text with ellipsis
 */
export function truncateText(text: string | undefined, maxLength = 80): string {
  if (!text || text.length <= maxLength) return text ?? ''
  return text.substring(0, maxLength).trim() + '...'
}

/**
 * Copy text to clipboard
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
```

---

## Header Component (`Header.tsx`)

```typescript
interface HeaderProps {
  problemStatement: string
}

export function Header({ problemStatement }: HeaderProps) {
  return (
    <div className="mb-6">
      <p className="heading-sm text-default mb-2">Your Unpack Summary</p>
      <div className="p-4 bg-surface rounded-xl border border-default">
        <p className="text-sm text-secondary mb-1">Problem</p>
        <p className="text-sm text-default">{problemStatement}</p>
      </div>
    </div>
  )
}
```

---

## ClusterCard Component (`ClusterCard.tsx`)

```typescript
import { Badge } from '@openai/apps-sdk-ui/components/Badge'
import type { QuestionCluster } from '../types'

interface ClusterCardProps {
  cluster: QuestionCluster
}

export function ClusterCard({ cluster }: ClusterCardProps) {
  return (
    <article
      tabIndex={0}
      className="rounded-2xl border border-default bg-surface-secondary p-5 flex flex-col min-h-[120px] shadow-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-ring)]"
      aria-label={`Cluster: ${cluster.theme}, ${cluster.questions.length} questions`}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <h3 className="text-sm font-semibold text-default m-0">
          {cluster.theme}
        </h3>
        <Badge color="secondary" variant="outline" size="sm">
          {cluster.questions.length}
        </Badge>
      </div>

      {/* Questions */}
      <ul className="space-y-2 list-none m-0 p-0 flex-1">
        {cluster.questions.map((q, i) => (
          <li key={i} className="text-sm text-default flex items-start gap-2">
            <span className="text-secondary" aria-hidden="true">•</span>
            <span>{q}</span>
          </li>
        ))}
      </ul>

      {/* Insight */}
      <p className="text-xs text-secondary italic mt-3 pt-3 border-t border-default">
        {cluster.insight}
      </p>
    </article>
  )
}
```

---

## App Component (`App.tsx`)

```typescript
import { useState, useEffect, useCallback } from 'react'
import { Button } from '@openai/apps-sdk-ui/components/Button'
import { Check } from '@openai/apps-sdk-ui/components/Icon'
import type { UnpackData } from './types'
import { getToolOutput, copyToClipboard } from './utils'
import { Header } from './components/Header'
import { ClusterCard } from './components/ClusterCard'

function App() {
  const [data, setData] = useState<UnpackData | null>(null)
  const [isInitialized, setIsInitialized] = useState(false)
  const [copied, setCopied] = useState(false)

  const notifyHeight = useCallback(() => {
    requestAnimationFrame(() => {
      window.openai?.notifyIntrinsicHeight?.()
    })
  }, [])

  const loadData = useCallback(() => {
    const output = getToolOutput()
    if (output) {
      setData(output)
      setIsInitialized(true)
      notifyHeight()
    }
  }, [notifyHeight])

  useEffect(() => {
    loadData()
    window.addEventListener('openai:set_globals', loadData, { passive: true })
    return () => window.removeEventListener('openai:set_globals', loadData)
  }, [loadData])

  const handleCopy = async () => {
    if (!data?.summary_markdown) return
    const success = await copyToClipboard(data.summary_markdown)
    if (success) {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  if (!isInitialized || !data) {
    return (
      <div className="p-6 text-center text-sm text-secondary bg-surface-secondary rounded-xl">
        Loading...
      </div>
    )
  }

  return (
    <main
      role="main"
      aria-label="Unpack Summary"
      className="bg-surface-secondary rounded-2xl px-8 py-6 -m-4"
    >
      <Header problemStatement={data.problem_statement} />

      {/* Cluster Cards */}
      {data.clusters.length > 0 ? (
        <div className="grid gap-4 grid-cols-[repeat(auto-fit,minmax(240px,1fr))]">
          {data.clusters.map((cluster) => (
            <ClusterCard key={cluster.id} cluster={cluster} />
          ))}
        </div>
      ) : (
        <div className="p-6 text-center text-sm text-secondary bg-surface rounded-xl">
          No clusters to display.
        </div>
      )}

      {/* Unclustered Questions */}
      {data.unclustered.length > 0 && (
        <div className="mt-4 p-4 bg-surface rounded-xl border border-default">
          <h3 className="text-sm font-semibold text-default mb-2">Other Questions</h3>
          <ul className="space-y-1 list-none m-0 p-0">
            {data.unclustered.map((q, i) => (
              <li key={i} className="text-sm text-secondary flex items-start gap-2">
                <span aria-hidden="true">•</span>
                <span>{q}</span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-secondary italic mt-2">
            These questions didn't fit a clear theme.
          </p>
        </div>
      )}

      {/* Copy Summary Button */}
      <div className="sticky bottom-0 pt-4 pb-2 bg-surface-secondary">
        <div className="flex items-center gap-3">
          <Button
            color="primary"
            variant="outline"
            onClick={handleCopy}
            aria-label="Copy summary to clipboard"
          >
            {copied ? 'Copied!' : 'Copy Summary'}
          </Button>
          {copied && (
            <span className="flex items-center gap-1 text-xs text-success">
              <Check className="w-3.5 h-3.5" aria-hidden="true" />
            </span>
          )}
        </div>
      </div>
    </main>
  )
}

export default App
```

---

## Resource Handler (`handlers/resources.py`)

```python
"""
Resource handlers for Unpack MCP.

Handles widget resource discovery and serving.
"""

from pathlib import Path
from typing import List

import structlog
from mcp import types as mcp_types

logger = structlog.get_logger(__name__)

# Widget configuration
WIDGET_URI = "ui://widget/unpack-clusters.html"
WIDGET_PATH = Path(__file__).parent.parent.joinpath("widgets/unpack-clusters.html")

# Lazy-loaded cache
_widget_html_cache: str | None = None


def get_widget_html() -> str:
    """Load widget HTML lazily (not at import time)."""
    global _widget_html_cache
    if _widget_html_cache is None:
        if not WIDGET_PATH.exists():
            raise FileNotFoundError(f"Widget not found: {WIDGET_PATH}")
        _widget_html_cache = WIDGET_PATH.read_text()
        logger.debug("widget.loaded", path=str(WIDGET_PATH), size=len(_widget_html_cache))
    return _widget_html_cache


async def list_resources() -> List[mcp_types.Resource]:
    """List available resources (widgets) for discovery."""
    return [
        mcp_types.Resource(
            name="unpack_clusters_widget",
            title="Unpack Clusters Widget",
            uri=WIDGET_URI,
            description="Widget for displaying clustered questions",
            mimeType="text/html+skybridge",
            _meta={
                "openai/outputTemplate": WIDGET_URI,
                "openai/widgetAccessible": True,
                "openai/resultCanProduceWidget": True,
            },
        )
    ]


async def list_resource_templates() -> List[mcp_types.ResourceTemplate]:
    """List resource templates for discovery."""
    return [
        mcp_types.ResourceTemplate(
            name="Unpack Clusters Widget",
            title="Unpack Clusters Widget",
            uriTemplate=WIDGET_URI,
            description="Widget for displaying clustered questions",
            mimeType="text/html+skybridge",
            _meta={
                "openai/outputTemplate": WIDGET_URI,
                "openai/widgetAccessible": True,
                "openai/resultCanProduceWidget": True,
            },
        )
    ]


async def handle_read_resource(req: mcp_types.ReadResourceRequest) -> mcp_types.ReadResourceResult:
    """Handle resource read requests."""
    uri_str = str(req.params.uri)

    if uri_str == WIDGET_URI:
        try:
            html = get_widget_html()
            return mcp_types.ReadResourceResult(
                contents=[
                    mcp_types.TextResourceContents(
                        uri=WIDGET_URI,
                        mimeType="text/html+skybridge",
                        text=html,
                    )
                ]
            )
        except FileNotFoundError as e:
            logger.error("widget.not_found", error=str(e))
            return mcp_types.ReadResourceResult(
                contents=[],
                _meta={"error": str(e)},
            )

    return mcp_types.ReadResourceResult(contents=[])
```

**Why lazy loading:**
- File missing → clear error at request time, not import crash
- Hot reload during dev works
- Easier to debug deploy issues
```

---

## Update `cluster_questions.py`

### Add widget metadata:

```python
from ..handlers.resources import WIDGET_URI

# In handle() success response:
meta = {
    "openai/outputTemplate": WIDGET_URI,
    "openai/toolInvocation/invoking": "Clustering your questions...",
    "openai/toolInvocation/invoked": "Here's your Unpack summary.",
    "openai/widgetAccessible": True,
    "openai/resultCanProduceWidget": True,
}

return mcp_types.CallToolResult(
    content=[mcp_types.TextContent(
        type="text",
        text=f"Clustered {total_questions} questions into {len(clusters)} groups."
    )],
    structuredContent={
        "problem_statement": validated.problem_statement,  # ADD THIS
        "clusters": clusters,
        "unclustered": unclustered,
        "summary_markdown": summary_markdown,
        "assistant_guidance": {
            "action": "WIDGET_RENDERED",
            "next_step": "SELECT_CLUSTER",
        },
    },
    _meta=meta,
)
```

**Note:** No prose in `assistant_guidance`. Phrasing goes in tool description:

```python
DESCRIPTION = """
...
AFTER WIDGET RENDERS:
- Give a brief observation about what you notice in the clusters
- Ask: 'Which area would you like to explore further?'
- Do NOT offer advice or solutions
- Wait for user to select a cluster
"""
```
```

### Update tool registration:

```python
register_tool(ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    widget_uri=WIDGET_URI,  # ADD THIS
    handle=handle,
    read_only_hint=True,
    destructive_hint=False,
    open_world_hint=False,
))
```

---

## Update `tool_logic.py`

Fix minimum questions to 5:

```python
if total_questions < 5:
    raise InsufficientQuestionsError(count=total_questions)
```

Update error message:

```python
class InsufficientQuestionsError(ClusterValidationError):
    """Raised when fewer than 5 questions provided."""
    def __init__(self, count: int):
        super().__init__(
            "insufficient_questions",
            f"Need at least 5 questions, got {count}",
            count=count,
            required_minimum=5,
        )
```

---

## Update `formulate_problem.py` Guidance

Already says "Minimum 5 from user" — no change needed.

---

## Build Process

```bash
cd mcp_server/unpack/widget-react
npm install
npm run build
# Output: ../widgets/unpack-clusters.html
```

Update `vite.config.ts`:

```typescript
export default defineConfig({
  plugins: [react(), viteSingleFile()],
  build: {
    outDir: '../widgets',
    emptyOutDir: false,
  },
})
```

Update `package.json` postbuild:

```json
"postbuild": "node -e \"require('fs').renameSync('../widgets/index.html', '../widgets/unpack-clusters.html')\""
```

---

## Acceptance Criteria

- [ ] Widget renders after `cluster_questions` call
- [ ] Problem statement displayed at top
- [ ] Clusters displayed as cards with theme, questions, insight
- [ ] Unclustered questions shown separately (if any)
- [ ] "Copy Summary" button copies markdown to clipboard
- [ ] Widget uses OpenAI Apps SDK UI components
- [ ] Widget follows OpenAI design tokens
- [ ] Accessible (keyboard nav, ARIA labels, VoiceOver)
- [ ] Minimum 5 questions enforced
- [ ] `assistant_guidance` uses intent codes only (no prose)
- [ ] Widget builds to single HTML file
- [ ] Resource handler serves widget with lazy loading
- [ ] **Test verifies cluster output uses `theme` field (not `label`)**
- [ ] **Test verifies `problem_statement` included in structuredContent**

---

## Data Shape Verification

**Critical:** Widget expects `theme`, backend must output `theme`.

### Verify in `tool_logic.py`:

```python
# ✅ Correct — uses "theme"
processed_clusters.append({
    "id": f"cluster_{i + 1}",
    "theme": theme,
    "questions": cluster_questions_list,
    "insight": insight,
})

# ❌ Wrong — uses "label" (widget will break!)
processed_clusters.append({
    "id": f"cluster_{i + 1}",
    "label": theme,
    ...
})
```

### Required unit tests:

```python
def test_cluster_output_uses_theme_field():
    """Verify output uses 'theme' not 'label' (widget depends on this)."""
    result = cluster_questions(
        problem_statement="Test problem",
        clusters=[
            {"theme": "Test theme", "questions": ["Q1", "Q2", "Q3", "Q4", "Q5"]}
        ],
    )
    
    assert "theme" in result["clusters"][0]
    assert "label" not in result["clusters"][0]
    assert result["clusters"][0]["theme"] == "Test theme"


def test_handler_includes_problem_statement_in_response():
    """Verify problem_statement is in structuredContent (widget header depends on this)."""
    # This test goes in handler tests, not tool_logic tests
    # Handler must add problem_statement to structuredContent
    pass
```

### Why defensive mapping in widget:

The `utils.ts` includes fallback handling:

```typescript
theme: c.theme ?? c.label ?? 'Untitled'
```

This ensures widget doesn't crash if backend temporarily uses wrong field name. But the backend should still use `theme` — this is just a safety net.

---

## Files to Create

| File | Source |
|------|--------|
| `widget-react/` | Copy from `clarity/widget-react/` |
| `widget-react/src/types.ts` | Rewrite (simpler) |
| `widget-react/src/utils.ts` | Simplify |
| `widget-react/src/App.tsx` | Adapt |
| `widget-react/src/components/Header.tsx` | Adapt |
| `widget-react/src/components/ClusterCard.tsx` | Adapt |
| `handlers/resources.py` | New (copy pattern from Clarity) |

## Files to Update

| File | Changes |
|------|---------|
| `tools/cluster_questions.py` | Add widget_uri, meta, simplified guidance |
| `tool_logic.py` | Minimum 5 questions |
| `server.py` | Register resource handlers |

---

## Deployment

After build:
1. Verify `widgets/unpack-clusters.html` exists
2. Commit to `fulfilling-productivity` repo
3. Push to GitHub
4. Render auto-deploys
5. Test widget renders in ChatGPT