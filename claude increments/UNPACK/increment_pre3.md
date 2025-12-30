# Unpack — Increment 3 Pre-Implementation Checklist

## Purpose

This checklist sequences the work so each step is independently testable. Follow in order. Don't skip verification points.

---

## Phase 1: Backend Updates (No Widget Yet)

### Step 1.1: Update `tool_logic.py`

**Changes:**
- [ ] Verify `theme` field is used (not `label`)
- [ ] Change minimum questions from 3 → 5
- [ ] Update `InsufficientQuestionsError` message

**Verify:**
```bash
cd mcp_server/unpack
python -m pytest tests/test_cluster_questions.py -v
```
- [ ] All tests pass
- [ ] Output clusters have `theme` field
- [ ] Error raised when < 5 questions

---

### Step 1.2: Update `tools/cluster_questions.py`

**Changes:**
- [ ] Add `problem_statement` to `structuredContent` output
- [ ] Simplify `assistant_guidance` to intent codes only:
  ```python
  "assistant_guidance": {
      "action": "WIDGET_RENDERED",
      "next_step": "SELECT_CLUSTER",
  }
  ```
- [ ] Update `DESCRIPTION` to include post-widget behavior
- [ ] Add `_meta` dict with widget flags
- [ ] Update `widget_uri` in `register_tool()`

**Important:** Temporarily define `WIDGET_URI` locally in this file:
```python
# TODO: Import from handlers.resources after Step 3.1
WIDGET_URI = "ui://widget/unpack-clusters.html"
```
Do NOT import from handlers yet — file doesn't exist.

**Verify:**
```bash
python -m pytest tests/test_cluster_questions.py -v
```
- [ ] Tests pass (no import errors)
- [ ] Response includes `problem_statement`
- [ ] `assistant_guidance` has no prose

---

### Step 1.3: Add unit tests for data shape

**Create/Update:** `tests/test_cluster_questions.py`

**Add tests:**
```python
def test_cluster_output_uses_theme_field():
    """Widget depends on 'theme' not 'label'."""
    ...

def test_response_includes_problem_statement():
    """Widget header depends on this."""
    ...

def test_minimum_five_questions_enforced():
    """Changed from 3 to 5."""
    ...
```

**Verify:**
```bash
python -m pytest tests/test_cluster_questions.py -v
```
- [ ] All new tests pass

---

## Phase 2: Widget Creation

### Step 2.1: Copy Clarity widget scaffold

**Actions:**
- [ ] Copy `clarity/widget-react/` → `unpack/widget-react/`
- [ ] Delete Clarity-specific files:
  - `src/components/PriorityBadge.tsx`
  - `src/components/SubclusterCard.tsx`
  - `src/components/TagPill.tsx`
  - `src/components/ThoughtItem.tsx`
  - `src/test/` (will recreate)
- [ ] Rename in `package.json`: `"name": "unpack-widget"`

**Verify:**
```bash
cd mcp_server/unpack/widget-react
npm install
```
- [ ] No errors

---

### Step 2.2: Rewrite `types.ts`

**Replace entire file with:**
```typescript
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

// window.openai types...
```

**Verify:**
- [ ] TypeScript compiles: `npx tsc --noEmit`

---

### Step 2.3: Simplify `utils.ts`

**Replace with:**
- `getToolOutput()` with defensive theme/label mapping
- `truncateText()`
- `copyToClipboard()`

**Remove:**
- All priority/sorting functions
- `normalizeThoughtItem`
- `extractStructuredContent` (not needed for Unpack)

**Verify:**
- [ ] TypeScript compiles: `npx tsc --noEmit`

---

### Step 2.4: Update `components/Header.tsx`

**Replace with:**
```typescript
interface HeaderProps {
  problemStatement: string
}

export function Header({ problemStatement }: HeaderProps) {
  // Show "Your Unpack Summary" + problem statement
}
```

**Verify:**
- [ ] TypeScript compiles

---

### Step 2.5: Simplify `components/ClusterCard.tsx`

**Replace with:**
- Props: `{ cluster: QuestionCluster }`
- Display: theme, questions list, insight
- Remove: priority badge, tags, subclusters

**Verify:**
- [ ] TypeScript compiles

---

### Step 2.6: Update `App.tsx`

**Replace with:**
- Load data via `getToolOutput()`
- Render `Header` with problem statement
- Render `ClusterCard` for each cluster
- Render unclustered section
- Add "Copy Summary" button

**Remove:**
- Save button
- `isSaving` state
- `handleSave` function

**Verify:**
- [ ] TypeScript compiles: `npx tsc --noEmit`

---

### Step 2.7: Update build config

**`vite.config.ts`:**
```typescript
build: {
  outDir: '../widgets',
  emptyOutDir: false,
}
```

**`package.json`:**
```json
"postbuild": "node -e \"require('fs').renameSync('../widgets/index.html', '../widgets/unpack-clusters.html')\""
```

**Verify:**
```bash
npm run build
ls ../widgets/
```
- [ ] `unpack-clusters.html` exists
- [ ] File is single HTML, reasonable size (<500KB)

---

## Phase 3: Resource Handler

### Step 3.1: Create `handlers/resources.py`

**Create with:**
- `WIDGET_URI = "ui://widget/unpack-clusters.html"`
- `WIDGET_PATH` constant
- `get_widget_html()` with lazy loading
- `list_resources()`
- `handle_read_resource()`

