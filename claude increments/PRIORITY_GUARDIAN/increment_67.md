Increment Briefing — iOS: Open Add Priority Form in Fullscreen
Context
The delay-based fix (Inc 66) did not resolve the scroll-off-screen issue on iPhone. The chosen fix is to take the widget fullscreen before opening the add form on mobile. This avoids fighting the iOS ChatGPT host scroll behaviour, which scrolls the conversation to the bottom when the widget's intrinsic height increases — behaviour that cannot be reliably controlled from inline mode.
Desktop behaviour must not change.
Change — App.tsx only
Do not modify handleExpandToFullscreen, handleMinimizeToInline, or notifyHeight.

1. Add two new refs alongside the existing refs (near wasAddingRef)
wasAddingRef is already present from Inc 66. Add only enteredFullscreenForAddRef:
ts// Tracks whether fullscreen was entered specifically for the add form (mobile only).
// Used to reverse the fullscreen on form close without affecting user-initiated fullscreen.
const enteredFullscreenForAddRef = useRef(false)

2. Add handleOpenAddForm in the Display Mode Handlers section
ts// On mobile: go fullscreen before opening the add form to avoid iOS host scroll-off-screen.
// On desktop: open the form inline — no display mode change.
// enteredFullscreenForAddRef is only set when we actually trigger the transition,
// so user-initiated fullscreen is not affected.
const handleOpenAddForm = useCallback(() => {
  if (isMobile && displayMode !== 'fullscreen') {
    enteredFullscreenForAddRef.current = true  // set before calling handler
    handleExpandToFullscreen()
  }
  setIsAddingPriority(true)
}, [isMobile, displayMode, handleExpandToFullscreen])
enteredFullscreenForAddRef must remain false in all other cases. The condition isMobile && displayMode !== 'fullscreen' already ensures this:

Desktop: condition is false → ref not set
Already fullscreen from manual expand: condition is false → ref not set
Do not set this ref anywhere else


3. Update the AddPriorityButton onClick
tsx// Before:
<AddPriorityButton onClick={() => setIsAddingPriority(true)} />

// After:
<AddPriorityButton onClick={handleOpenAddForm} />

4. Replace the two Inc 66 effects with one new effect
Remove both existing Inc 66 effects entirely:
ts// Notify height when add form closes...
useEffect(() => {
  if (!isInitialized) return
  if (!isAddingPriority && wasAddingRef.current) {
    notifyHeight()
  }
  wasAddingRef.current = isAddingPriority
}, [isAddingPriority, isInitialized, notifyHeight])

// Notify height when add form opens — mobile only, delayed (Inc 66)...
useEffect(() => {
  if (!isInitialized) return
  if (!isAddingPriority) return
  if (!isMobile) return
  const id = setTimeout(() => { notifyHeight() }, 300)
  return () => clearTimeout(id)
}, [isAddingPriority, isInitialized, isMobile, notifyHeight])
Replace with this single effect:
ts// On mobile: when add form closes, return to inline — but only if fullscreen was entered
// specifically for the add form. Does not collapse user-initiated fullscreen.
useEffect(() => {
  if (!isInitialized) return
  // Only act on true → false transition
  if (!wasAddingRef.current || isAddingPriority) {
    wasAddingRef.current = isAddingPriority
    return
  }
  wasAddingRef.current = isAddingPriority

  if (isMobile && enteredFullscreenForAddRef.current) {
    enteredFullscreenForAddRef.current = false
    handleMinimizeToInline()
  }
}, [isAddingPriority, isInitialized, isMobile, handleMinimizeToInline])
notifyHeight is called inside handleMinimizeToInline — no separate call needed.

Scope

App.tsx only
One new ref added (enteredFullscreenForAddRef) — wasAddingRef already exists
One new callback (handleOpenAddForm)
One JSX prop updated (AddPriorityButton onClick)
Two effects removed (Inc 66), one added
No other component files, no i18n, no backend, no schema, no types
Do not modify handleExpandToFullscreen, handleMinimizeToInline, notifyHeight


