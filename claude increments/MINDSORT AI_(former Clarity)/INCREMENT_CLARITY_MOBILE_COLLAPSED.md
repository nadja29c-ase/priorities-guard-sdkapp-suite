# Increment: MindSort AI Widget — Mobile Collapsed Mode

## Goal

On mobile, when the widget loads from a saved board (via `load_saved_board`), clusters and subclusters are collapsed by default. The user can expand them individually. On desktop, and after any active operation (`organize_thoughts`, `start_prioritization_flow`, `edit_board`), the widget is always fully expanded.

---

## Approach — Copy and Adjust, Never Rewrite

Copy each file listed below verbatim. Make only the listed adjustments. Do not restructure, rename, or improve anything not explicitly listed.

---

## Part 1 — Backend: `load_saved_board.py`

**File:** `mcp_server/clarity/tools/load_saved_board.py`

**Single change:** In the `handle` function, in the branch where `cluster_count > 0` (the "Snapshot exists with clusters" branch), add `"collapsed_by_default": True` to the `structured` dict.

Current:
```python
structured = {
    "clusters": clusters,
    "has_history": True,
    "is_empty_snapshot": False,
    "assistant_guidance": guidance,
}
```

Change to:
```python
structured = {
    "clusters": clusters,
    "has_history": True,
    "is_empty_snapshot": False,
    "collapsed_by_default": True,
    "assistant_guidance": guidance,
}
```

No other changes to this file.

---

## Part 2 — Widget: `App.tsx`

**File:** `mcp_server/clarity/widget-react/src/App.tsx`

**Four changes:**

**Change 1 — Add mobile detection.** After the existing `lastToolOutputRef` declaration, add:

```tsx
// Mobile detection (same pattern as PG widget)
const isMobile =
  (window.openai as any)?.userAgent?.device?.type === 'mobile' ||
  /iPhone|iPad|iPod|Android/.test(navigator?.userAgent || '')
```

**Change 2 — Add `defaultCollapsed` state.** Add alongside the existing state declarations:

```tsx
const [defaultCollapsed, setDefaultCollapsed] = useState(false)
```

**Change 3 — Read `collapsed_by_default` from toolOutput and set state.** Inside the `loadClusters` callback, after `setClusters(data)`, add:

```tsx
// Derive collapsed_by_default from toolOutput structuredContent
const sc = (t as any)?.result?.structuredContent ?? (t as any)?.structuredContent ?? t
const collapsedByDefault = isMobile && sc?.collapsed_by_default === true
setDefaultCollapsed(collapsedByDefault)
```

**Change 4 — Pass prop to `ClusterCard`.** In the render, where `ClusterCard` is currently rendered:

Current:
```tsx
<ClusterCard key={cluster.cluster_name} cluster={cluster} />
```

Change to:
```tsx
<ClusterCard key={cluster.cluster_name} cluster={cluster} defaultCollapsed={defaultCollapsed} />
```

---

## Part 3 — Widget: `ClusterCard.tsx`

**File:** `mcp_server/clarity/widget-react/src/components/ClusterCard.tsx`

**Five changes:**

**Change 1 — Add `defaultCollapsed` prop.** Update the props interface:

```tsx
interface ClusterCardProps {
  cluster: Cluster
  defaultCollapsed?: boolean
}
```

**Change 2 — Add `isExpanded` state and ref-guarded sync effect.** Inside the component body, after existing variable declarations:

```tsx
const [isExpanded, setIsExpanded] = useState(!defaultCollapsed)

// Only reset isExpanded when defaultCollapsed actually transitions between values.
// A plain useEffect without this guard would reset user-expanded clusters on every
// toolOutput update that doesn't change the collapsed mode.
const prevDefaultCollapsedRef = useRef(defaultCollapsed)
useEffect(() => {
  if (prevDefaultCollapsedRef.current !== defaultCollapsed) {
    setIsExpanded(!defaultCollapsed)
    prevDefaultCollapsedRef.current = defaultCollapsed
  }
}, [defaultCollapsed])
```

Note: `useRef` must be imported alongside `useState` and `useEffect`.

**Change 3 — Add body content ID for correct aria-controls.** After the existing `headingId` declaration, add:

```tsx
const contentId = `${headingId}-content`
```

**Change 4 — Make header a toggle button when in collapsed mode.** Replace the existing header `div` with a conditional. Build a `headerContent` variable first, then render it conditionally:

