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

  // Connection failure (Claude-B / B2). Two distinguishable terminal states:
  //   'timeout' — no connection within BRIDGE_TIMEOUT_MS. Almost always a widget
  //               rendered from a previous conversation, whose bridge no longer exists.
  //   'error'   — the SDK reported an explicit connection/initialisation failure.
  // Previously this was a single boolean set by a timer that tested whether the app
  // OBJECT existed. The object is assigned in onAppCreated, which runs BEFORE connect()
  // is attempted — so a connection that hung or failed left the object present, the
  // timer concluded the bridge was fine, and the widget rendered its loading skeleton
  // forever. `isBridgeStale` is now derived from a real connection outcome.
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

  // Track whether host accepted fullscreen (for hiding widget header on mobile)
  const [hostFullscreen, setHostFullscreen] = useState(false)

  // App reference for CRUD operations
  const appRef = useRef<McpApp | null>(null)

  // Ref for inline main element height diagnostic
  const inlineMainRef = useRef<HTMLElement>(null)

  // Timestamp of last CRUD operation — suppress stale ontoolresult for 1500ms after
  const lastCrudAtRef = useRef(0)

  const isInline = displayMode !== 'fullscreen'

  // DIAGNOSTIC: Log inline main height for 500px compliance check
  useEffect(() => {
    if (isInline && inlineMainRef.current && isInitialized) {
      const height = inlineMainRef.current.scrollHeight
      console.log(`[PG Diagnostic] Inline main scrollHeight: ${height}px (limit: 500px, ${height > 500 ? 'EXCEEDS LIMIT' : 'OK'})`)
    }
  }, [isInline, isInitialized, data, timeAllocation])

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
          // ---- B3: every exit below either initialises or sets a load error ----
          //
          // Previously this handler initialised ONLY inside the `structuredContent.data`
          // guard. Three distinct results fell straight through, setting neither an error
          // nor isInitialized — so the widget sat on its loading skeleton forever:
          // an MCP error result, empty structuredContent, and structuredContent without
          // the expected payload. All three now terminate.

          // CASE 1 — a valid MCP/tool error. Surface the message the SERVER chose.
          // Verified safe at the source (handlers/tools_dupl.py): an intentional
          // ToolUsageError returns str(e) — a user-facing rejection such as "You already
          // have 3 active priorities" — while an unexpected exception returns the fixed
          // string "Something went wrong. Please try again." Exception text and payload
          // internals never reach content[0].text, so §5.4's "no internal details" holds
          // because the server enforces it, not because we hope so.
          if (result?.isError) {
            const first = result.content?.[0]
            const serverMessage =
              first && 'text' in first && typeof first.text === 'string' ? first.text.trim() : ''
            setLoadError(serverMessage || t('noData'))
            setIsInitialized(true)
            return
          }

          const structuredContent = result?.structuredContent
          if (structuredContent?.data) {
            const resultData = structuredContent.data as DashboardData | PieChartData

            // Set locale from data if present
            if ('locale' in resultData && resultData.locale) {
              setLocale(resultData.locale as string)
            }

            setData(resultData)

            // Update timeAllocation from DashboardData
            if (!isPieChartData(resultData) && resultData.timeAllocation !== undefined) {
              setTimeAllocation(resultData.timeAllocation)
            }

            setLoadError(null)
            setIsInitialized(true)
            return
          }

          // CASES 2 and 3 — a non-error result whose structuredContent is missing,
          // empty, or present without the expected `data` payload. Both are "the call
          // succeeded but gave us nothing usable", which is not the user's problem to
          // interpret, so both get the same generic localized message. §5.4 forbids
          // exposing what was actually wrong with the payload.
          setLoadError(t('noData'))
          setIsInitialized(true)
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

    const applyHostContext = (ctx: HostContextUpdate) => {
      if (ctx.displayMode !== undefined) {
        const hostSaysFullscreen = ctx.displayMode === 'fullscreen'
        setDisplayMode(hostSaysFullscreen ? 'fullscreen' : 'inline')
        // Set in BOTH directions. This update came FROM the host, so a fullscreen report
        // is by definition host-controlled fullscreen.
        //
        // Previously only the false side was written, and `setHostFullscreen(true)`
        // existed nowhere in this file — so `hostFullscreen` was initialised false and
        // could never become true. It gates `isMobileHostFullscreen`, which gates every
        // safe-area inset. Fixing `platform` alone would therefore have changed nothing:
        // the insets would still never apply. A field written in only one direction by a
        // function that receives both is the tell.
        setHostFullscreen(hostSaysFullscreen)

        // ⚠️ REPORTED, NOT GUARDED — B1 can make a previously inert asymmetry visible.
        // handleExpandToFullscreen sets displayMode locally and never calls
        // requestDisplayMode, so the host is never told the widget went fullscreen.
        // Before B1 nothing could contradict that local state. Now this handler can:
        // if the host later sends any update carrying displayMode (an orientation change
        // or resize plausibly does), it will read 'inline' and yank the user out of
        // fullscreen mid-edit. Theme-only updates are safe — the guard above requires
        // ctx.displayMode !== undefined.
        //
        // NOT guarded here, because the fix belongs at the asymmetry (expand should tell
        // the host, as minimize does) and that is outside B1-B5. It may also be purely
        // theoretical if the host never includes displayMode in partial updates.
        // ON-HOST: expand locally, then rotate or resize, and see whether fullscreen
        // survives. Decide from the observation, not from this comment.
      }
      if (ctx.platform !== undefined) {
        setPlatform(ctx.platform)
      }
      // Per-inset guards: a partial safeAreaInsets must not reset the omitted sides.
      const insets = ctx.safeAreaInsets
      if (insets?.top !== undefined) setSafeAreaTop(insets.top)
      if (insets?.bottom !== undefined) setSafeAreaBottom(insets.bottom)
      if (insets?.left !== undefined) setSafeAreaLeft(insets.left)
      if (insets?.right !== undefined) setSafeAreaRight(insets.right)
    }

    // 1. Subscribe (additive — does not displace the SDK's own style listeners)
    const onHostContextChanged = (ctx: HostContextUpdate) => applyHostContext(ctx)
    app.addEventListener('hostcontextchanged', onHostContextChanged)

    // 2. Read the initial context, now that it exists
    const initial = app.getHostContext()
    if (initial) {
      applyHostContext(initial)
    }

    // 3. Remove on cleanup
    return () => {
      app.removeEventListener('hostcontextchanged', onHostContextChanged)
    }
  }, [app])

  // Store app reference
  useEffect(() => {
    if (app) {
      appRef.current = app
    }
  }, [app])

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
      const content = extractClaudeStructuredContent<{ data?: DashboardData }>(result)
      if (content?.data) {
        setData(content.data)
        if (content.data.timeAllocation !== undefined) {
          setTimeAllocation(content.data.timeAllocation)
        }
        setLoadError(null)
      }
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

  const handleExpandToFullscreen = useCallback(async () => {
    if (isBridgeStale) return
    setDisplayMode('fullscreen')
  }, [isBridgeStale])

  const handleMinimizeToInline = useCallback(async () => {
    setHostFullscreen(false)
    if (appRef.current?.requestDisplayMode) {
      try {
        const result = await appRef.current.requestDisplayMode({ mode: 'inline' })
        setDisplayMode(result.mode === 'fullscreen' ? 'fullscreen' : 'inline')
      } catch {
        // Silent — inline is the default, failure here is harmless
      }
    } else {
      setDisplayMode('inline')
    }
  }, [])

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
          // Matches the inline branch's desktop cap without reading `platform`:
          // on a mobile viewport the cap never binds and auto margins compute to 0,
          // so the ternary the inline branch uses does no work the cascade wouldn't.
          maxWidth: '560px',
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
          padding: '16px',
          background: 'var(--color-background-secondary, #F5F4ED)',
          touchAction: 'pan-y',
          overscrollBehavior: 'contain',
          ...(isInline ? {} : { maxWidth: '672px', marginLeft: 'auto', marginRight: 'auto' }),
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
        ref={inlineMainRef}
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
  // On desktop: fixed 16px padding
  // Safe-area padding (Claude-B / §5.2). Existing padding is a FLOOR, never reduced:
  // an inset smaller than the base padding must not shrink the layout, so each side takes
  // the larger of the two.
  //
  // Before B, this gate was dead TWICE OVER and either cause alone was sufficient:
  // `platform` was permanently undefined (its only writers ran before connect), AND
  // `hostFullscreen` could never become true (`setHostFullscreen(true)` existed nowhere).
  // So no inset was ever applied, and fixing only one of the two would have changed
  // nothing observable — which is precisely how the second cause stayed hidden.
  const isMobileHostFullscreen = platform === 'mobile' && hostFullscreen
  const BASE_PADDING = 16
  const BASE_PADDING_BOTTOM = 32
  const paddingTop = isMobileHostFullscreen
    ? Math.max(safeAreaTop, BASE_PADDING)
    : BASE_PADDING
  // NOTE: bottom uses a DIFFERENT formula from the other three — inset + base, floored at
  // 32, rather than max(inset, 16). This is deliberate: it preserves the pre-B behaviour
  // (`safeAreaBottom + 16 : 32`) because the composer sits below the widget and needs
  // clearance beyond the home indicator itself. Stated explicitly so the four sides are
  // not mistaken for one uniform rule.
  const paddingBottom = isMobileHostFullscreen
    ? Math.max(safeAreaBottom + BASE_PADDING, BASE_PADDING_BOTTOM)
    : BASE_PADDING
  // .left/.right were read nowhere before B. They matter in landscape, where the notch
  // intrudes horizontally and would otherwise clip controls.
  const paddingLeft = isMobileHostFullscreen
    ? Math.max(safeAreaLeft, BASE_PADDING)
    : BASE_PADDING
  const paddingRight = isMobileHostFullscreen
    ? Math.max(safeAreaRight, BASE_PADDING)
    : BASE_PADDING
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
        maxWidth: '672px',
        marginLeft: 'auto',
        marginRight: 'auto',
        background: 'var(--color-background-secondary, #F5F4ED)',
        touchAction: 'pan-y',
        overscrollBehavior: 'contain',
      }}
    >
      {/* Only show widget minimize header when host is NOT controlling fullscreen */}
      {!hostFullscreen && <FullscreenHeader onMinimize={handleMinimizeToInline} />}

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