Tests
No automated tests — iOS host behaviour and requestDisplayMode cannot be tested in JSDOM.
Manual tests on iPhone:

Tap "+ Add a new priority" → widget goes fullscreen → form is visible and usable
After fullscreen opens and form appears, verify the name input receives focus and the keyboard opens automatically
Fill form and save → widget returns to inline
Tap "+ Add a new priority" → tap Cancel → widget returns to inline
Manually expand widget → open form → close form → widget stays fullscreen (not forced back to inline)

Manual test on desktop:
5. Tap "+ Add a new priority" → form opens inline, no fullscreen transition, no behaviour change

Pre-deploy
Read doc/OPERATIONS_PREDEPLOY.md. No migration. No backend deploy. Build with npm run build inside widget-react/, verify output lands in ../widgets/pg-dashboard.html. Sonnet 4.6Claude is AI and can make mistakes. Please double-check responses.


Increment 68 — Fix isMobile detection (likely cause of fullscreen not triggering on iPhone)
Context: The add priority form fullscreen fix (Inc 67) relies on isMobile being true on iPhone. Testing shows fullscreen never triggers on device. The likely cause: window.openai.userAgent is a structured object { device: { type: 'mobile' | 'tablet' | 'desktop' }, capabilities: { hover, touch } }, not a string. The regex test coerces it to "[object Object]", never matches, the navigator.userAgent fallback never fires, and isMobile evaluates to false on all devices.
This is not runtime-confirmed — add a console.log on mount to capture the actual value for verification.
File to change: mcp_server/priority_guardian/widget-react/src/App.tsx only.
Change 1 — replace the isMobile const (currently lines 62–64):
ts// Add temporary diagnostic log — remove after confirming on device
const ua = (window.openai as any)?.userAgent
console.log('[PG] window.openai.userAgent:', JSON.stringify(ua))

const isMobile =
  ua?.device?.type === 'mobile' ||
  /iPhone|iPad|iPod|Android/.test(navigator.userAgent)
Do not rename isMobile — it is referenced in multiple places throughout the file. Do not remove the navigator.userAgent fallback — it is required for browser-based testing and environments where window.openai is absent.
After the change: Run npm run build in widget-react/. Read OPERATIONS_PREDEPLOY.md before committing. No other files change. No tests change.

The console.log stays in for this deploy so you can open Safari Web Inspector on Mac connected to your iPhone, load the widget, and see what window.openai.userAgent actually contains. Once confirmed, we remove it in Inc 68b.

Increment 69 — Apply bottom safe area inset in fullscreen on mobile
Context: In fullscreen mode on iOS, the ChatGPT "Ask anything" input bar overlays the bottom of the widget, obscuring the Google Calendar ConnectionStatus component. window.openai.safeArea.insets.bottom is the SDK-provided value for exactly this clearance.
File to change: mcp_server/priority_guardian/widget-react/src/App.tsx only.
Changes:

Add a state variable near the other state declarations:

tsconst [hostBottomInset, setHostBottomInset] = useState<number>(
  () => (window.openai as any)?.safeArea?.insets?.bottom ?? 0
)

Inside the existing openai:set_globals listener — in the handleSetGlobals function where displayMode is already synced — add:

tsconst bottom = (window.openai as any)?.safeArea?.insets?.bottom ?? 0
setHostBottomInset(bottom)

On both <main> elements (pie chart view and dashboard view), add a style prop. The <main> already has padding: 2rem 1.75rem from CSS (32px bottom). The inline style must preserve that base and add the inset on top — do not replace it:

tsxstyle={!isInline ? { paddingBottom: `calc(2rem + ${hostBottomInset}px)` } : undefined}
If hostBottomInset is 0 (desktop, Android), calc(2rem + 0px) equals the existing CSS value — no regression. Do not change main.css. Do not change any other layout or padding. Do not rename any existing variables.
Read OPERATIONS_PREDEPLOY.md before committing. No test changes needed.