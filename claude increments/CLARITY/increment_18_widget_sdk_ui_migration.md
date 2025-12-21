# Increment 18: Clarity Widget SDK UI Migration

## Objective

Migrate the Clarity widget from vanilla HTML/CSS to OpenAI Apps SDK UI (React + Tailwind 4) to meet ChatGPT app submission requirements for "polished UI" using the official design system.

The widget must not introduce any new decision-making logic or suggestions beyond what already exists. This is execution-only UI.

## Context

**Current State:**
- `mcp_server/clarity/widgets/clarity-clusters.html` - 450 lines vanilla HTML/CSS/JS
- Custom CSS variables that approximate ChatGPT colors but don't use official tokens
- Manual theme detection via `window.openai.theme`
- Working functionality: cluster display, subclusters, priority badges, tags, save modal

**Target State:**
- React + Vite build producing a single HTML file
- `@openai/apps-sdk-ui` components and design tokens
- WCAG AA compliant via SDK UI defaults
- Same functionality, compliant styling

## Design Direction

**Visual Concept: Card Grid Board**
- Clean, minimalistic design
- Cluster cards arranged in responsive grid
- Thought items within clusters styled as list items (bullet aesthetic)
- Balance between card layout and todo list readability

**Hard Constraint:** The "post-it board" concept is purely structural. Cards must remain neutral surfaces using SDK tokens. No skeuomorphic styling:
- ❌ No colored card backgrounds (yellow, pastel, etc.)
- ❌ No paper textures or decorative shadows
- ❌ No playful/whimsical styling
- ✅ Neutral `bg-surface` backgrounds only
- ✅ Standard `shadow-sm` or `shadow-md` only
- ✅ SDK border tokens only

## Technical Requirements

### Build Setup

Create a new widget build directory:
```
mcp_server/clarity/widget-react/
├── package.json
├── vite.config.ts
├── index.html
├── src/
│   ├── main.tsx
│   ├── main.css
│   ├── App.tsx
│   └── components/
│       ├── ClusterCard.tsx
│       ├── SubclusterCard.tsx
│       ├── ThoughtItem.tsx
│       ├── PriorityBadge.tsx
│       ├── TagPill.tsx
│       ├── SaveModal.tsx
│       └── Header.tsx
└── dist/
    └── clarity-clusters.html  (build output)
```

**Dependencies:**
- React 18+
- Vite with `vite-plugin-singlefile`
- `@openai/apps-sdk-ui`
- Tailwind CSS 4

**Build Size:** Tree-shaking and component-level imports must be enforced to keep output under 500KB.

### SDK UI Integration

**CSS Setup (main.css):**
```css
@import "tailwindcss";
@import "@openai/apps-sdk-ui/css";
@source "../node_modules/@openai/apps-sdk-ui";
```

**Theme Handling:**

Preferred approach for React - use SDK hook:
```typescript
import { useDocumentTheme } from "@openai/apps-sdk-ui";

function App() {
  const theme = useDocumentTheme(); // Returns "light" | "dark"
  // Hook auto-updates on theme change via MutationObserver
}
```

Alternative (if needed for initial setup before React mounts):
```typescript
import { getDocumentTheme, applyDocumentTheme } from "@openai/apps-sdk-ui";
```

**Important:** Do not manually set the `data-theme` attribute. The SDK hook manages theme reactively. The widget should sync with `window.openai.theme` on initial load only if SDK hooks are unavailable.

### Data Contract (unchanged)

The widget receives this structure via `window.openai.toolOutput.structuredContent.clusters`:

```typescript
interface Cluster {
  cluster_name: string;
  thought_items?: string[];           // Direct items (flat) - may be undefined
  subclusters?: Subcluster[];         // Nested groups - may be undefined
  sum_thought_items: number;          // Total count
  tags?: string[];                    // May be undefined
  priority?: { rank: "P1" | "P2" | "P3" };
}

interface Subcluster {
  subcluster_name: string;
  thought_items?: string[];           // May be undefined
  sum_thought_items: number;
  tags?: string[];                    // May be undefined
  priority?: { rank: "P1" | "P2" | "P3" };
}
```

**Defensive Handling:** All arrays must be treated as optional at render time. Use `array ?? []` or optional chaining.

### Component Mapping

SDK UI primitives or tokenized Tailwind utilities (only where no SDK component exists):

| Current Element | SDK UI Equivalent |
|-----------------|-------------------|
| `.cluster-card` | `<div className="rounded-2xl border border-default bg-surface shadow-md p-4">` |
| `.subcluster-card` | `<div className="rounded-lg border border-subtle bg-surface-secondary p-3">` |
| `.priority-badge` | `<Badge color="secondary" variant="solid" size="sm">P1</Badge>` |
| `.tag-pill` | `<Badge color="secondary" variant="soft" size="sm">` |
| `.item-count` | `<Badge color="secondary" variant="outline" size="sm">` |
| `.save-btn` | `<Button color="primary" variant="solid">Save</Button>` |
| `.modal-btn-cancel` | `<Button color="secondary" variant="outline">` |
| Thought bullet | Use `text-secondary` for bullet, `text-default` for text |

**Priority Badge Colors:**

