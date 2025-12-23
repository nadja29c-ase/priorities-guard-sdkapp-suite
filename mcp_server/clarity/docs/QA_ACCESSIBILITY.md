# Accessibility QA Checklist

Run through this checklist before submission. Test in **Safari** (VoiceOver's native browser).

## Keyboard Navigation

- [ ] Tab through widget — verify focus ring visible on ALL elements:
  - Cluster articles
  - Subcluster headings (h4)
  - Thought items (li)
  - Save button
- [ ] Tab order flows logically: Cluster → its items → its subclusters → subcluster items → next Cluster → Save
- [ ] Verify focus never gets "stuck"
- [ ] Shift+Tab moves backwards correctly
- [ ] Focus rings use correct color (var(--color-ring))

## Screen Reader (VoiceOver in Safari)

Enable: Cmd+F5

- [ ] Tab to cluster — VoiceOver announces cluster name
- [ ] Tab to subcluster — VoiceOver announces "Subcluster: [name], heading level 4"
- [ ] Tab to thought item — VoiceOver announces item text
- [ ] Priority badges announced as "Priority 1/2/3" (not "P1")
- [ ] Item counts announced as "X items in this cluster" (not just number)
- [ ] Subcluster item counts announced as "X items in this subcluster"

## Modal Focus Management

- [ ] Click Save button → modal opens
- [ ] Focus trapped inside modal (Tab cycles through modal buttons only)
- [ ] Press Escape → modal closes
- [ ] After close → focus returns to Save button

## Theme Compatibility

- [ ] Toggle to dark mode in ChatGPT settings
- [ ] Focus rings visible in dark mode
- [ ] All text readable in dark mode
- [ ] Toggle back to light mode
- [ ] Focus rings visible in light mode

---

## Code Requirements (for reference)

### Elements with tabIndex={0}
- `ClusterCard.tsx` — `<article>`
- `SubclusterCard.tsx` — `<h4>`
- `ThoughtItem.tsx` — `<li>`

### Screen reader text patterns
- Priority: `<span role="text" aria-label="Priority X">`
- Item counts: `<span role="text" aria-label="X items in this cluster">`
- Subclusters: `aria-label="Subcluster: [name]"`
- Thought items: `aria-label={item.text}`

### Required CSS
```css
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
```
