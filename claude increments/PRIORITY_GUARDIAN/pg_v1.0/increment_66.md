Increment Briefing — iOS: Delay notifyHeight When Add Form Opens (Final)
Problem
On iPhone, tapping "+ Add a new priority" causes the entire widget to scroll off screen. The form mounts, widget height grows, the iOS host may react to the intrinsic height change during the same layout cycle and scroll the conversation to the new bottom edge — past the widget.
Root cause
In App.tsx there is exactly one useEffect that calls notifyHeight() when isAddingPriority changes:
tsuseEffect(() => {
  if (isInitialized) {
    notifyHeight()
  }
}, [isAddingPriority, isInitialized, notifyHeight])
This fires immediately on both open and close transitions, and on every re-render where isAddingPriority is true. On iOS, notifying the host immediately when the form opens gives the host no time to settle before it scrolls to the new bottom.
Change — App.tsx only
Do not modify notifyHeight itself.
Add one new ref alongside the existing refs (near hasCrudDataRef):
ts// Tracks previous isAddingPriority for transition detection (iOS scroll fix)
const wasAddingRef = useRef(false)
Replace the existing effect:
ts// Notify height when add form state changes
useEffect(() => {
  if (isInitialized) {
    notifyHeight()
  }
}, [isAddingPriority, isInitialized, notifyHeight])
With these two effects:
ts// Notify height when add form closes — immediate is safe (height shrinks, no scroll risk).
// wasAddingRef guards against firing on unrelated re-renders where isAddingPriority === false.
useEffect(() => {
  if (!isInitialized) return
  if (!isAddingPriority && wasAddingRef.current) {
    notifyHeight()
  }
  wasAddingRef.current = isAddingPriority
}, [isAddingPriority, isInitialized, notifyHeight])

// Notify height when add form opens — mobile only, delayed.
// On iOS the host may react to intrinsic height changes during the same layout cycle,
// scrolling the conversation before the user can see the form.
// Delay gives the host time to settle before receiving the height notification.
// Desktop: no delay needed, this behaviour does not occur there.
useEffect(() => {
  if (!isInitialized) return
  if (!isAddingPriority) return
  if (!isMobile) return

  const id = setTimeout(() => {
    notifyHeight()
  }, 300)

  return () => clearTimeout(id)
}, [isAddingPriority, isInitialized, isMobile, notifyHeight])
Scope

App.tsx only — one ref added, one effect replaced by two
No other component files
No i18n, no backend, no schema, no displayMode change, no widget API change
Do not modify notifyHeight

Tests
No automated tests — iOS host timing cannot be reproduced in JSDOM. Manual test on iPhone: tap "+ Add a new priority", confirm the form stays visible and the widget does not scroll off screen. Confirm desktop behaviour is unchanged.
Pre-deploy
Read doc/OPERATIONS_PREDEPLOY.md. No migration. No backend deploy. Build with npm run build inside widget-react/, verify output lands in ../widgets/pg-dashboard.html.