Use **neutral coloring** for all priority badges - differentiate by label only:
- P1 → `<Badge color="secondary" variant="solid">P1</Badge>`
- P2 → `<Badge color="secondary" variant="solid">P2</Badge>`
- P3 → `<Badge color="secondary" variant="solid">P3</Badge>`

Rationale: Using success/warning/danger colors implies judgment (good/bad). Priority is user-defined importance, not a value judgment by the app.

### window.openai API Usage

Preserve existing functionality:

```typescript
// Get tool output
const clusters = window.openai?.toolOutput?.structuredContent?.clusters ?? [];

// Save board
await window.openai?.callTool("save_board", { confirmed: true, clusters });
```

### Build Output

Vite must produce a single self-contained HTML file:
- All JS/CSS inlined
- No external dependencies at runtime
- Output to: `mcp_server/clarity/widgets/clarity-clusters.html`

**vite.config.ts requirements:**
- Use `vite-plugin-singlefile` 
- Build target: `esnext`
- Output: single HTML file

## Functional Requirements

1. **Display clusters** in responsive grid (current: `grid-template-columns: repeat(auto-fit, minmax(240px, 1fr))`)

2. **Sort by priority** - P1 clusters first, then P2, P3, then unprioritized

3. **Show subclusters** nested within cluster cards

4. **Thought items** as bullet list with truncation at 80 chars (visual only, no data loss)

5. **Tags** as small pills below items

6. **Priority badges** next to cluster/subcluster names (neutral color, label differentiates)

7. **Save button** with confirmation modal

8. **Saved indicator** shows briefly after successful save

9. **Loading state** when no data yet

10. **Theme switching** via `useDocumentTheme` hook

## Compliance Checklist

Per OpenAI Design Guidelines:
- [ ] Uses `@openai/apps-sdk-ui` components where available
- [ ] All colors via semantic tokens (no hardcoded hex)
- [ ] Typography via SDK text/heading utilities
- [ ] Border radius via `--radius-*` tokens
- [ ] Shadows via `--shadow-*` tokens
- [ ] WCAG AA contrast (automatic via SDK tokens)
- [ ] Supports light/dark themes
- [ ] No custom fonts
- [ ] No custom gradients
- [ ] No persistent browser storage (localStorage/sessionStorage)
- [ ] No `<form>` elements

## Files to Modify

1. **Rename:** `mcp_server/clarity/widgets/clarity-clusters.html` → `clarity-clusters-backup.html`
2. **Create:** `mcp_server/clarity/widget-react/` (entire React project directory)
3. **Build output:** `mcp_server/clarity/widgets/clarity-clusters.html` (new file from build)

The widget URI in `handlers/resources.py` remains unchanged - it still points to `clarity-clusters.html`.

## Files NOT to Modify

- `mcp_server/clarity/tools/*.py` (tool definitions unchanged)
- `mcp_server/clarity/tool_logic.py` (data enrichment unchanged)
- `mcp_server/clarity/handlers/resources.py` (widget URI unchanged)
- Any backend code

---

## Unit Test Requirements

Test the React components in isolation using Vitest + React Testing Library:

1. **ClusterCard rendering**
   - Renders cluster name
   - Shows item count badge
   - Displays priority badge when present
   - Renders thought items list (handles undefined gracefully)
   - Renders subclusters when present (handles undefined gracefully)
   - Shows tags when present (handles undefined gracefully)

2. **Priority sorting**
   - Clusters sorted P1 → P2 → P3 → unprioritized
   - Subclusters sorted within parent

3. **Theme handling**
   - `useDocumentTheme` returns correct value
   - Component re-renders on theme change

4. **Save modal**
   - Opens on Save button click
   - Closes on Cancel
   - Calls handler on Confirm

---

## Integration Test Requirements

Test widget behavior in simulated ChatGPT environment:

1. **Data loading**
   - Reads from window.openai.toolOutput
   - Handles missing/empty clusters gracefully
   - Handles undefined arrays within clusters
   - Shows loading state when no data

2. **Save flow**
   - Calls window.openai.callTool with correct arguments
   - Shows saved indicator on success
   - Handles save failure gracefully

3. **Theme integration**
   - useDocumentTheme responds to data-theme changes
   - Correct visual appearance in both themes

**Test setup:** Mock window.openai object, test theme via `data-theme` attribute mutation

---

## Acceptance Criteria

1. Widget renders identically in functionality to current implementation
2. Build produces single HTML file < 500KB
3. Passes all unit and integration tests
4. Visual inspection confirms SDK UI styling (neutral, not skeuomorphic)
5. No console errors in browser
6. Theme switching works correctly
7. Save functionality works via callTool API
8. All arrays handled defensively (no crashes on undefined)

## Reference Files

- Current widget: `mcp_server/clarity/widgets/clarity-clusters.html`
- Tool definition: `mcp_server/clarity/tools/organize_thoughts.py`
- Data enrichment: `mcp_server/clarity/tool_logic.py`
- SDK UI tokens: See project knowledge `openai-sdk-ui-tokens-reference.md`
- OpenAI Design Guidelines: See project knowledge `ChatGPT_Apps_SDK_-_Official_Design_Guidelines.md`