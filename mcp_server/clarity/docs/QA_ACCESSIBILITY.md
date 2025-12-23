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

## Modal Accessibility

- [x] Click Save button → modal opens
- [x] Modal has `role="dialog"` and `aria-modal="true"`
- [x] Modal title linked via `aria-labelledby`
- [x] Press Escape → modal closes
- [x] After close → focus returns to Save button
- [x] Modal buttons keyboard accessible

> **Note:** Focus trapping (Tab cycling only within modal) does not work due to ChatGPT iframe sandbox limitations. This is a known platform constraint, not an app bug.

## Theme Compatibility

- [X] Toggle to dark mode in ChatGPT settings
- [X] Focus rings visible in dark mode
- [X] All text readable in dark mode
- [X] Toggle back to light mode
- [X] Focus rings visible in light mode