**Verify:**
- [ ] File exists
- [ ] Imports work: `python -c "from mcp_server.unpack.handlers.resources import WIDGET_URI; print(WIDGET_URI)"`

---

### Step 3.2: Update `handlers/__init__.py`

**Current state:** File exists but is empty (just docstring)

**Update to:**
```python
"""Unpack MCP request handlers."""

from .resources import (
    WIDGET_URI,
    list_resources,
    list_resource_templates,
    handle_read_resource,
)
```

**Verify:**
- [ ] Import works: `python -c "from mcp_server.unpack.handlers import WIDGET_URI; print(WIDGET_URI)"`

---

### Step 3.3: Update `server.py`

**Current state:** No resource handlers registered

**Add imports:**
```python
from mcp_server.unpack.handlers import (
    list_resources,
    list_resource_templates,
    handle_read_resource,
)
```

**Add resource handler registration (after tool handlers):**
```python
# Resource handlers (widget discovery and serving)
@mcp._mcp_server.list_resources()
async def _list_resources():
    return await list_resources()


@mcp._mcp_server.list_resource_templates()
async def _list_resource_templates():
    return await list_resource_templates()


mcp._mcp_server.request_handlers[mcp_types.ReadResourceRequest] = handle_read_resource
```

**Verify:**
```bash
cd mcp_server/unpack
python -c "from server import app; print('OK')"
```
- [ ] No import errors

---

### Step 3.4: Create `widgets/` directory

**Actions:**
```bash
mkdir -p mcp_server/unpack/widgets
```
- [ ] Directory exists: `mcp_server/unpack/widgets/`
- [ ] After widget build (Step 2.7): `unpack-clusters.html` is in this directory

---

## Phase 4: Integration Testing

### Step 4.1: Local server test

**Start server:**
```bash
cd mcp_server/unpack
uvicorn server:app --port 8003
```

**Verify:**
- [ ] Server starts without errors
- [ ] `http://localhost:8003/mcp` responds

---

### Step 4.2: MCP Inspector test

**Connect to:** `http://localhost:8003/mcp`

**Test `formulate_problem`:**
- [ ] Call with complete input
- [ ] Returns `confidence: high`
- [ ] Guidance mentions question brainstorming

**Test `cluster_questions`:**
- [ ] Call with 5+ questions and clusters
- [ ] Response includes `problem_statement`
- [ ] Response includes `clusters` with `theme` field
- [ ] Response includes `summary_markdown`
- [ ] Response includes `_meta` with widget flags
- [ ] `_meta["openai/outputTemplate"]` == `"ui://widget/unpack-clusters.html"`
- [ ] `_meta["openai/resultCanProduceWidget"]` == `True`
- [ ] `assistant_guidance` has `action: "WIDGET_RENDERED"`

---

### Step 4.3: Widget resource test

**In MCP Inspector or curl:**
```bash
# List resources
curl http://localhost:8003/mcp/resources

# Read widget
curl http://localhost:8003/mcp/resources/ui://widget/unpack-clusters.html
```

**Verify:**
- [ ] Widget HTML returned
- [ ] HTML is valid (contains `<html>`, `<script>`, etc.)

---

### Step 4.4: ChatGPT integration test

**Deploy to Render, then:**

1. Start conversation with Unpack
2. Describe a problem → `formulate_problem` called
3. Confirm problem statement
4. Brainstorm 5+ questions
5. Say "done" → `cluster_questions` called
6. **Widget should render**

**Verify:**
- [ ] Widget appears in chat
- [ ] Problem statement shown at top
- [ ] Clusters displayed as cards
- [ ] "Copy Summary" button works
- [ ] Unclustered section shows (if applicable)

---

## Phase 5: Cleanup

### Step 5.1: Remove dead code

- [ ] Delete any unused Clarity imports
- [ ] Delete commented-out code
- [ ] Delete unused test files

### Step 5.2: Final test run

```bash
cd mcp_server/unpack
python -m pytest tests/ -v
```
- [ ] All tests pass

### Step 5.3: Commit

```bash
git add .
git commit -m "Increment 3: Add clusters widget with copy summary"
git push
```

---

## Common Pitfalls

| Pitfall | Prevention |
|---------|------------|
| Widget import fails before resource handler exists | Use placeholder URI string in Step 1.2, import from handlers after Step 3.1 |
| TypeScript errors from Clarity types | Delete all Clarity-specific files (PriorityBadge, SubclusterCard, etc.) before adapting |
| Widget doesn't render in ChatGPT | Check `_meta` flags in handler response AND tool registration |
| Empty header in widget | Verify `problem_statement` is in `structuredContent` |
| "theme" vs "label" mismatch | Run data shape unit tests before widget work |
| Build outputs to wrong location | Check `vite.config.ts` outDir and `postbuild` script |
| Lazy loading fails | Ensure `widgets/` directory exists AND widget is built before server start |
| Resource handlers not called | Verify `server.py` registers `list_resources`, `list_resource_templates`, AND `handle_read_resource` |
| Tests fail on minimum questions | Tests may still expect 3, need to update to 5 |

---

## Order Summary

```
1. Backend logic (tool_logic.py)
2. Handler updates (cluster_questions.py)
3. Unit tests for data shape
4. Copy widget scaffold
5. Rewrite types.ts
6. Simplify utils.ts
7. Update components
8. Update App.tsx
9. Build widget
10. Create resource handler
11. Update server.py
12. Local test
13. MCP Inspector test
14. ChatGPT integration test
15. Cleanup & commit
```

Each phase is independently testable. If something breaks, you know which step caused it.