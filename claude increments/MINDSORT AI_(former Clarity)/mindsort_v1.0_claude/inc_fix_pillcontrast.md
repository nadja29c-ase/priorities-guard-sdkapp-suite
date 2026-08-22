Claude Code Briefing — TagPill visible boundary (MindSort-Claude)
Scope: TagPill only. One-line change. UX fix.
What this is

The action-tag pill (TagPill, e.g. "decide") is a filled pill whose fill (--color-background-tertiary, resolves to 
#FAF9F5 light) is nearly identical to the card behind it (
#FFFFFF cluster / 
#F5F4ED subcluster) — ~1.03:1. In light mode the pill shape disappears, so "decide" reads as floating text indistinguishable from the thought items above it, instead of as a distinct action tag. This is a UI/UX fix — the component fails to communicate that it's a tag.

Diagnosis already complete (confirmed against live resolved values, not the token table): the text passes fine (
#3D3D3A on 
#FAF9F5 = ~10:1) — text color and fill are NOT the problem and must not be changed. The missing thing is a visible boundary.

The change

In TagPill (mcp_server/mindsort_claude/widget-react/src/App.tsx), add a 1px border using currentColor:

border: '1px solid currentColor',

Keep everything else as-is — the existing fill (--color-background-tertiary) and text (--color-text-secondary) do not change.

Why currentColor: the pill's text is already --color-text-secondary (a host token that adapts per theme). currentColor makes the border follow that same resolved foreground color — so the border is a real dark stroke in light mode and a light stroke on the dark card in dark mode, automatically, with no new token decision, no hardcoded value, and no risk of the border drifting from the text color. It is the foreground color by definition, so it is not a repurposed token.

What NOT to do
Do not change the pill's color or background — both are correct; the text passes at ~10:1 and the fill is the intended design.
Do not introduce a --color-border-* token (the neutral border tokens top out at 2.58:1 and don't achieve the goal) or any semantic/status color.
Do not add padding/layout changes to "fix" it — the boundary is the fix.
Do not touch RANK_COLORS.
Any adjacent issue noticed → flag in the report, don't fix here. (One is already known and belongs in a separate increment: --color-border-strong at App.tsx ~1353/2120 is a phantom token falling back to hardcoded 
#141413, invisible in dark mode — M1/M18 defect. Do NOT fix it in this increment; just confirm it's logged.)
Verify before committing (on the real Claude host — the load-bearing check)

This is a visual fix; the acceptance is visual, not a spreadsheet. On the live fullscreen board, in both themes:

Light mode: the border makes "decide" clearly read as a distinct pill, not floating text next to the thought items.
Dark mode: the border stays visible but is not excessively heavy/harsh.

If both hold, ship. If the border looks too heavy in either mode, report back before adjusting — do not silently swap to a different token. No token survey or WCAG computation is needed unless this simple fix visually fails.

Note (do not skip verification because of it): the border inherits currentColor = the resolved --color-text-secondary, which was measured live as 
#3D3D3A in light mode — a crisp dark edge against the card. That's the expectation, but confirm it looks right on-device rather than assuming, given this codebase's history of resolved values differing from the token table.

Deploy mechanics
Widget-bytes change → bump WIDGET_VERSION in handlers/resources_dupl.py, Vite rebuild, cache-bust (disconnect/re-add the connector).
Before deploying, read doc/OPERATIONS_PREDEPLOY.md for any additional pre-deploy steps.
Test instructions
Unit: none — no logic added, a single style property.
Build/regression: existing widget tests and the Vite build stay green. Confirm TagPill remains used only by FullscreenClusterCard and FullscreenSubclusterCard (no other importers).
On-device acceptance: the two visual checks above, both themes.
Report back with
The one-line change as committed.
Confirmation of the two on-device visual checks (light + dark).
A commit hash (review verifies against git show <hash>:<path>).
Anything you did NOT verify, plus adjacent issues flagged-not-fixed (expected: the --color-border-strong phantom-token note).

That's the whole increment. One line, currentColor, keep fill and text, verify both themes visually, ship if it looks right. The --color-border-strong phantom token stays flagged-not-fixed for its own increment — it's the one genuinely separate defect this investigation surfaced, and it's a cleaner, more clearly-biting M1/M18 bug than the pill ever was, so it's worth doing next.