```tsx
const headerContent = (
  <>
    <div className="flex items-center gap-2">
      <h3 id={headingId} aria-label={`Cluster: ${cluster.cluster_name}`} className="text-sm font-semibold text-default m-0">
        {cluster.cluster_name || 'Untitled cluster'}
      </h3>
      {hasPriority && <PriorityBadge rank={hasPriority} />}
    </div>
    <div className="flex items-center gap-2">
      <span role="text" aria-label={`${cluster.sum_thought_items} items in this cluster`}>
        <Badge color="secondary" variant="outline" size="sm" aria-hidden="true">
          {cluster.sum_thought_items}
        </Badge>
        <span className="sr-only">{cluster.sum_thought_items} items</span>
      </span>
      {defaultCollapsed && (
        <span className="text-xs text-secondary ml-1" aria-hidden="true">{isExpanded ? '▲' : '▼'}</span>
      )}
    </div>
  </>
)
```

Then render the header:
```tsx
{defaultCollapsed ? (
  <button
    onClick={() => setIsExpanded(e => !e)}
    className="flex items-center justify-between gap-2 mb-3 w-full text-left bg-transparent border-none p-0 cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-ring)]"
    aria-expanded={isExpanded}
    aria-controls={contentId}
  >
    {headerContent}
  </button>
) : (
  <div className="flex items-center justify-between gap-2 mb-3">
    {headerContent}
  </div>
)}
```

**Change 5 — Conditionally render body, wrapped in a div with `contentId`, `role="region"`, and `aria-labelledby`.** Replace the existing body (summary, thought items, subclusters, tags) with:

```tsx
<div id={contentId} role="region" aria-labelledby={headingId}>
  {/* Summary — hidden when collapsed */}
  {isExpanded && cluster.summary && (
    <p className="text-sm text-secondary mb-3">
      {truncateText(cluster.summary, 100)}
    </p>
  )}

  {/* Direct thought items:
      - Expanded: all items
      - Collapsed: only items with a priority rank assigned */}
  {sortedItems.length > 0 && (
    <ul role="list" className="space-y-2 list-none m-0 p-0">
      {(isExpanded ? sortedItems : sortedItems.filter(item => item.priority?.rank)).map((item, i) => (
        <ThoughtItem key={`${cluster.cluster_name}-item-${i}-${item.text.slice(0,20)}`} item={item} />
      ))}
    </ul>
  )}

  {/* Subclusters:
      - When parent is collapsed: pass defaultCollapsed=true so subclusters also start collapsed
      - When parent is expanded: pass defaultCollapsed={defaultCollapsed} so subclusters start
        collapsed individually (two-level progressive disclosure on mobile) */}
  {sortedSubclusters.length > 0 && (
    <div className="flex flex-col gap-3 mt-3">
      {sortedSubclusters.map((sub) => (
        <SubclusterCard
          key={sub.subcluster_name}
          subcluster={sub}
          defaultCollapsed={!isExpanded ? true : defaultCollapsed}
        />
      ))}
    </div>
  )}

  {/* Tags — only when expanded */}
  {isExpanded && tags.length > 0 && (
    <div role="list" aria-label="Suggested actions" className="flex flex-wrap gap-2 mt-auto pt-4">
      {tags.map((tag) => (
        <TagPill key={tag} tag={tag} />
      ))}
    </div>
  )}
</div>
```

---

## Part 4 — Widget: `SubclusterCard.tsx`

**File:** `mcp_server/clarity/widget-react/src/components/SubclusterCard.tsx`

Same pattern as `ClusterCard`. Five changes:

**Change 1 — Add `defaultCollapsed` prop:**
```tsx
interface SubclusterCardProps {
  subcluster: Subcluster
  defaultCollapsed?: boolean
}
```

**Change 2 — Add `isExpanded` state and ref-guarded sync effect:**
```tsx
const [isExpanded, setIsExpanded] = useState(!defaultCollapsed)

const prevDefaultCollapsedRef = useRef(defaultCollapsed)
useEffect(() => {
  if (prevDefaultCollapsedRef.current !== defaultCollapsed) {
    setIsExpanded(!defaultCollapsed)
    prevDefaultCollapsedRef.current = defaultCollapsed
  }
}, [defaultCollapsed])
```

Note: `useRef` must be imported alongside `useState` and `useEffect`.

**Change 3 — Add body content ID:**
```tsx
const contentId = `${headingId}-content`
```

**Change 4 — Make header a toggle button when in collapsed mode.** Same pattern as ClusterCard. Build `headerContent`, render conditionally as button or div. `aria-controls` references `contentId`. Button includes focus ring matching the widget's existing focus style.

