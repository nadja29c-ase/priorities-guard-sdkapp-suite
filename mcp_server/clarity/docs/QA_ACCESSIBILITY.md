# Accessibility QA Checklist

Run through this checklist before submission.

## Keyboard Navigation

- [ ] Tab through widget — verify focus ring visible on each ClusterCard
- [ ] Count tab stops — should equal number of clusters (NOT subclusters or items)
- [ ] Verify focus never gets "stuck"
- [ ] Shift+Tab moves backwards correctly

## Screen Reader (VoiceOver on Mac / NVDA on Windows)

- [ ] Navigate by headings (Ctrl+Alt+H on NVDA, VO+Cmd+H on Mac)
  - Cluster names announced as h3
  - Subcluster names announced as h4
- [ ] Navigate lists
  - Thought items announced as list items
- [ ] Tags announced with visible text (no duplicate announcements)
- [ ] Priority badges announced

## Modal Focus Management

- [ ] Click Save button → modal opens
- [ ] Focus automatically on Cancel button
- [ ] Tab → focus moves to Save button
- [ ] Tab → focus returns to Cancel button (trapped)
- [ ] Shift+Tab cycles backwards
- [ ] Tab does NOT escape modal to background content
- [ ] Press Escape → modal closes
- [ ] After close → focus returns to Header Save button
- [ ] Click backdrop → modal closes
- [ ] After backdrop close → focus returns to Header Save button

## Theme Compatibility

- [ ] Toggle to dark mode
- [ ] Focus rings visible in dark mode
- [ ] All text readable in dark mode
- [ ] Toggle back to light mode
- [ ] Focus rings visible in light mode
