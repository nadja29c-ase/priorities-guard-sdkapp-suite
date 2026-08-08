import { useState, useEffect, useCallback, useRef } from 'react'
import { useApp, useHostStyles, App as McpApp, McpUiToolResultNotification } from '@modelcontextprotocol/ext-apps/react'

import type { Priority, DashboardData, CalendarKeyword, TimeAllocation, PieChartData } from './types'
import { isPieChartData } from './types'
import { sortPrioritiesByKeyword, extractClaudeStructuredContent } from './utils'
import { setLocale, t } from './i18n'
import { ConnectionStatus } from './components/ConnectionStatus'
import { DeadlineCard } from './components/DeadlineCard'
import { FlexibleCard } from './components/FlexibleCard'
import { AddPriorityForm, AddPriorityButton } from './components/AddPriorityForm'
import { TimeAllocationBar } from './components/TimeAllocationBar'
import { PieChart } from './components/PieChart'
import { ExpandButton } from './components/ExpandButton'
import { FullscreenHeader } from './components/FullscreenHeader'
import { CalendarConnectionMinimal } from './components/CalendarConnectionMinimal'

type DisplayMode = 'inline' | 'fullscreen'

/**
 * How long to wait for the MCP Apps bridge to connect before treating the widget as
 * unreachable. Preserved from the pre-Claude-B implementation, where it was an unnamed
 * literal inside the timer. Claude-B changed the predicate, not the budget — moving both
 * at once would make any on-host regression impossible to attribute.
 */
const BRIDGE_SLOW_MS = 3000

/**
 * How long before the widget is willing to assert that the session is stale and tell the
 * user to start a new conversation. Deliberately much longer than BRIDGE_SLOW_MS: that
 * advice is directive and unrecoverable-sounding, so it should not be given on the
 * evidence of a handshake that is merely slow.
 */
const BRIDGE_STALE_MS = 15000

/**
 * C2 — THE ONE CONTRACT for interpreting a tool result.
 *
 * `ontoolresult` (initial load, host-delivered) and `refreshData` (retry / manual
 * refresh, widget-initiated) previously interpreted results differently: refreshData
 * ignored `isError` entirely and accepted any truthy `content.data`. So a failed retry
 * left the original error on screen with no sign it had failed, and a malformed payload
 * was stored as if valid.
 *
 * Both paths now call this. It is deliberately ONE function rather than two aligned
 * implementations — §4's requirement — because two implementations of one contract
 * diverge, which is exactly how these two came apart in the first place.
 *
 * Payload validity is checked HERE, at ingestion, so structurally invalid data can never
 * enter component state. C3 additionally guards the consumer, because ingestion validity
 * is a property of these two call sites and the consumer guard is a property of the
 * claim itself.
 */
type ToolOutcome =
  /** A valid MCP/tool error. `message` is the server's own user-facing string, possibly empty. */
  | { kind: 'error'; message: string }
  /** A success carrying a structurally valid payload. */
  | { kind: 'data'; data: DashboardData | PieChartData }
  /** A success carrying nothing usable: no structuredContent, no `data`, or a malformed shape. */
  | { kind: 'unusable' }

function classifyToolResult(result: unknown): ToolOutcome {
  const r = (result ?? {}) as Record<string, unknown>

  // A valid MCP/tool error. Safe to surface verbatim: handlers/tools_dupl.py returns
  // str(e) for an intentional ToolUsageError and the fixed "Something went wrong. Please
  // try again." for an unexpected exception — exception text and payload internals never
  // reach content[0].text. The server enforces that, so we are not assuming it.
  if (r.isError) {
    const content = Array.isArray(r.content) ? r.content : []
    const first = content[0] as Record<string, unknown> | undefined
    const text = typeof first?.text === 'string' ? first.text.trim() : ''
    return { kind: 'error', message: text }
  }

  const structured = r.structuredContent as Record<string, unknown> | undefined
  const data = structured?.data
  if (!data || typeof data !== 'object') return { kind: 'unusable' }

  // Chart-shaped: `slices` must be an ARRAY. isPieChartData only tests key presence, and
  // PieChart calls slices.filter() during render — outside any try/catch.
  if (isPieChartData(data as DashboardData | PieChartData)) {
    return Array.isArray((data as PieChartData).slices)
      ? { kind: 'data', data: data as PieChartData }
      : { kind: 'unusable' }
  }

  // Dashboard-shaped: `priorities` must be an ARRAY. Without this, a truthy-but-wrong
  // object becomes `priorities = []` downstream and renders "No priorities yet" — a false
  // claim about the user's data. Five separate routes to that output have been found.
  return Array.isArray((data as DashboardData).priorities)
    ? { kind: 'data', data: data as DashboardData }
    : { kind: 'unusable' }
}

/**
 * Priority Guardian Dashboard - Claude Widget (CRUD-enabled)
 *
 * Uses MCP Apps SDK for tool calls and display mode management.
 * Supports inline (display-only) and fullscreen (full CRUD) modes.
 */