```tsx
const headerContent = (
  <>
    <div className="flex items-center gap-2">
      <h4 id={headingId} className="text-sm font-medium text-default m-0">
        {subcluster.subcluster_name || 'Untitled'}
      </h4>
      {hasPriority && <PriorityBadge rank={hasPriority} size="sm" />}
    </div>
    <div className="flex items-center gap-2">
      <span role="text" aria-label={`${subcluster.sum_thought_items || rawItems.length} items in this subcluster`}>
        <Badge color="secondary" variant="outline" size="sm" aria-hidden="true">
          {subcluster.sum_thought_items || rawItems.length}
        </Badge>
        <span className="sr-only">{subcluster.sum_thought_items || rawItems.length} items</span>
      </span>
      {defaultCollapsed && (
        <span className="text-xs text-secondary ml-1" aria-hidden="true">{isExpanded ? '▲' : '▼'}</span>
      )}
    </div>
  </>
)
```

```tsx
{defaultCollapsed ? (
  <button
    onClick={() => setIsExpanded(e => !e)}
    className="flex items-center justify-between gap-2 mb-2 w-full text-left bg-transparent border-none p-0 cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-ring)]"
    aria-expanded={isExpanded}
    aria-controls={contentId}
  >
    {headerContent}
  </button>
) : (
  <div className="flex items-center justify-between gap-2 mb-2">
    {headerContent}
  </div>
)}
```

Note: the existing `tabIndex={0}` and `aria-label` on the `<h4>` can be removed since the button now handles interactivity. Do not change anything else on the `<h4>`.

**Change 5 — Conditionally render body, wrapped in `contentId` div with region semantics:**

```tsx
<div id={contentId} role="region" aria-labelledby={headingId}>
  {/* Thought items:
      - Expanded: all items
      - Collapsed: only items with a priority rank assigned */}
  {sortedItems.length > 0 && (
    <ul role="list" className="space-y-1 list-none m-0 p-0">
      {(isExpanded ? sortedItems : sortedItems.filter(item => item.priority?.rank)).map((item, i) => (
        <ThoughtItem key={`${subcluster.subcluster_name}-item-${i}-${item.text.slice(0,20)}`} item={item} size="small" />
      ))}
    </ul>
  )}

  {/* Tags — only when expanded */}
  {isExpanded && tags.length > 0 && (
    <div role="list" aria-label="Suggested actions" className="flex flex-wrap gap-1.5 mt-auto pt-2">
      {tags.map((tag) => (
        <TagPill key={tag} tag={tag} size="sm" />
      ))}
    </div>
  )}
</div>
```

---

## Summary of all changes

| File | What changes |
|---|---|
| `load_saved_board.py` | Add `"collapsed_by_default": True` to structuredContent (cluster_count > 0 branch only) |
| `App.tsx` | Mobile detection, `defaultCollapsed` state, read flag from toolOutput, pass to `ClusterCard` |
| `ClusterCard.tsx` | `defaultCollapsed` prop, `isExpanded` + ref-guarded `useEffect`, `contentId`, toggle button with focus ring and `aria-controls={contentId}`, body div with `role="region" aria-labelledby={headingId}` |
| `SubclusterCard.tsx` | Same pattern as `ClusterCard` |

---

## Rejected feedback (do not apply)

**"Simplify subcluster logic to `defaultCollapsed || !isExpanded`"** — Mathematically wrong. Truth table: when `defaultCollapsed=false` and `isExpanded=false`, original returns `false`, suggested version returns `true`. Original `!isExpanded ? true : defaultCollapsed` is correct and stays.

**"`key={cluster.id || cluster.cluster_name}`"** — `Cluster` and `Subcluster` types have no `id` field. The fallback would always be `cluster_name` anyway. When a cluster is renamed via `edit_board`, `defaultCollapsed` is `false` so all clusters expand on re-render — the remount from key change is harmless. No change needed.

**"`item.priority?.rank != null`"** — rank is typed as `'P1' | 'P2' | 'P3'`, never a falsy non-null value. Existing check is safe.

**"`typeof window !== 'undefined'` guard"** — Not needed in this browser-only iframe runtime. PG widget uses same pattern without it.

---

## What does NOT change

- `organize_thoughts.py` — no change. No `collapsed_by_default` flag → widget renders fully expanded.
- `start_prioritization_flow.py` — no change. Same reasoning.
- `edit_board.py` — no change. User just made an edit and expects to see the result immediately.
- `read_saved_board.py` — no change. LLM-internal tool, never produces widget output.
- `types.ts`, `utils.ts` — no changes needed.
- Desktop behaviour — unchanged. `isMobile` is `false` on desktop so `defaultCollapsed` is always `false`.

---

## Before deploying

Read `OPERATIONS_PREDEPLOYMENT.md` and check for any pre-deploy tasks required.
