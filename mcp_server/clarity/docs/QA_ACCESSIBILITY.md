# Accessibility QA Checklist

Run through this checklist before submission. Test in **Safari** (VoiceOver's native browser).

## Keyboard Navigation

- [x] Tab through widget — verify focus ring visible on ALL elements:
  - Cluster articles ✓
  - Subcluster headings (h4) ✓
  - Thought items (li) ✓
  - Save button ✓
- [x] Tab order flows logically: Cluster → its items → its subclusters → subcluster items → next Cluster → Save
- [x] Verify focus never gets "stuck"
- [x] Shift+Tab moves backwards correctly

## Screen Reader (VoiceOver in Safari)

Enable: Cmd+F5

- [x] Tab to cluster — VoiceOver announces: "Cluster: [name], Priority X, Y items, article"
- [x] Tab to subcluster — VoiceOver announces: "Subcluster: [name], Priority X, Y items, heading level 4"
- [x] Tab to thought item — VoiceOver announces item text
- [x] Priority badges announced as "Priority 1/2/3" (not "P1")
- [x] Item counts announced as "X items" (not just number)

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