function App() {
  const [data, setData] = useState<DashboardData | PieChartData | null>(null)
  const [isInitialized, setIsInitialized] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)

  // TimeAllocation is stored separately so CRUD operations don't clear it
  const [timeAllocation, setTimeAllocation] = useState<TimeAllocation | undefined>(undefined)

  // Edit state: only one priority can be edited at a time
  const [editingPriorityId, setEditingPriorityId] = useState<string | null>(null)

  // Add priority form state
  const [isAddingPriority, setIsAddingPriority] = useState(false)

  // OAuth flow state
  const [awaitingOAuth, setAwaitingOAuth] = useState(false)

  // Display mode state
  const [displayMode, setDisplayMode] = useState<DisplayMode>('inline')

  // Connection failure (Claude-B / B2). THREE distinguishable states:
  //
  // Previously this was a single boolean set by a timer that tested whether the app
  // OBJECT existed. The object is assigned in onAppCreated, which runs BEFORE connect()
  // is attempted — so a connection that hung or failed left the object present, the
  // timer concluded the bridge was fine, and the widget rendered its loading skeleton
  // forever. `isBridgeStale` is now derived from a real connection outcome.
  //
  //   'slow'  — not connected within BRIDGE_SLOW_MS. Says only that, and says it
  //             non-directively, because at this point nothing is actually known to be
  //             wrong: connect() is a postMessage handshake with the parent frame, and a
  //             throttled background tab is enough to exceed a few seconds.
  //   'stale' — still not connected after BRIDGE_STALE_MS. Now the directive
  //             "start a new conversation" advice is earned.
  //   'error' — the SDK reported an explicit connection/initialisation failure.
  const [connectionFailure, setConnectionFailure] = useState<'slow' | 'stale' | 'error' | null>(null)
  const isBridgeStale = connectionFailure !== null

  // Safe area insets for mobile fullscreen (notch/home indicator, native header).
  // All four are tracked: .left/.right matter in landscape, where the notch intrudes
  // horizontally. Before Claude-B none of these were ever set — see the lifecycle effect.
  const [safeAreaTop, setSafeAreaTop] = useState(0)
  const [safeAreaBottom, setSafeAreaBottom] = useState(0)
  const [safeAreaLeft, setSafeAreaLeft] = useState(0)
  const [safeAreaRight, setSafeAreaRight] = useState(0)

  // Platform detection for mobile-specific padding
  const [platform, setPlatform] = useState<string | undefined>(undefined)


  // C1: what the HOST currently offers — distinct from what PG declares it can render.
  // PG's appCapabilities.availableDisplayModes is a declaration sent at initialization;
  // this is Claude's answer. Declaring is not permission, so the request path checks this
  // before asking. undefined means "not yet known", which is treated as not offering.
  const [availableDisplayModes, setAvailableDisplayModes] = useState<string[] | undefined>(undefined)

  // App reference for CRUD operations
  const appRef = useRef<McpApp | null>(null)

  // Timestamp of last CRUD operation — suppress stale ontoolresult for 1500ms after
  const lastCrudAtRef = useRef(0)

  // C1: in-flight guard for requestDisplayMode. A ref, not state — it must not cause a
  // render, and it is read and written within one tick.
  const displayModeRequestPendingRef = useRef(false)

  // Has PG negotiated a display mode with the host yet? Guards the ONE-SHOT initial
  // context read from overwriting a mode we have already agreed. `requestDisplayMode`
  // does NOT update the SDK's cached _hostContext — only a hostcontextchanged
  // notification does — so a late-running initial read can otherwise carry the stale
  // `inline` it was constructed with and undo a granted fullscreen. Notifications are
  // unaffected: the host stays authoritative for genuine changes.
  const displayModeNegotiatedRef = useRef(false)

  const isInline = displayMode !== 'fullscreen'

  // DERIVED, not tracked. Every fullscreen is now host-granted — C1 removed the local
  // path — so "the host is controlling fullscreen" and "we are in fullscreen" are the
  // same fact. They were two state variables, definitionally equal and always written
  // together, which is precisely the drift condition C spent this increment eliminating
  // on the display-mode handlers. Making it structural means it cannot come apart.
  const hostFullscreen = displayMode === 'fullscreen'

  // True host-granted fullscreen on a phone. Hoisted here because BOTH the chart branch
  // and the dashboard branch need it for M10's width reconciliation, and the chart branch
  // returns first. It gates safe-area insets too — see the padding block below.
  const isMobileHostFullscreen = platform === 'mobile' && hostFullscreen

  // HOISTED in Claude-C: the chart branch returns BEFORE the dashboard branch and needs
  // the same safe-area padding. Computing this only in the dashboard section meant the
  // chart rendered with a fixed 16px inset in host fullscreen — content under the notch
  // whenever safeAreaTop > 16. Found by the fifth review.
  // On desktop: fixed 16px padding
  // Safe-area padding (Claude-B / §5.2). Existing padding is a FLOOR, never reduced:
  // an inset smaller than the base padding must not shrink the layout, so each side takes
  // the larger of the two.
  //
  // Before B, this gate was dead TWICE OVER and either cause alone was sufficient:
  // `platform` was permanently undefined (its only writers ran before connect), AND
  // `hostFullscreen` could never become true — nothing in the file ever set it true.
  // (It is derived from displayMode as of Claude-C and can no longer be set at all.)
  // So no inset was ever applied, and fixing only one of the two would have changed
  // nothing observable — which is precisely how the second cause stayed hidden.
  // DENSITY CONTRACT (Claude-C): fullscreen preserves inline's base visual density.
  // These are two DIFFERENT numbers that were previously one, and conflating them is what
  // made desktop fullscreen looser than inline for no reason.
  //
  //   DENSITY_PADDING — what the dashboard uses when no safe area is involved. It matches
  //     the inline <main>'s 12px exactly, because fullscreen adds viewport and expanded
  //     information; it must not visually loosen the layout.
  //   SAFE_AREA_FLOOR — the minimum inset on mobile host fullscreen. Stays 16px: this is
  //     the one padding difference that is functionally justified (M3), and normalising it
  //     to 12 would turn a density fix into an M3 regression.
  const DENSITY_PADDING = 12
  const SAFE_AREA_FLOOR = 16
  const BASE_PADDING_BOTTOM = 32
  const paddingTop = isMobileHostFullscreen
    ? Math.max(safeAreaTop, SAFE_AREA_FLOOR)
    : DENSITY_PADDING
  // NOTE: bottom uses a DIFFERENT formula from the other three — inset + base, floored at
  // 32, rather than max(inset, 16). This is deliberate: it preserves the pre-B behaviour
  // (`safeAreaBottom + 16 : 32`) because the composer sits below the widget and needs
  // clearance beyond the home indicator itself. Stated explicitly so the four sides are
  // not mistaken for one uniform rule.
  const paddingBottom = isMobileHostFullscreen
    ? Math.max(safeAreaBottom + SAFE_AREA_FLOOR, BASE_PADDING_BOTTOM)
    : DENSITY_PADDING
  // .left/.right were read nowhere before B. They matter in landscape, where the notch
  // intrudes horizontally and would otherwise clip controls.
  const paddingLeft = isMobileHostFullscreen
    ? Math.max(safeAreaLeft, SAFE_AREA_FLOOR)
    : DENSITY_PADDING
  const paddingRight = isMobileHostFullscreen
    ? Math.max(safeAreaRight, SAFE_AREA_FLOOR)
    : DENSITY_PADDING

  // ONE CONTRACT FOR DISPLAY MODE.
  //
  // Three call sites used to set this state independently and they disagreed twice:
  // expand derived from the returned mode while minimize cleared `hostFullscreen`
  // optimistically BEFORE asking, and minimize did not handle a refusal at all. Both were
  // invisible until C1, because `hostFullscreen` could never be true, so minimize's
  // pre-clear was a no-op on a flag that was already false.
  //
  // Aligning three implementations again would just reset the clock — the same reasoning
  // as C2, applied to display mode instead of tool results. So there is one function,
  // and `mode` is always the AUTHORITATIVE value: the host's returned mode from a
  // request, or the host's reported mode from a notification. Never an assumption about
  // what we asked for.
  //
  // `hostFullscreen` is derived, not tracked separately: fullscreen that the host either
  // granted or reported IS host-controlled fullscreen. The body class and safe-area
  // insets derive from it in turn, so a refusal in either direction is handled by
  // construction rather than by remembering to handle it.
  const applyDisplayMode = useCallback((mode: string) => {
    setDisplayMode(mode === 'fullscreen' ? 'fullscreen' : 'inline')
    // hostFullscreen is derived from displayMode — see its declaration. Nothing else to
    // set, which is the point: one write, no second variable to forget.
  }, [])

  // C2 — the single application of the single contract.
  //
  // classifyToolResult decides WHAT a result is; this decides what the widget DOES about
  // it. Both are shared, because §4 asks for one contract and aligning two
  // implementations is not the same as having one. Every setter reachable from a tool
  // result lives here, so initial load and retry cannot drift apart.
  //
  // `markInitialized` IS THE ONE DELIBERATE DIVERGENCE between the two paths, and it is a
  // parameter with NO DEFAULT so every call site has to state its intent.
  //
  // `isInitialized` is a LIFECYCLE fact — "the widget has received its first payload" —
  // not a result-handling one. A refresh happens after that by definition, so setting it
  // from a refresh is either a no-op or a lie. It is a no-op today only because refresh
  // currently runs post-initialisation by CONVENTION, not by enforcement.
  //
  // That precondition is exactly the kind this increment keeps finding violated: it was
  // also true that `platform` would be set before it was read, and that expand did not
  // need to tell the host. If a future path ever calls refreshData before initialisation
  // — a prefetch, an earlier retry, a background poll — an unconditional set would mark
  // the widget initialised with no data, hand the loading branch off to an empty
  // dashboard, and reopen the "No priorities yet" class from a new direction.
  //
  // Do not "tidy" this into a single unconditional call.
  //
  // Safe with [] deps: it closes over nothing but React setters and `t`, all stable.
  const applyToolOutcome = useCallback((outcome: ToolOutcome, markInitialized: boolean) => {
    if (outcome.kind === 'error') {
      // The server's own string, falling back only when it sent none.
      setLoadError(outcome.message || t('noData'))
    } else if (outcome.kind === 'unusable') {
      setLoadError(t('noData'))
    } else {
      const resultData = outcome.data
      if ('locale' in resultData && resultData.locale) {
        setLocale(resultData.locale as string)
      }
      setData(resultData)
      if (!isPieChartData(resultData) && resultData.timeAllocation !== undefined) {
        setTimeAllocation(resultData.timeAllocation)
      }
      setLoadError(null)
    }
    if (markInitialized) {
      setIsInitialized(true)
    }
  }, [])

  // M10 — release #root's 600px cap in mobile host fullscreen.
  //
  // #root lives outside this component, in index.html, styled by main.css. No child can
  // exceed its max-width, so the cap cannot be reconciled from inside the component tree
  // — a class on <body> is the narrowest lever that reaches it.
  //
  // This cap was inert until C1: host fullscreen never happened, so the widget was always
  // inside a chat panel narrower than 600px and nothing ever reached it. C1 promotes the
  // iframe for the first time, which makes the cap bind for the first time.
  useEffect(() => {
    const CLASS = 'pg-host-fullscreen'
    // Keyed on hostFullscreen, NOT isMobileHostFullscreen. Scoping the override to mobile
    // was an error: #root's 600px cap sits ABOVE the fullscreen <main>, so a desktop
    // fullscreen asking for a width above 600px could never reach it — the source
    // asserted a width the outer cap forbade. The OVERRIDE applies to any host fullscreen;
    // the WIDTH is what differs by platform (100% on mobile, 480px on desktop — a
    // line-length choice, NOT a match to inline; see the rationale at the fullscreen
    // <main>).
    if (hostFullscreen) {
      document.body.classList.add(CLASS)
    } else {
      document.body.classList.remove(CLASS)
    }
    // Removed on unmount too: the class outlives the component otherwise, and the widget
    // is remounted per tool result.
    return () => document.body.classList.remove(CLASS)
  }, [hostFullscreen])

  // C5: the 500px diagnostic is REMOVED. It logged on every inline render, asserting a
  // limit that does not exist — a stale-fetch artifact already corrected in the
  // compliance documents. On v6 it reported "704px (limit: 500px, EXCEEDS LIMIT)", where
  // 704px is simply the real inline height and nothing was exceeded. It shipped through
  // M20, A, B and v6. Its ABSENCE from C's console record is the expected signal.

  // MCP Apps bridge: useApp hook to receive tool results.
  // isConnected and error were available all along and never destructured — which is why
  // a failed connection had no observable consequence (B2).
  const { app, isConnected, error: connectionError } = useApp({
    appInfo: { name: 'Priority Guardian', version: '1.0.0' },
    capabilities: {
      availableDisplayModes: ['inline', 'fullscreen'],
    },
    onAppCreated: useCallback((appInstance: McpApp) => {
      appRef.current = appInstance

      // WHAT THIS BLOCK NOW DOES: it registers handlers, and nothing else.
      //
      // It previously also read host context here — `getHostContext()` for displayMode,
      // safeAreaInsets and platform. That was dead code. The SDK calls onAppCreated
      // BEFORE `await connect()`, and `_hostContext` is only assigned inside connect():
      // "Returns undefined if called before connection is established." Every read here
      // returned undefined, so platform, displayMode and the insets were never set.
      // The read now lives in the host-context lifecycle effect below, which runs only
      // once `app` is set — i.e. after connect() has resolved.
      //
      // Handler registration MUST stay here. `toolresult` is a one-shot event: the SDK
      // warns (and throws under strict) if it is first registered after connect(), because
      // the host may already have sent the notification. `hostcontextchanged` is NOT
      // one-shot, which is why the lifecycle effect may subscribe to it later.

      // Register handler for incoming tool results
      appInstance.ontoolresult = (result: McpUiToolResultNotification['params']) => {
        // Guard against stale get_priorities echoes after CRUD.
        // Note: McpUiToolResultNotification carries no tool name (CallToolResult only),
        // so we cannot filter by tool name — timestamp window is the correct approach.
        //
        // ⚠️ REPORTED, NOT CHANGED (Claude-B / B3). This guard sits ABOVE the try block,
        // so within 1500ms of a CRUD operation EVERY tool result is dropped — including,
        // now, an isError result that CASE 1 below would otherwise surface. That was
        // harmless before B3, because errors were not handled at all. It does not affect
        // B3's requirement, which concerns the FIRST result, and a first result cannot
        // fall inside a CRUD window. But it is a new interaction created by B3 and is
        // recorded rather than left to be discovered: an error arriving within 1.5s of a
        // CRUD call is still swallowed silently.
        if (Date.now() - lastCrudAtRef.current < 1500) return

        try {
          // B3 + C2: every exit terminates, and the decision is made by the SHARED
          // contract rather than by logic local to this handler. Previously this handler
          // and refreshData interpreted results differently — that divergence is what C2
          // exists to remove.
          // true: this path DELIVERS the first payload, so it owns initialisation.
          applyToolOutcome(classifyToolResult(result), true)
        } catch (err) {
          // Thrown while interpreting an otherwise-successful result — same class as
          // cases 2/3 from the user's point of view. The exception itself goes to the
          // console only; it never reaches the UI.
          console.error('PG Claude widget: Error processing tool result:', err)
          setLoadError(t('noData'))
          setIsInitialized(true)
        }
      }

      // NOTE: the host-context subscription is NOT registered here. It lives in the
      // lifecycle effect below, using the additive addEventListener API rather than the
      // single-slot `on*` setter. On ext-apps 1.2.2 the setter was how PG's handler got
      // destroyed — useHostStyles assigned the same slot twice after this ran.
    }, []),
  })

  // Inject host theme CSS variables (must pass hostContext for dark mode)
  useHostStyles(app, app?.getHostContext())

  // ---------------------------------------------------------------------------
  // Host context lifecycle (Claude-B / B1)
  //
  // Keyed on `app`, which useApp only sets AFTER `await connect()` resolves — so by the
  // time this runs the ui/initialize handshake is complete and getHostContext() has real
  // data. This is the whole fix: the previous read ran in onAppCreated, before connect,
  // and always saw undefined.
  //
  // ORDER MATTERS: subscribe first, then read. A notification arriving between the two
  // would otherwise be missed by our state (the SDK still merges it into _hostContext,
  // so reading after subscribing captures it either way). Re-applying is idempotent.
  //
  // Updates are PARTIAL. Every field is guarded individually so an update carrying only
  // `theme` cannot blank out `platform`, and a safeAreaInsets object carrying only `top`
  // cannot zero `.bottom`. That is the merge requirement — never replace.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!app) return

    // Derived from the SDK's own signature rather than an imported name —
    // McpUiHostContext is not re-exported from the /react entry point, and deriving it
    // means the type cannot drift from the method it describes.
    type HostContextUpdate = Partial<NonNullable<ReturnType<McpApp['getHostContext']>>>

    const applyHostContext = (ctx: HostContextUpdate, isInitialRead: boolean) => {
      if (ctx.displayMode !== undefined) {
        // Routed through the SAME applier the two handlers use, so displayMode,
        // hostFullscreen and everything derived from them cannot drift apart. A host
        // report is authoritative for the same reason a returned mode is.
        //
        // EXCEPT for the one-shot initial read when PG has already negotiated a mode.
        // `requestDisplayMode` does not update the SDK's cached _hostContext — only a
        // hostcontextchanged notification does — so a late-running initial read still
        // carries the `inline` it was constructed with, and would undo a fullscreen the
        // host had just granted. Notifications are never skipped: the host remains
        // authoritative for genuine changes, only for a stale snapshot it is not.
        if (!(isInitialRead && displayModeNegotiatedRef.current)) {
          applyDisplayMode(ctx.displayMode)
        }
      }
      if (ctx.platform !== undefined) {
        setPlatform(ctx.platform)
      }
      // C1: the host's currently-offered modes. Guarded per-field like everything else,
      // so an update omitting it cannot erase what we know.
      if (ctx.availableDisplayModes !== undefined) {
        setAvailableDisplayModes(ctx.availableDisplayModes)
      }
      // Per-inset guards: a partial safeAreaInsets must not reset the omitted sides.
      const insets = ctx.safeAreaInsets
      if (insets?.top !== undefined) setSafeAreaTop(insets.top)
      if (insets?.bottom !== undefined) setSafeAreaBottom(insets.bottom)
      if (insets?.left !== undefined) setSafeAreaLeft(insets.left)
      if (insets?.right !== undefined) setSafeAreaRight(insets.right)
    }

    // 1. Subscribe (additive — does not displace the SDK's own style listeners)
    // false: a notification is a live report, never a stale snapshot.
    const onHostContextChanged = (ctx: HostContextUpdate) => applyHostContext(ctx, false)
    app.addEventListener('hostcontextchanged', onHostContextChanged)

    // 2. Read the initial context, now that it exists
    const initial = app.getHostContext()
    if (initial) {
      // true: this is the one-shot snapshot, which may predate a negotiated mode.
      applyHostContext(initial, true)
    }

    // 3. Remove on cleanup
    return () => {
      app.removeEventListener('hostcontextchanged', onHostContextChanged)
    }
  }, [app, applyDisplayMode])

  // Store app reference
  useEffect(() => {
    if (app) {
      appRef.current = app
    }
  }, [app, applyDisplayMode])

  // Connection outcome (Claude-B / B2).
  //
  // Duration PRESERVED at the pre-B 3000ms — this increment changes the predicate, not
  // the budget, and changing both at once would make an on-host regression ambiguous.
  //
  // The predicate no longer asks "does the app object exist" (it always does, from
  // onAppCreated, before connect is even attempted). It asks whether the connection
  // actually succeeded, failed, or neither within the budget.
  //
  // Timer cleared on all three exits: success and explicit-error return early, and React
  // runs this effect's cleanup before re-running it, so the pending timer is cleared in
  // both cases; unmount runs the same cleanup.
  useEffect(() => {
    if (isConnected) {
      setConnectionFailure(null)
      return
    }
    if (connectionError) {
      setConnectionFailure('error')
      return
    }
    // TWO thresholds, because the old single one made a confident claim on thin evidence.
    // At 3s all that is known is "not connected yet" — the previous wording told the user
    // their session had expired and to start a new conversation, which is directive,
    // actionable and wrong for a handshake that is merely slow. The directive message now
    // requires BRIDGE_STALE_MS of evidence.
    const slowTimer = setTimeout(() => setConnectionFailure('slow'), BRIDGE_SLOW_MS)
    const staleTimer = setTimeout(() => setConnectionFailure('stale'), BRIDGE_STALE_MS)
    return () => {
      clearTimeout(slowTimer)
      clearTimeout(staleTimer)
    }
  }, [isConnected, connectionError])

  // Sync locale on data changes
  useEffect(() => {
    if (data && 'locale' in data && data.locale) {
      setLocale(data.locale as string)
    }
  }, [data])

  // Update data from CRUD response
  const updateDataFromResponse = useCallback((content: { data?: DashboardData } | null | undefined) => {
    if (content?.data) {
      setData(prevData => {
        // Preserve weeklyHourActual from existing state (CRUD responses have null)
        if (prevData && !isPieChartData(prevData)) {
          const existingById = Object.fromEntries(
            prevData.priorities.map(p => [p.id, p])
          )
          return {
            ...content.data!,
            priorities: content.data!.priorities.map(p => ({
              ...p,
              weeklyHourActual: p.weeklyHourActual ?? existingById[p.id]?.weeklyHourActual ?? null,
            })),
          } as DashboardData
        }
        return content.data!
      })
      // Update timeAllocation if present in response (backfill from CRUD)
      if (content.data.timeAllocation !== undefined) {
        setTimeAllocation(content.data.timeAllocation)
      }
      setLoadError(null)
    }
  }, [])

  // Silent backfill of timeAllocation after CRUD (fire-and-forget)
  const backfillTimeAllocation = useCallback(async () => {
    if (!appRef.current?.callServerTool) return
    try {
      const result = await appRef.current.callServerTool({ name: 'get_priorities', arguments: {} })
      const content = extractClaudeStructuredContent<{ data?: DashboardData }>(result)
      if (content?.data?.timeAllocation !== undefined) {
        setTimeAllocation(content.data.timeAllocation)
      }
    } catch {
      // Silent — don't surface backfill errors to user
    }
  }, [])

  // Refresh data by calling get_priorities
  const refreshData = useCallback(async () => {
    if (!appRef.current?.callServerTool) return

    setIsRefreshing(true)
    try {
      const result = await appRef.current.callServerTool({ name: 'get_priorities', arguments: {} })
      // C2: the SAME contract the initial-load path uses. This previously ignored
      // result.isError entirely and accepted any truthy content.data — so a failed retry
      // left the original error on screen with no sign it had failed, and a malformed
      // payload was stored as valid and rendered "No priorities yet".
      // false: a refresh is post-initialisation by definition — see applyToolOutcome.
      applyToolOutcome(classifyToolResult(result), false)
    } catch (err) {
      console.error('Failed to refresh data:', err)
      // Localized as a scope amendment: this writes the SAME state variable that B3 just
      // made localized, rendered by the SAME banner. Leaving it hardcoded would give a
      // German user a German dashboard with an English refresh error in it — the
      // half-fixed state §6 exists to prevent.
      setLoadError(t('failedToRefresh'))
    } finally {
      setIsRefreshing(false)
    }
  }, [])

  // ============ Priority CRUD Operations ============

  const handleAddPriority = useCallback(async (priorityData: {
    name: string
    type: 'deadline' | 'flexible'
    deadline?: string
    weekly_hour_target?: number
    checkpoint_date?: string
    initial_goal_text?: string
  }) => {
    if (isBridgeStale || !appRef.current?.callServerTool) throw new Error('Tool calls not available')

    const result = await appRef.current.callServerTool({ name: 'add_priority', arguments: priorityData })
    const content = extractClaudeStructuredContent<{ data?: DashboardData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    lastCrudAtRef.current = Date.now()
    updateDataFromResponse(content)
    backfillTimeAllocation()
    setIsAddingPriority(false)
  }, [isBridgeStale, updateDataFromResponse, backfillTimeAllocation])

  const handleUpdatePriority = useCallback(async (priorityId: string, updates: {
    name?: string
    deadline?: string
    weekly_hour_target?: number
    checkpoint_date?: string
  }) => {
    if (isBridgeStale || !appRef.current?.callServerTool) throw new Error('Tool calls not available')

    const result = await appRef.current.callServerTool({
      name: 'update_priority',
      arguments: {
        priority_id: priorityId,
        ...updates,
      },
    })
    const content = extractClaudeStructuredContent<{ data?: DashboardData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    lastCrudAtRef.current = Date.now()
    updateDataFromResponse(content)
    backfillTimeAllocation()
    setEditingPriorityId(null)
  }, [isBridgeStale, updateDataFromResponse, backfillTimeAllocation])

  const handleDeletePriority = useCallback(async (priorityId: string) => {
    if (isBridgeStale || !appRef.current?.callServerTool) throw new Error('Tool calls not available')

    const result = await appRef.current.callServerTool({
      name: 'delete_priority',
      arguments: {
        priority_id: priorityId,
        confirm: true,
      },
    })
    const content = extractClaudeStructuredContent<{ data?: DashboardData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    lastCrudAtRef.current = Date.now()
    updateDataFromResponse(content)
    backfillTimeAllocation()
    setEditingPriorityId((current) => current === priorityId ? null : current)
  }, [isBridgeStale, updateDataFromResponse, backfillTimeAllocation])

  // ============ Deliverable CRUD Operations ============

  const handleAddDeliverable = useCallback(async (priorityId: string, name: string) => {
    if (isBridgeStale || !appRef.current?.callServerTool) throw new Error('Tool calls not available')

    const result = await appRef.current.callServerTool({
      name: 'add_deliverable',
      arguments: {
        priority_id: priorityId,
        name,
      },
    })
    const content = extractClaudeStructuredContent<{ data?: DashboardData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    lastCrudAtRef.current = Date.now()
    updateDataFromResponse(content)
  }, [isBridgeStale, updateDataFromResponse])

  const handleToggleDeliverable = useCallback(async (deliverableId: string, done: boolean) => {
    if (isBridgeStale || !appRef.current?.callServerTool) throw new Error('Tool calls not available')

    const result = await appRef.current.callServerTool({
      name: 'update_deliverable',
      arguments: {
        deliverable_id: deliverableId,
        done,
      },
    })
    const content = extractClaudeStructuredContent<{ data?: DashboardData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    lastCrudAtRef.current = Date.now()
    updateDataFromResponse(content)
  }, [isBridgeStale, updateDataFromResponse])

  const handleRenameDeliverable = useCallback(async (deliverableId: string, name: string) => {
    if (isBridgeStale || !appRef.current?.callServerTool) throw new Error('Tool calls not available')

    const result = await appRef.current.callServerTool({
      name: 'update_deliverable',
      arguments: {
        deliverable_id: deliverableId,
        name,
      },
    })
    const content = extractClaudeStructuredContent<{ data?: DashboardData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    lastCrudAtRef.current = Date.now()
    updateDataFromResponse(content)
  }, [isBridgeStale, updateDataFromResponse])

  const handleDeleteDeliverable = useCallback(async (deliverableId: string) => {
    if (isBridgeStale || !appRef.current?.callServerTool) throw new Error('Tool calls not available')

    const result = await appRef.current.callServerTool({
      name: 'delete_deliverable',
      arguments: {
        deliverable_id: deliverableId,
        confirm: true,
      },
    })
    const content = extractClaudeStructuredContent<{ data?: DashboardData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    lastCrudAtRef.current = Date.now()
    updateDataFromResponse(content)
  }, [isBridgeStale, updateDataFromResponse])

  // ============ Goal CRUD Operations ============

  const handleAddGoal = useCallback(async (priorityId: string, text: string) => {
    if (isBridgeStale || !appRef.current?.callServerTool) throw new Error('Tool calls not available')

    const result = await appRef.current.callServerTool({
      name: 'add_goal',
      arguments: {
        priority_id: priorityId,
        text,
      },
    })
    const content = extractClaudeStructuredContent<{ data?: DashboardData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    lastCrudAtRef.current = Date.now()
    updateDataFromResponse(content)
  }, [isBridgeStale, updateDataFromResponse])

  const handleToggleGoal = useCallback(async (goalId: string, achieved: boolean) => {
    if (isBridgeStale || !appRef.current?.callServerTool) throw new Error('Tool calls not available')

    const result = await appRef.current.callServerTool({
      name: 'update_goal',
      arguments: {
        goal_id: goalId,
        achieved,
      },
    })
    const content = extractClaudeStructuredContent<{ data?: DashboardData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    lastCrudAtRef.current = Date.now()
    updateDataFromResponse(content)
  }, [isBridgeStale, updateDataFromResponse])

  const handleRenameGoal = useCallback(async (goalId: string, text: string) => {
    if (isBridgeStale || !appRef.current?.callServerTool) throw new Error('Tool calls not available')

    const result = await appRef.current.callServerTool({
      name: 'update_goal',
      arguments: {
        goal_id: goalId,
        text,
      },
    })
    const content = extractClaudeStructuredContent<{ data?: DashboardData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    lastCrudAtRef.current = Date.now()
    updateDataFromResponse(content)
  }, [isBridgeStale, updateDataFromResponse])

  const handleDeleteGoal = useCallback(async (goalId: string) => {
    if (isBridgeStale || !appRef.current?.callServerTool) throw new Error('Tool calls not available')

    const result = await appRef.current.callServerTool({
      name: 'delete_goal',
      arguments: {
        goal_id: goalId,
        confirm: true,
      },
    })
    const content = extractClaudeStructuredContent<{ data?: DashboardData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    lastCrudAtRef.current = Date.now()
    updateDataFromResponse(content)
  }, [isBridgeStale, updateDataFromResponse])

  // ============ Keyword Reassignment ============

  const handleKeywordChange = useCallback(async (priorityId: string, keyword: CalendarKeyword) => {
    if (isBridgeStale || !appRef.current?.callServerTool) throw new Error('Tool calls not available')

    const result = await appRef.current.callServerTool({
      name: 'update_priority',
      arguments: {
        priority_id: priorityId,
        calendar_keyword: keyword,
      },
    })
    const content = extractClaudeStructuredContent<{ data?: DashboardData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    lastCrudAtRef.current = Date.now()
    updateDataFromResponse(content)
  }, [isBridgeStale, updateDataFromResponse])

  // ============ Display Mode Handlers ============

  // C1 — HOST-NEGOTIATED fullscreen.
  //
  // This previously did `setDisplayMode('fullscreen')` and nothing else. The host was
  // never asked, so the iframe was never promoted: PG rendered its fullscreen layout
  // INSIDE the inline-sized frame, content began under the status bar and Claude's
  // header, and because the host never *reported* fullscreen, `hostFullscreen` stayed
  // false and every safe-area inset stayed unapplied. One root cause, four symptoms —
  // and B1's insets were correct code that nothing could reach.
  //
  // The defect was the scroll ORIGIN, not the height. A fullscreen dashboard scrolling
  // for several screens is normal and compliant.
  const handleExpandToFullscreen = useCallback(async () => {
    if (isBridgeStale) return

    // Step 2 — check what the host CURRENTLY OFFERS, not what PG declared it can render.
    //
    // PERMISSIVE WHEN ABSENT. `availableDisplayModes` is OPTIONAL in the SDK's
    // host-context type while `hostContext` itself is required, so a missing field means
    // "the host didn't say", NOT "not offered". Treating silence as denial reads a fact
    // into a gap — and against a spec-legal host that simply omits the field it would
    // make fullscreen permanently unreachable, replacing "expand always works locally,
    // wrongly" with "expand never works at all".
    //
    // The real guard was never this pre-check: it is step 4 below, where the RETURN VALUE
    // decides. That protects us whatever the host advertised. This check is only an
    // optimisation to skip a request we know would be refused.
    //
    // It also closes the pre-population window for free: `availableDisplayModes` is
    // undefined until the host-context effect runs, and undefined is now permissive, so
    // an early tap sends a request and the response resolves it. No dead button, no
    // dependence on effect timing.
    if (availableDisplayModes && !availableDisplayModes.includes('fullscreen')) {
      return
    }

    const app = appRef.current
    if (!app?.requestDisplayMode) return

    // Double-tap guard. Without it two rapid taps send two requests; a ref rather than
    // state because this must not trigger a render, and the flag is read and written in
    // the same tick.
    if (displayModeRequestPendingRef.current) return
    displayModeRequestPendingRef.current = true

    try {
      const result = await app.requestDisplayMode({ mode: 'fullscreen' })

      // Step 4 — THE RETURN VALUE DECIDES, not the fact that the call resolved.
      // A successful request may legitimately return `inline`; treating the request as
      // success reproduces the exact state being fixed, by a different route.
      if (result.mode !== 'fullscreen' && result.mode !== 'inline') {
        // PG does not declare `pip` in appCapabilities, so the host returned a mode the
        // app never claimed to support. Falling back is correct; falling back silently is
        // not — if this ever fires, it is worth knowing.
        console.warn(
          `[PG] Host returned display mode "${result.mode}", which PG does not declare. Falling back to inline.`
        )
      }
      // The returned mode is authoritative, including when it refuses what we asked for.
      displayModeNegotiatedRef.current = true
      applyDisplayMode(result.mode)
    } catch (err) {
      // Denied or failed: remain inline with a usable layout — never fullscreen UI inside
      // an inline iframe.
      console.error('PG: requestDisplayMode failed', err)
      displayModeNegotiatedRef.current = true
      applyDisplayMode('inline')
    } finally {
      displayModeRequestPendingRef.current = false
    }
  }, [isBridgeStale, availableDisplayModes, applyDisplayMode])

  // Same contract as expand. It previously cleared `hostFullscreen` BEFORE requesting and
  // then set only `displayMode` from the result — so a host that refused the minimize and
  // returned `fullscreen` left PG rendering the fullscreen branch with hostFullscreen
  // false: internal header shown, safe-area padding dropped, #root's 600px cap
  // re-imposed. Host fullscreen wearing non-host-fullscreen layout.
  const handleMinimizeToInline = useCallback(async () => {
    if (appRef.current?.requestDisplayMode) {
      if (displayModeRequestPendingRef.current) return
      displayModeRequestPendingRef.current = true
      try {
        const result = await appRef.current.requestDisplayMode({ mode: 'inline' })
        displayModeNegotiatedRef.current = true
        applyDisplayMode(result.mode)
      } catch {
        // Inline is the safe resting state, and unlike expand there is no worse outcome
        // than being inline when the host wanted fullscreen.
        displayModeNegotiatedRef.current = true
        applyDisplayMode('inline')
      } finally {
        displayModeRequestPendingRef.current = false
      }
    } else {
      displayModeNegotiatedRef.current = true
      applyDisplayMode('inline')
    }
  }, [applyDisplayMode])

  // Connection failure OUTRANKS loading (Claude-B / B2).
  //
  // This branch must be evaluated BEFORE `!isInitialized`. `setIsInitialized(true)` is
  // only ever called from the ontoolresult handler, so a connection that never completes
  // means no result, means isInitialized stays false forever. With the loading branch
  // first, this terminal state was UNREACHABLE in exactly the case it exists for: B2
  // would have fixed the predicate and the state, and the user would still have watched
  // a skeleton spin indefinitely.
  //
  // Ordering, not messaging, is what makes B2 observable. A failed connection is not a
  // slow one — it is the reason loading will never finish, so it is the more specific
  // answer and belongs first.
  if (isBridgeStale) {
    return (
      <div style={{
        padding: '24px',
        textAlign: 'center',
        color: 'var(--color-text-secondary, #3D3D3A)',
        fontSize: '12px',
        lineHeight: '1.5',
        background: 'var(--color-background-secondary, #F5F4ED)',
        borderRadius: '12px',
      }}>
        {/* §5.3: three different facts, three different statements. 'slow' asserts only
            what is known — not connected yet — and gives no advice, because none is
            warranted. The directive session-expired wording is reserved for 'stale',
            which requires five times the evidence. */}
        <p style={{ marginBottom: '8px', fontWeight: 600 }}>
          {connectionFailure === 'error'
            ? t('widgetConnectionFailed')
            : connectionFailure === 'slow'
              ? t('connecting')
              : t('widgetSessionExpired')}
        </p>
        {connectionFailure !== 'slow' && (
          <p style={{ margin: 0 }}>
            {connectionFailure === 'error' ? t('widgetConnectionFailedHint') : t('widgetSessionExpiredHint')}
          </p>
        )}
      </div>
    )
  }

  // Loading state — skeleton mirroring the inline branch layout (M20).
  // TimeAllocationBar is omitted: it is gated on dashboardData?.google_connected,
  // and dashboardData is derived below from `data`, which is null until the same
  // handler that calls setIsInitialized(true).
  // No `platform` dependency — the skeleton stays platform-agnostic (Claude-B §6),
  // and platform is only populated after connect resolves.
  if (!isInitialized) {
    const skeletonBar = (width: string, height: string, radius = '4px') => ({
      width,
      height,
      borderRadius: radius,
      background: 'var(--color-border-tertiary, rgba(31,30,29,0.15))',
    })
    return (
      <main
        role="main"
        aria-label="Priority Guardian Dashboard"
        aria-busy="true"
        style={{
          width: '100%',
          // Matches the FULLSCREEN cap, not inline's declaration. Inline's 560 never binds
          // — the host panel is narrower (~378px observed) — so matching it was matching
          // an inert value. Aligning with fullscreen's 480 removes an 80px snap when the
          // widget loads while the host is ALREADY in fullscreen, which C1 made possible.
          // That snap is the exact seam M20 exists to eliminate.
          //
          // Still platform-agnostic, per M20: a literal swap, not a new conditional. On a
          // mobile viewport the cap never binds and auto margins compute to 0, so the
          // ternary the inline branch uses does no work the cascade wouldn't.
          maxWidth: '480px',
          marginLeft: 'auto',
          marginRight: 'auto',
          background: 'var(--color-background-secondary, #F5F4ED)',
          borderRadius: '16px',
          padding: '12px',
          touchAction: 'pan-y',
          overscrollBehavior: 'contain',
        }}
      >
        <span className="sr-only">{t('loading')}</span>

        {/* Priority card placeholders — the COMMON SUBSET of the two inline card variants.
            DeadlineCard (:189) uses overflow:hidden with a background-secondary banner strip and a
            separately padded body. FlexibleCard (:208) has no banner: padding sits directly on the
            article, followed by the badge+name header. Mirroring DeadlineCard would show a banner
            that VANISHES for flexible priorities, collapsing content upward — the seam M20 exists
            to remove. The mix is unknown at load, so this renders only what both share: padded
            shell, badge circle + name row, one content bar. A deadline card then GAINS a banner on
            load and pushes content down, which is the forgiving direction. */}
        <div aria-hidden="true" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {[0, 1].map((i) => (
            <div
              key={i}
              style={{
                borderRadius: '12px',
                padding: '12px',
                background: 'var(--color-background-primary, #fff)',
                border: '1px solid var(--color-border-primary, rgba(31,30,29,0.4))',
                borderLeft: '3px solid var(--color-border-tertiary, rgba(31,30,29,0.15))',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <div className="pg-skeleton-bar" style={skeletonBar('24px', '24px', '50%')} />
                <div className="pg-skeleton-bar" style={skeletonBar('60%', '12px')} />
              </div>
              <div className="pg-skeleton-bar" style={skeletonBar('42%', '12px')} />
            </div>
          ))}
        </div>

        {/* CalendarConnectionMinimal placeholder */}
        <div
          aria-hidden="true"
          style={{ marginTop: '8px', display: 'flex', alignItems: 'center', gap: '8px', paddingLeft: '4px', paddingRight: '4px' }}
        >
          <div className="pg-skeleton-bar" style={skeletonBar('6px', '6px', '9999px')} />
          <div className="pg-skeleton-bar" style={skeletonBar('120px', '11px')} />
        </div>

        {/* ExpandButton placeholder */}
        <div
          aria-hidden="true"
          style={{ width: '100%', marginTop: '8px', padding: '10px 0', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
        >
          <div className="pg-skeleton-bar" style={skeletonBar('140px', '12px')} />
        </div>
      </main>
    )
  }

  // ============ Pie Chart View ============
  //
  // B4: this branch returns BEFORE both `{loadError && …}` sites (the inline and
  // fullscreen dashboards), so an error occurring while a chart was displayed set
  // loadError correctly and then rendered nothing — the user kept looking at a chart with
  // no indication anything had failed. The fix is NOT to reorder: §5.5 requires the chart
  // to be RETAINED and the error shown alongside it. So the banner is rendered here.
  // ============ Error with no data — TERMINAL ============
  //
  // Found by adversarial review; a regression THIS increment introduced. B3 correctly
  // made failed results set loadError and isInitialized, but left `data` null — so the
  // render fell through to the dashboard branch, where `dashboardData?.priorities ?? []`
  // yields an empty list and EmptyState renders. An auth failure therefore displayed
  // "Authentication required" directly above "No priorities yet. Ask the assistant to
  // help you set up your top priorities."
  //
  // That does not merely fail to inform — it makes a FALSE claim about the user's data
  // and invites them to recreate priorities that still exist. Before B3 this path showed
  // a skeleton: uninformative but honest. Informative and wrong is worse.
  //
  // Handled as its own terminal branch rather than by suppressing EmptyState inside the
  // dashboard branch. Conditional suppression would leave the whole dashboard shell
  // rendering around an error and push the same reachability question one level down.
  // The retry control is NOT optional decoration. Without it this branch is a dead end:
  // a transient first-load failure (a lapsed token, a rate limit) leaves the widget with
  // no control of any kind, and loadError is only cleared by a successful result that
  // this branch renders no way to request. Found by the second adversarial review — the
  // fix for a false claim had introduced a state with no way forward.
  //
  // refreshData is reachable here: it is guarded only by appRef.current?.callServerTool,
  // NOT by isBridgeStale, so the bridge is live even though the first result failed.
  if (loadError && !data) {
    return (
      <div style={{
        padding: '24px',
        textAlign: 'center',
        color: 'var(--color-text-secondary, #3D3D3A)',
        fontSize: '13px',
        lineHeight: '1.5',
        background: 'var(--color-background-secondary, #F5F4ED)',
        borderRadius: '12px',
      }}>
        <p style={{ margin: '0 0 12px' }}>{loadError}</p>
        <button
          type="button"
          onClick={refreshData}
          disabled={isRefreshing}
          style={{
            padding: '8px 16px',
            fontSize: '13px',
            fontWeight: 600,
            cursor: isRefreshing ? 'default' : 'pointer',
            color: 'var(--color-text-primary, #141413)',
            background: 'var(--color-background-primary, #fff)',
            border: '1px solid var(--color-border-primary, rgba(31,30,29,0.4))',
            borderRadius: '8px',
            opacity: isRefreshing ? 0.6 : 1,
          }}
        >
          {isRefreshing ? t('loading') : t('retry')}
        </button>
      </div>
    )
  }

  // B5: the `&& data.slices.length > 0` that used to be here WAS the defect. An empty
  // chart result is still chart data — isPieChartData tests `'slices' in data`, key
  // presence, independent of length — but the extra clause sent it past this branch into
  // the dashboard branch below, where it was cast to DashboardData, yielded no
  // priorities, and rendered "no priorities yet". The user asked for a weekly report and
  // was told they had no priorities.
  //
  // PieChart already owns the correct state: it filters zero-hour slices and renders
  // t('noTimeData') when none remain (PieChart.tsx:61-79). That state has been
  // unreachable since v1 — not missing, just never routed to.
  //
  // The Array.isArray check is load-bearing, not defensive noise: isPieChartData only
  // tests `'slices' in data`, and PieChart calls slices.filter() during RENDER — outside
  // the result handler's try/catch, so a malformed `slices` would throw past it. The type
  // guard proves the key exists; it does not prove the component can use the value.
  //
  // It is INSIDE this branch rather than in its condition, and that placement is the
  // point. As a condition (`isPieChartData(data) && Array.isArray(...)`) a malformed
  // payload fell through to the dashboard branch, where it became `priorities = []` and
  // rendered "No priorities yet" — the same false claim the terminal branch above was
  // just added to eliminate. Guarding in the condition closed one ROUTE to that lie and
  // left another open. Here, anything chart-shaped either renders a chart or renders an
  // error, and cannot reach the dashboard branch at all. Found by the second review.
  if (isPieChartData(data)) {
    if (!Array.isArray(data.slices)) {
      return (
        <div style={{
          padding: '24px',
          textAlign: 'center',
          color: 'var(--color-text-secondary, #3D3D3A)',
          fontSize: '13px',
          lineHeight: '1.5',
          background: 'var(--color-background-secondary, #F5F4ED)',
          borderRadius: '12px',
        }}>
          <p style={{ margin: 0 }}>{t('noData')}</p>
        </div>
      )
    }
    return (
      <main
        role="main"
        aria-label="Time Allocation Pie Chart"
        style={{
          borderRadius: '16px',
          // Safe-area padding, same as the dashboard fullscreen branch. This was a flat
          // 16px: in host fullscreen on mobile, chart content sat under the notch.
          paddingTop: `${paddingTop}px`,
          paddingBottom: `${paddingBottom}px`,
          paddingLeft: `${paddingLeft}px`,
          paddingRight: `${paddingRight}px`,
          background: 'var(--color-background-secondary, #F5F4ED)',
          touchAction: 'pan-y',
          overscrollBehavior: 'contain',
          // M10: same reconciliation as the dashboard's fullscreen <main>.
          ...(isInline
            ? {}
            : isMobileHostFullscreen
              ? { maxWidth: '100%', marginLeft: '0', marginRight: '0' }
              // Same 480px desktop cap as the dashboard branch — see the rationale at
              // the fullscreen <main>. NOTE: this branch has NEVER carried an explicit
              // inline width; in inline mode it inherits #root. If the chart looks wrong,
              // that is why.
              : { maxWidth: '480px', marginLeft: 'auto', marginRight: 'auto' }),
        }}
      >
        {loadError && (
          <div
            role="status"
            style={{
              marginBottom: '12px',
              padding: '12px',
              fontSize: '14px',
              lineHeight: '1.4',
              color: 'var(--color-text-primary, #141413)',
              background: 'var(--color-background-primary, #fff)',
              border: '1px solid var(--color-border-primary, rgba(31,30,29,0.4))',
              borderRadius: '12px',
            }}
          >
            {loadError}
          </div>
        )}
        <PieChart
          slices={data.slices}
          totalHours={data.totalHours}
          weekStart={data.weekStart}
          weekEnd={data.weekEnd}
          semanticTargetLabel={data.semanticTargetLabel}
        />
      </main>
    )
  }

  // ============ Dashboard View ============
  // ============ C3 — close the "No priorities yet" CLASS at the consumer ============
  //
  // `dashboardData?.priorities ?? []` defaults a missing array to empty, and EmptyState
  // renders whenever the list is empty REGARDLESS OF WHY. Every path that produced a
  // truthy-but-wrong `data` object landed there. Five routes were found; three were
  // closed one at a time, and a fourth and fifth appeared behind them. Patching routes
  // was the wrong shape — this is the consumer, and it is where the claim is made.
  //
  // "No priorities yet" is a CLAIM ABOUT THE USER'S DATA. Make it only when the payload
  // actually supports it: a real array that is genuinely empty. Anything else is the
  // generic load error, which claims nothing.
  //
  // C2 already rejects malformed payloads at ingestion, so on the two known paths this is
  // unreachable. It is here anyway because ingestion validity is a property of those two
  // call sites, while this is a property of the claim — and a sixth route would otherwise
  // reopen the class.
  if (data && !Array.isArray((data as DashboardData).priorities)) {
    return (
      <div style={{
        padding: '24px',
        textAlign: 'center',
        color: 'var(--color-text-secondary, #3D3D3A)',
        fontSize: '13px',
        lineHeight: '1.5',
        background: 'var(--color-background-secondary, #F5F4ED)',
        borderRadius: '12px',
      }}>
        <p style={{ margin: 0 }}>{t('noData')}</p>
      </div>
    )
  }

  const dashboardData = data as DashboardData | null
  const priorities = dashboardData?.priorities ?? []
  const activePriorities = priorities.filter(p => p.status === 'active')
  const sortedPriorities = sortPrioritiesByKeyword(activePriorities)
  const availableKeywords = dashboardData?.available_keywords ?? []

  // Extract active keywords for TimeAllocationBar legend
  const activeKeywords: CalendarKeyword[] = []
  const keywordSet = new Set(activePriorities.map(p => p.calendarKeyword))
  if (keywordSet.has('P1')) activeKeywords.push('P1')
  if (keywordSet.has('P2')) activeKeywords.push('P2')
  if (keywordSet.has('P3')) activeKeywords.push('P3')

  // When editing or adding, don't allow starting another edit
  const canEdit = !editingPriorityId && !isAddingPriority

  // Inline mode: display-only (no CRUD actions)
  if (isInline) {
    return (
      <main
        role="main"
        aria-label="Priority Guardian Dashboard"
        style={{
          width: '100%',
          maxWidth: platform === 'mobile' ? '100%' : '560px',
          marginLeft: platform === 'mobile' ? '0' : 'auto',
          marginRight: platform === 'mobile' ? '0' : 'auto',
          background: 'var(--color-background-secondary, #F5F4ED)',
          borderRadius: '16px',
          padding: '12px',
          touchAction: 'pan-y',
          overscrollBehavior: 'contain',
        }}
      >
        {loadError && (
          <div style={{
            marginBottom: '16px',
            padding: '12px',
            fontSize: '14px',
            color: 'var(--color-text-danger, #7F2C28)',
            background: 'var(--color-background-primary, #fff)',
            borderRadius: '8px',
            border: '1px solid var(--color-border-danger, #fecaca)',
          }} role="alert">
            {loadError}
          </div>
        )}

        {/* Time Allocation Bar */}
        {dashboardData?.google_connected && (
          <TimeAllocationBar
            timeAllocation={timeAllocation}
            activeKeywords={activeKeywords}
            onRefresh={refreshData}
            isRefreshing={isRefreshing}
          />
        )}

        {/* Priority Cards (display-only) */}
        {sortedPriorities.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {sortedPriorities.map((priority) => (
              priority.type === 'deadline' ? (
                <DeadlineCard
                  key={priority.id}
                  priority={priority}
                  isInline
                  defaultDeliverablesExpanded={false}
                />
              ) : (
                <FlexibleCard
                  key={priority.id}
                  priority={priority}
                  isInline
                  defaultGoalsExpanded={false}
                />
              )
            ))}
          </div>
        ) : (
          <EmptyState />
        )}

        {/* Calendar connection status (inline, no actions) */}
        <CalendarConnectionMinimal connected={dashboardData?.google_connected ?? false} />

        {/* Expand to fullscreen button */}
        <ExpandButton onClick={handleExpandToFullscreen} />

        {/* Hint: CRUD requires full dashboard */}
        {sortedPriorities.length > 0 && (
          <p style={{
            fontSize: '11px',
            color: 'var(--color-text-secondary, #3D3D3A)',
            textAlign: 'center',
            marginTop: '8px',
            marginBottom: '0',
            fontStyle: 'italic',
          }}>
            {t('openDashboardToEdit')}
          </p>
        )}
      </main>
    )
  }

  // Fullscreen mode: full CRUD
  // On mobile in host fullscreen: use safeAreaInsets for precise padding (native header + home indicator)
  return (
    <main
      role="main"
      aria-label="Priority Guardian Dashboard"
      style={{
        borderRadius: '16px',
        paddingTop: `${paddingTop}px`,
        paddingLeft: `${paddingLeft}px`,
        paddingRight: `${paddingRight}px`,
        paddingBottom: `${paddingBottom}px`,
        // M10: full viewport width in mobile host fullscreen.
        // Desktop fullscreen is capped at 480px, NOT the inline declaration's 560px.
        // Inline never reaches its own cap — the host chat panel is narrower (~378px
        // observed) — so inline width is host-determined and varies with the window.
        // "Match inline" is therefore not a value PG can set; the previous 560 matched an
        // inert number. 480 is chosen for two reasons: it narrows the perceived jump from
        // inline, and at 14px body text it keeps line length nearer the comfortable 45-75
        // characters (560px of content ran ~90-100). Mobile fullscreen is unaffected — it
        // uses the full viewport per the design guidelines.
        //
        // History: this was 672px until Claude-C — INHERITED FROM THE CHATGPT WIDGET and
        // unreachable, because #root's 600px cap sat above it. Nobody chose it for this
        // layout and nobody had ever seen it render, which is why it survived four
        // increments and two adversarial reviews unexamined.
        maxWidth: isMobileHostFullscreen ? '100%' : '480px',
        marginLeft: isMobileHostFullscreen ? '0' : 'auto',
        marginRight: isMobileHostFullscreen ? '0' : 'auto',
        background: 'var(--color-background-secondary, #F5F4ED)',
        touchAction: 'pan-y',
        overscrollBehavior: 'contain',
      }}
    >
      {/* Only show widget minimize header when host is NOT controlling fullscreen */}
      {/* KEPT DELIBERATELY, WITH AN EXPIRY — this was `{!hostFullscreen && ...}`, which
          is now always false here: hostFullscreen derives from displayMode, and this
          branch only renders in fullscreen. So the guard silently made PG's only fallback
          exit unreachable, along with handleMinimizeToInline.
          The guidelines say Claude renders a close button in the native header bar in
          fullscreen. NOBODY HAS OBSERVED IT — host fullscreen was unreachable until C1,
          so B's pre-registered "confirm the native close returns cleanly to inline" could
          never be run. Deleting the only fallback exit on a documented-but-unobserved
          behaviour is the exact trade this project has been punished for repeatedly (the
          500px limit, the deprecated service, --maxfail=5 — all documented, none true).
          The asymmetry decides it: if the native close exists, the cost is one redundant
          control for one release; if it is missing or unobvious on some surface, the user
          is trapped in fullscreen with no way out.
          EXPIRY: the Claude-C on-host pass. Host fullscreen is finally producible, so
          Nadja will see PG's Minimize bar and Claude's close side by side. If the native
          close is clearly present and returns cleanly on BOTH platforms, delete this
          header and handleMinimizeToInline — before submission, since two exit
          affordances on one surface is the kind of thing a reviewer notices. */}
      <FullscreenHeader onMinimize={handleMinimizeToInline} />

      {loadError && (
        <div
          style={{
            marginBottom: '16px',
            padding: '12px',
            fontSize: '14px',
            color: 'var(--color-text-danger, #7F2C28)',
            background: 'var(--color-background-primary, #fff)',
            borderRadius: '8px',
            border: '1px solid var(--color-border-danger, #fecaca)',
          }}
          role="alert"
        >
          {loadError}
        </div>
      )}

      {/* Time Allocation Bar */}
      {dashboardData?.google_connected && (
        <TimeAllocationBar
          timeAllocation={timeAllocation}
          activeKeywords={activeKeywords}
          onRefresh={refreshData}
          isRefreshing={isRefreshing}
        />
      )}

      {/* Priority Cards (full CRUD) */}
      {sortedPriorities.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: platform === 'mobile' ? '20px' : '12px' }}>
          {sortedPriorities.map((priority) => (
            <PriorityCardWrapper
              key={priority.id}
              priority={priority}
              priorities={activePriorities}
              isEditing={editingPriorityId === priority.id}
              canStartEdit={canEdit}
              defaultSectionsExpanded={true}
              onStartEdit={() => setEditingPriorityId(priority.id)}
              onCancelEdit={() => setEditingPriorityId(null)}
              onSavePriority={handleUpdatePriority}
              onDeletePriority={handleDeletePriority}
              onKeywordChange={handleKeywordChange}
              onToggleDeliverable={handleToggleDeliverable}
              onRenameDeliverable={handleRenameDeliverable}
              onDeleteDeliverable={handleDeleteDeliverable}
              onAddDeliverable={handleAddDeliverable}
              onAddGoal={handleAddGoal}
              onToggleGoal={handleToggleGoal}
              onRenameGoal={handleRenameGoal}
              onDeleteGoal={handleDeleteGoal}
            />
          ))}
        </div>
      ) : (
        <EmptyState />
      )}

      {/* Add Priority Section */}
      {isAddingPriority ? (
        <div style={{ marginTop: '16px' }}>
          <AddPriorityForm
            availableKeywords={availableKeywords}
            onAdd={handleAddPriority}
            onCancel={() => setIsAddingPriority(false)}
          />
        </div>
      ) : (
        availableKeywords.length > 0 && canEdit && (
          <div style={{ marginTop: '16px' }}>
            <AddPriorityButton onClick={() => setIsAddingPriority(true)} />
          </div>
        )
      )}

      {/* Connection Status */}
      {appRef.current && (
        <div style={{ marginTop: platform === 'mobile' ? '24px' : '16px' }}>
          <ConnectionStatus
            app={appRef.current}
            connected={dashboardData?.google_connected ?? false}
            onRefresh={refreshData}
            isRefreshing={isRefreshing}
            awaitingOAuth={awaitingOAuth}
            onAwaitingOAuthChange={setAwaitingOAuth}
          />
        </div>
      )}
    </main>
  )
}

interface PriorityCardWrapperProps {
  priority: Priority
  priorities: Priority[]
  isEditing: boolean
  canStartEdit: boolean
  defaultSectionsExpanded: boolean
  onStartEdit: () => void
  onCancelEdit: () => void
  onSavePriority: (priorityId: string, data: {
    name?: string
    deadline?: string
    weekly_hour_target?: number
    checkpoint_date?: string
  }) => Promise<void>
  onDeletePriority: (priorityId: string) => Promise<void>
  onKeywordChange: (priorityId: string, keyword: CalendarKeyword) => Promise<void>
  onToggleDeliverable: (deliverableId: string, done: boolean) => Promise<void>
  onRenameDeliverable: (deliverableId: string, name: string) => Promise<void>
  onDeleteDeliverable: (deliverableId: string) => Promise<void>
  onAddDeliverable: (priorityId: string, name: string) => Promise<void>
  onAddGoal: (priorityId: string, text: string) => Promise<void>
  onToggleGoal: (goalId: string, achieved: boolean) => Promise<void>
  onRenameGoal: (goalId: string, text: string) => Promise<void>
  onDeleteGoal: (goalId: string) => Promise<void>
}

function PriorityCardWrapper({
  priority,
  priorities,
  isEditing,
  canStartEdit,
  defaultSectionsExpanded,
  onStartEdit,
  onCancelEdit,
  onSavePriority,
  onDeletePriority,
  onKeywordChange,
  onToggleDeliverable,
  onRenameDeliverable,
  onDeleteDeliverable,
  onAddDeliverable,
  onAddGoal,
  onToggleGoal,
  onRenameGoal,
  onDeleteGoal,
}: PriorityCardWrapperProps) {
  if (priority.type === 'deadline') {
    return (
      <DeadlineCard
        priority={priority}
        priorities={priorities}
        isEditing={isEditing}
        defaultDeliverablesExpanded={defaultSectionsExpanded}
        onStartEdit={canStartEdit ? onStartEdit : undefined}
        onCancelEdit={onCancelEdit}
        onSave={onSavePriority}
        onDelete={onDeletePriority}
        onKeywordChange={onKeywordChange}
        onToggleDeliverable={onToggleDeliverable}
        onRenameDeliverable={onRenameDeliverable}
        onDeleteDeliverable={onDeleteDeliverable}
        onAddDeliverable={onAddDeliverable}
      />
    )
  }
  return (
    <FlexibleCard
      priority={priority}
      priorities={priorities}
      isEditing={isEditing}
      defaultGoalsExpanded={defaultSectionsExpanded}
      onStartEdit={canStartEdit ? onStartEdit : undefined}
      onCancelEdit={onCancelEdit}
      onSave={onSavePriority}
      onDelete={onDeletePriority}
      onKeywordChange={onKeywordChange}
      onAddGoal={(text) => onAddGoal(priority.id, text)}
      onToggleGoal={onToggleGoal}
      onRenameGoal={onRenameGoal}
      onDeleteGoal={onDeleteGoal}
    />
  )
}

function EmptyState() {
  return (
    <div style={{
      padding: '24px',
      textAlign: 'center',
      background: 'var(--color-background-primary, #fff)',
      borderRadius: '12px',
      border: '1px solid var(--color-border-primary, rgba(31,30,29,0.4))',
    }}>
      <p style={{ fontSize: '16px', fontWeight: 500, color: 'var(--color-text-primary, #141413)', marginBottom: '8px' }}>
        {t('noPriorities')}
      </p>
      <p style={{ fontSize: '14px', color: 'var(--color-text-secondary, #3D3D3A)' }}>
        {t('noPrioritiesHint')}
      </p>
    </div>
  )
}

export default App
