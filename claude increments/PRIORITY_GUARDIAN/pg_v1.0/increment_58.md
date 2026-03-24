Increment 58-debug — In-Widget Debug Overlay
Purpose: Confirm the set_globals state-overwrite bug hypothesis. This is a temporary diagnostic build — not for submission, to be removed once the bug is confirmed or disproven.
Scope: App.tsx only. No backend changes, no migration, no other files.

What to build
Add a debug overlay that renders inside the widget (visible in the ChatGPT UI on both desktop and iPhone) showing a live log of every openai:set_globals event.
The overlay must capture and display:

Event counter: how many times set_globals has fired since init
For each event (keep last 5): toolOutputChanged: true/false, hostDisplayMode: inline/fullscreen/undefined
Current internal displayMode state value

Activation: Hardcode const PG_DEBUG = true at the top of App.tsx (not via window.__PG_DEBUG__ — that can't be injected cross-origin). This constant controls all debug behavior.

Implementation details
State to add:
tsconst [debugLog, setDebugLog] = useState<Array<{
  n: number
  toolOutputChanged: boolean
  hostDisplayMode: string | undefined
}>>([])
const debugCounterRef = useRef(0)
```

**Where to log:** Inside `handleToolOutputUpdate`, when `PG_DEBUG === true`, before the guard check — capture `toolOutputChanged` and `hostDisplayMode`, push to `debugLog` state (keep last 5 entries).

**Overlay JSX:** Render as a fixed-position element inside the `<main>` return, bottom of the DOM, only when `PG_DEBUG === true`. Style it so it doesn't interfere with the widget layout — small monospace text, semi-transparent dark background, `z-index` high enough to always be visible. Use only inline styles or Tailwind utility classes that are already in use elsewhere in the widget (no new dependencies).

**Content to show in overlay:**
```
[PG DEBUG]
displayMode: inline  (current React state)
─── set_globals log ───
#3  toolOutputChanged:true   hostMode:fullscreen
#2  toolOutputChanged:false  hostMode:fullscreen  
#1  toolOutputChanged:false  hostMode:inline

What we're testing
The hypothesis: after a CRUD action (toggle deliverable), when the user clicks expand to fullscreen, iOS fires set_globals with a new object reference for toolOutput even though the data hasn't changed. This causes toolOutputChanged: true in the log — which would confirm the bug.
Expected result if hypothesis is correct:

Toggle a deliverable → set_globals fires, toolOutputChanged: false (ref still matches, guard passes correctly)
Click expand → set_globals fires, toolOutputChanged: true (new reference, guard fails → state overwrite)

Expected result if hypothesis is wrong:

Expand fires toolOutputChanged: false → the bug has a different root cause


Important constraints

PG_DEBUG = true is hardcoded for this build only — make it trivially easy to flip back to false
The overlay must not affect any existing functionality, layout, or state
Do not remove the existing window.__PG_DEBUG__ console log — keep it, add the overlay on top
Read OPERATIONS_PREDEPLOY.md before committing


After testing
Once the log confirms or disproves the hypothesis, a follow-up increment will either implement hasCrudDataRef fix (if confirmed) or investigate further (if disproven). The overlay and PG_DEBUG constant will be removed in that same follow-up increment.