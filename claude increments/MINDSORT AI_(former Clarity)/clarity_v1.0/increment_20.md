Clarity Widget Fixes Required
File: mcp_server/clarity/widget-react/src/App.tsx
1. DELETE manual theme mutation (compliance violation)
tsx// DELETE THIS ENTIRE useEffect - ChatGPT controls data-theme, not the widget
useEffect(() => {
  document.documentElement.setAttribute('data-theme', theme)
}, [theme])
2. Replace inline grid style with Tailwind arbitrary value
tsx// CHANGE FROM:
<div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>

// CHANGE TO:
<div className="grid gap-4 grid-cols-[repeat(auto-fit,minmax(240px,1fr))]">
3. Fix index keys for clusters
tsx// CHANGE FROM:
{sortedClusters.map((cluster, i) => (
  <ClusterCard key={i} cluster={cluster} />
))}

// CHANGE TO:
{sortedClusters.map((cluster) => (
  <ClusterCard key={cluster.cluster_name} cluster={cluster} />
))}

File: mcp_server/clarity/widget-react/src/components/ClusterCard.tsx
4. Fix all index keys
tsx// Thought items - CHANGE FROM:
{items.map((item, i) => (
  <ThoughtItem key={i} text={item} />
))}
// CHANGE TO:
{items.map((item, i) => (
  <ThoughtItem key={`${cluster.cluster_name}-item-${i}-${item.slice(0,20)}`} text={item} />
))}

// Subclusters - CHANGE FROM:
{sortedSubclusters.map((sub, i) => (
  <SubclusterCard key={i} subcluster={sub} />
))}
// CHANGE TO:
{sortedSubclusters.map((sub) => (
  <SubclusterCard key={sub.subcluster_name} subcluster={sub} />
))}

// Tags - CHANGE FROM:
{tags.map((tag, i) => (
  <TagPill key={i} tag={tag} />
))}
// CHANGE TO:
{tags.map((tag) => (
  <TagPill key={tag} tag={tag} />
))}

File: mcp_server/clarity/widget-react/src/components/SubclusterCard.tsx
5. Fix index keys (same pattern)

Thought items: use key={\subcluster.subclustername−item−{subcluster.subcluster_name}-item-
subcluster.subclustern​ame−item−{i}-${item.slice(0,20)}\`}`

Tags: use key={tag}


File: mcp_server/clarity/widget-react/src/components/SaveModal.tsx
6. Add accessible role to modal overlay
tsx// Add role="dialog" aria-modal="true" to the overlay div
<div 
  role="dialog" 
  aria-modal="true"
  className="fixed inset-0 ..."
  onClick={onCancel}
>

Test Fixes
7. ClusterCard.test.tsx - Add minimal cluster test:
tsxit('renders safely with minimal cluster data', () => {
  const cluster: Cluster = {
    cluster_name: 'Minimal',
    sum_thought_items: 0,
  }
  render(<ClusterCard cluster={cluster} />)
  expect(screen.getByText('Minimal')).toBeInTheDocument()
})
8. SaveModal.test.tsx - Fix overlay click test:
tsx// CHANGE FROM:
const overlay = screen.getByText('Save Board?').parentElement?.parentElement
// CHANGE TO:
fireEvent.click(screen.getByRole('dialog'))
9. SaveModal.test.tsx - Add disabled state test:
tsxit('disables save button while saving', () => {
  render(<SaveModal isOpen isSaving onCancel={vi.fn()} onConfirm={vi.fn()} />)
  expect(screen.getByRole('button', { name: /save/i })).toBeDisabled()
})
10. test-utils.ts - Add afterEach cleanup:
tsxafterEach(() => {
  resetMocks()
  document.documentElement.removeAttribute('data-theme')
})
11. test-utils.ts - Separate theme helpers:
tsx// Replace combined helper with:
export function setMockDocumentTheme(theme: 'light' | 'dark') {
  document.documentElement.setAttribute('data-theme', theme)
}

// Only if testing fallback:
export function setMockOpenaiTheme(theme: 'light' | 'dark') {
  mockOpenai.theme = theme
}

After fixes, rebuild:
bashcd mcp_server/clarity/widget-react && npm run build
Acceptance criteria:

No useEffect setting data-theme
No inline style={} attributes
No key={i} with index-only keys
All tests pass
Build produces single HTML < 500KB