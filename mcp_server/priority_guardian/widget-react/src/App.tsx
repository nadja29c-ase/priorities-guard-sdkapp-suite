import { useState, useEffect, useRef, useCallback } from 'react'

import type { Priority, ToolOutputData, WidgetState, TimeAllocation, CalendarKeyword, DashboardData } from './types'
import { isPieChartData, isDashboardData } from './types'
import { getToolOutput, sortPrioritiesByKeyword, extractStructuredContent } from './utils'
import { t } from './i18n'
import { ConnectionStatus } from './components/ConnectionStatus'
import { DeadlineCard } from './components/DeadlineCard'
import { FlexibleCard } from './components/FlexibleCard'
import { AddPriorityForm, AddPriorityButton } from './components/AddPriorityForm'
import { TimeAllocationBar } from './components/TimeAllocationBar'
import { PieChart } from './components/PieChart'
import { FullscreenHeader } from './components/FullscreenHeader'
import { InlinePriorityRow } from './components/InlinePriorityRow'
import { ExpandButton } from './components/ExpandButton'
import { CalendarConnectionMinimal } from './components/CalendarConnectionMinimal'
import { reportWidgetDiagnostic } from './widgetErrorReporter'

// Inc 89: temporary diagnostic flag. Set to false before next non-diagnostic deploy.
const PG_DIAG_FULLSCREEN = true

// Card width fix: explicit width for both display modes, applied unconditionally
// so neither mode ever derives its width from #root by accident (main.css previously
// gave inline no width rule of its own, so it silently inherited #root's 900px cap).
// - Inline and fullscreen share one value: switching between them is a pure displayMode
//   state flip (see handleExpandToFullscreen/handleMinimizeToInline below), and the
//   <main> container itself is not remounted — both branches return the same JSX
//   element, so keeping it at one width avoids a layout jump on the container. NOTE:
//   this does NOT mean nothing below it remounts — sortedPriorities.map's key includes
//   displayMode (see `${priority.id}-${displayMode}` a few hundred lines down), so every
//   priority card already unmounts/remounts on toggle for a separate, pre-existing
//   reason unrelated to width. The "avoid a reflow" argument here applies to the <main>
//   box, not to everything it contains.
// - The 672px value itself (Tailwind's max-w-2xl) is carried over from this file's
//   pre-existing fullscreen rule, not independently measured against this card's content
//   (badge/name row, HourRing/stat row, deliverable list) — subject to revision at the
//   Verification Layer 1 gate (real ChatGPT session, representative widths).
const CARD_MAX_WIDTH_CLASS = 'max-w-2xl mx-auto'

type DisplayMode = 'inline' | 'fullscreen'

function App() {
  // Theme is handled automatically by SDK CSS via data-theme attribute
  // (same approach as Clarity widget — applyDocumentTheme not needed)

  const [data, setData] = useState<ToolOutputData | null>(null)
  const [isInitialized, setIsInitialized] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)

  // TimeAllocation is stored separately so CRUD operations don't clear it
  // (CRUD responses don't include timeAllocation, only get_priorities does)
  const [timeAllocation, setTimeAllocation] = useState<TimeAllocation | undefined>(undefined)

  // Edit state: only one priority can be edited at a time
  // Initialize from widgetState if available (survives widget re-renders)
  const [editingPriorityId, setEditingPriorityId] = useState<string | null>(() => {
    const widgetState = window.openai?.widgetState as WidgetState | undefined
    return widgetState?.editingPriorityId ?? null
  })

  // Add priority form state
  const [isAddingPriority, setIsAddingPriority] = useState(() => {
    const widgetState = window.openai?.widgetState as WidgetState | undefined
    return widgetState?.addFormOpen ?? false
  })

  // OAuth flow state - persisted to survive widget remounts during redirect
  const [awaitingOAuth, setAwaitingOAuth] = useState(() => {
    const widgetState = window.openai?.widgetState as WidgetState | undefined
    return widgetState?.awaitingOAuth ?? false
  })

  // Display mode state (inline = collapsed sections, fullscreen = expanded)
  const [displayMode, setDisplayMode] = useState<DisplayMode>(() => {
    const mode = (window.openai as { displayMode?: string } | undefined)?.displayMode
    return mode === 'fullscreen' ? 'fullscreen' : 'inline'
  })

  // Bottom safe area inset from host (iOS input bar clearance, Inc 69)
  const [hostBottomInset, setHostBottomInset] = useState<number>(
    () => (window.openai as any)?.safeArea?.insets?.bottom ?? 0
  )

  const isInline = displayMode !== 'fullscreen'

  // Mobile detection — only mobile gets host requestDisplayMode calls
  const ua = (window.openai as any)?.userAgent
  const isMobile =
    ua?.device?.type === 'mobile' ||
    /iPhone|iPad|iPod|Android/.test(navigator.userAgent)

  // Ref to avoid re-running effect on data change
  const isInitializedRef = useRef(false)

  // Ref to detect whether toolOutput has actually changed on each openai:set_globals event
  const lastToolOutputRef = useRef<unknown>(null)

  // Ref to block set_globals after CRUD — iOS fires with new toolOutput reference (Inc 59)
  const hasCrudDataRef = useRef(false)

  // Tracks previous isAddingPriority for transition detection (iOS scroll fix)
  const wasAddingRef = useRef(false)

  // Tracks whether fullscreen was entered specifically for the add form (mobile only).
  // Used to reverse the fullscreen on form close without affecting user-initiated fullscreen.
  const enteredFullscreenForAddRef = useRef(false)

  // Tracks whether fullscreen was entered specifically for editing (mobile only). (Inc 71)
  const enteredFullscreenForEditRef = useRef(false)
  const wasEditingRef = useRef<string | null>(null)

  // Inc 89.10: desktop-local fullscreen intent guard.
  // Desktop fullscreen is owned by the widget (no requestDisplayMode call).
  // Host displayMode stays 'inline' during desktop local-fullscreen sessions.
  // When true, ignore host set_globals(hostMode: 'inline') syncs that would revert
  // local fullscreen. Cleared by handleMinimizeToInline. Mobile is unaffected.
  const desktopLocalFullscreenIntentRef = useRef(false)

  // Guard against double backfillTimeAllocation calls (race between mount and set_globals)
  const backfillCalledRef = useRef(false)

  // Inc 89: session-scoped diagnostic id
  const diagSessionIdRef = useRef<string>(
    `pg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  )

  // Inc 89: helper to log every displayMode change with caller marker
  const logDisplayModeChange = (next: DisplayMode | 'sync' | 'sync-ignored', caller: string, extra?: Record<string, unknown>) => {
    if (!PG_DIAG_FULLSCREEN) return
    reportWidgetDiagnostic({
      event: 'displayMode.change',
      data: {
        sid: diagSessionIdRef.current,
        next,
        caller,
        hostMode: (window.openai as { displayMode?: string } | undefined)?.displayMode,
        ts: performance.now(),
        ...extra,
      },
    })
  }

  // Notify host of height changes (for iOS scroll fix)
  const notifyHeight = useCallback(() => {
    requestAnimationFrame(() => {
      window.openai?.notifyIntrinsicHeight?.()
    })
  }, [])

  // Handle subsequent toolOutput updates after initial load
  // Called on every openai:set_globals event after widget is initialized
  const handleToolOutputUpdate = useCallback(() => {
    // Only run if widget is already initialized
    if (!isInitializedRef.current) return

    // Block stale host toolOutput after CRUD (Inc 59) — CRUD data wins
    if (hasCrudDataRef.current) return

    // Guard: if toolOutput is absent or same reference, do nothing
    // (openai:set_globals fires for theme, displayMode, locale changes too)
    const currentToolOutput = window.openai?.toolOutput
    if (!currentToolOutput || currentToolOutput === lastToolOutputRef.current) return

    // Parse new toolOutput using shared utility
    const { data: parsed, error } = getToolOutput()

    if (error) {
      setLoadError(error)
      console.error('PG widget update error:', error)
    } else {
      setLoadError(null)
    }

    if (parsed) {
      // Use functional setData to preserve weeklyHourActual if not in new response
      setData(prevData => {
        if (isDashboardData(parsed) && isDashboardData(prevData)) {
          const existingById = Object.fromEntries(
            prevData.priorities.map(p => [p.id, p])
          )
          return {
            ...parsed,
            priorities: parsed.priorities.map(p => ({
              ...p,
              weeklyHourActual: p.weeklyHourActual ?? existingById[p.id]?.weeklyHourActual ?? null,
            })),
          } as DashboardData
        }
        return parsed
      })

      // Update timeAllocation (only DashboardData has it)
      if (isDashboardData(parsed)) {
        if (parsed.timeAllocation !== undefined) {
          setTimeAllocation(parsed.timeAllocation)
        } else if (
          parsed.timeAllocation === undefined &&
          parsed.google_connected === false
        ) {
          // Clear timeAllocation when disconnected (Inc 65)
          setTimeAllocation(undefined)
        }
      }
    }

    // Update ref to current toolOutput
    lastToolOutputRef.current = currentToolOutput
  }, [])

  // Update data from tool response
  // Note: CRUD responses don't include timeAllocation or weeklyHourActual,
  // only get_priorities does. Preserve calendar-derived data across CRUD operations.
  const updateDataFromResponse = useCallback((content: { data?: ToolOutputData } | null | undefined) => {
    if (content?.data) {
      // Use functional setData to access previous state and preserve weeklyHourActual
      setData(prevData => {
        if (isDashboardData(content.data) && isDashboardData(prevData)) {
          // Build lookup of existing priorities by ID
          const existingById = Object.fromEntries(
            prevData.priorities.map(p => [p.id, p])
          )
          // Merge weeklyHourActual from existing state (CRUD responses have null)
          return {
            ...content.data,
            priorities: content.data.priorities.map(p => ({
              ...p,
              weeklyHourActual: p.weeklyHourActual ?? existingById[p.id]?.weeklyHourActual ?? null,
            })),
          } as DashboardData
        }
        return content.data!
      })
      setLoadError(null)

      // Update timeAllocation when present, or clear when disconnected
      // CRUD responses don't include it; only get_priorities does
      if (isDashboardData(content.data)) {
        if (content.data.timeAllocation !== undefined) {
          setTimeAllocation(content.data.timeAllocation)
        } else if (
          content.data.timeAllocation === undefined &&
          content.data.google_connected === false
        ) {
          // Clear timeAllocation when disconnected (Inc 65)
          setTimeAllocation(undefined)
        }
      }

      notifyHeight()

      // Advance ref to prevent handleToolOutputUpdate from overwriting CRUD result on next set_globals
      const currentToolOutput = window.openai?.toolOutput
      if (currentToolOutput) {
        lastToolOutputRef.current = currentToolOutput
      }

      // Mark that we have CRUD data — block subsequent set_globals (Inc 59)
      hasCrudDataRef.current = true
    }
  }, [notifyHeight])

  // Backfill timeAllocation when widget mounts with CRUD response lacking it (Inc 73)
  // Fire-and-forget: silently fetches get_priorities to restore progress bar
  // Only extracts timeAllocation — does NOT use updateDataFromResponse (which sets hasCrudDataRef)
  const backfillTimeAllocation = useCallback(async () => {
    if (!window.openai?.callTool) return
    try {
      const result = await window.openai.callTool<{ data?: ToolOutputData }>('get_priorities', {})
      const content = extractStructuredContent<{ data?: ToolOutputData }>(result)
      // Only extract timeAllocation — priorities already set from create_priority response
      if (content?.data && isDashboardData(content.data) && content.data.timeAllocation !== undefined) {
        setTimeAllocation(content.data.timeAllocation)
      }
    } catch {
      // Silently ignore — user can use refresh button as manual recovery
    }
  }, [])

  // Load data from window.openai.toolOutput (first load only)
  const loadData = useCallback(() => {
    hasCrudDataRef.current = false  // Reset on load/remount (Inc 59)
    backfillCalledRef.current = false  // Reset backfill guard
    if (isInitializedRef.current) return

    const t = window.openai?.toolOutput
    if (!t) return // No data yet, wait for event

    const { data: parsed, error } = getToolOutput()

    if (error) {
      setLoadError(error)
      console.error('PG widget load error:', error)
    } else {
      setLoadError(null)
    }

    setData(parsed)

    // Set timeAllocation from get_priorities response
    // Only DashboardData has timeAllocation; PieChartData doesn't
    if (parsed && isDashboardData(parsed)) {
      if (parsed.timeAllocation !== undefined) {
        setTimeAllocation(parsed.timeAllocation)
      } else if (
        parsed.timeAllocation === undefined &&
        parsed.google_connected === false
      ) {
        // Clear timeAllocation when disconnected (Inc 65)
        setTimeAllocation(undefined)
      } else if (
        parsed.timeAllocation === undefined &&
        parsed.google_connected === true &&
        parsed.priorities.length > 0 &&
        window.openai?.callTool &&
        !backfillCalledRef.current  // Guard against double call (race between mount and set_globals)
      ) {
        // Backfill timeAllocation when missing but Google connected (Inc 73)
        // Fire-and-forget — does not block loadData
        backfillCalledRef.current = true
        backfillTimeAllocation()
      }
    }

    setIsInitialized(true)
    isInitializedRef.current = true

    // Track last toolOutput reference for subsequent update detection
    lastToolOutputRef.current = window.openai?.toolOutput

    // Notify host of new content height
    notifyHeight()
  }, [notifyHeight, backfillTimeAllocation])

  // Refresh data by calling get_priorities
  const refreshData = useCallback(async () => {
    hasCrudDataRef.current = false  // Allow set_globals after explicit refresh (Inc 59)
    if (!window.openai?.callTool) return

    setIsRefreshing(true)
    try {
      const result = await window.openai.callTool<{ data?: ToolOutputData }>('get_priorities', {})
      const content = extractStructuredContent<{ data?: ToolOutputData }>(result)
      updateDataFromResponse(content)
    } catch (err) {
      console.error('Failed to refresh data:', err)
      setLoadError('Failed to refresh. Please try again.')
    } finally {
      setIsRefreshing(false)
      notifyHeight()
    }
  }, [notifyHeight, updateDataFromResponse])

  // ============ Priority CRUD Operations ============

  const handleAddPriority = useCallback(async (priorityData: {
    name: string
    type: 'deadline' | 'flexible'
    deadline?: string
    weekly_hour_target?: number
    checkpoint_date?: string
    initial_goal_text?: string
  }) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('add_priority', priorityData) as { isError?: boolean }

    // Check for error response
    if (result?.isError) {
      throw new Error("Couldn't save. Try again.")
    }

    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)

    // Check for malformed response (no data)
    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    updateDataFromResponse(content)
    setIsAddingPriority(false)
  }, [updateDataFromResponse])

  const handleUpdatePriority = useCallback(async (priorityId: string, updates: {
    name?: string
    deadline?: string
    weekly_hour_target?: number
    checkpoint_date?: string
  }) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('update_priority', {
      priority_id: priorityId,
      ...updates,
    }) as { isError?: boolean }

    // Check for error response
    if (result?.isError) {
      throw new Error("Couldn't save. Try again.")
    }

    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)

    // Check for malformed response (no data)
    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    updateDataFromResponse(content)
    setEditingPriorityId(null)
  }, [updateDataFromResponse])

  const handleDeletePriority = useCallback(async (priorityId: string) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('delete_priority', {
      priority_id: priorityId,
      confirm: true,
    }) as { isError?: boolean }

    // Check for error response
    if (result?.isError) {
      throw new Error("Couldn't save. Try again.")
    }

    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)

    // Check for malformed response (no data)
    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    updateDataFromResponse(content)

    // Clear edit state if deleted priority was being edited
    setEditingPriorityId((current) => current === priorityId ? null : current)
  }, [updateDataFromResponse])

  // ============ Deliverable CRUD Operations ============

  const handleAddDeliverable = useCallback(async (priorityId: string, name: string) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('add_deliverable', {
      priority_id: priorityId,
      name,
    }) as { isError?: boolean }

    if (result?.isError) {
      throw new Error("Couldn't save. Try again.")
    }

    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    updateDataFromResponse(content)
  }, [updateDataFromResponse])

  const handleToggleDeliverable = useCallback(async (deliverableId: string, done: boolean) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('update_deliverable', {
      deliverable_id: deliverableId,
      done,
    }) as { isError?: boolean }

    if (result?.isError) {
      throw new Error("Couldn't save. Try again.")
    }

    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    updateDataFromResponse(content)
  }, [updateDataFromResponse])

  const handleRenameDeliverable = useCallback(async (deliverableId: string, name: string) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('update_deliverable', {
      deliverable_id: deliverableId,
      name,
    }) as { isError?: boolean }

    if (result?.isError) {
      throw new Error("Couldn't save. Try again.")
    }

    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    updateDataFromResponse(content)
  }, [updateDataFromResponse])

  const handleDeleteDeliverable = useCallback(async (deliverableId: string) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('delete_deliverable', {
      deliverable_id: deliverableId,
      confirm: true,
    }) as { isError?: boolean }

    if (result?.isError) {
      throw new Error("Couldn't save. Try again.")
    }

    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    updateDataFromResponse(content)
  }, [updateDataFromResponse])

  // ============ Goal CRUD Operations (Inc D) ============

  const handleAddGoal = useCallback(async (priorityId: string, text: string) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('add_goal', {
      priority_id: priorityId,
      text,
    }) as { isError?: boolean }

    if (result?.isError) {
      throw new Error("Couldn't save. Try again.")
    }

    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    updateDataFromResponse(content)
  }, [updateDataFromResponse])

  const handleToggleGoal = useCallback(async (goalId: string, achieved: boolean) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('update_goal', {
      goal_id: goalId,
      achieved,
    }) as { isError?: boolean }

    if (result?.isError) {
      throw new Error("Couldn't save. Try again.")
    }

    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    updateDataFromResponse(content)
  }, [updateDataFromResponse])

  const handleRenameGoal = useCallback(async (goalId: string, text: string) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('update_goal', {
      goal_id: goalId,
      text,
    }) as { isError?: boolean }

    if (result?.isError) {
      throw new Error("Couldn't save. Try again.")
    }

    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    updateDataFromResponse(content)
  }, [updateDataFromResponse])

  const handleDeleteGoal = useCallback(async (goalId: string) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('delete_goal', {
      goal_id: goalId,
      confirm: true,
    }) as { isError?: boolean }

    if (result?.isError) {
      throw new Error("Couldn't save. Try again.")
    }

    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    updateDataFromResponse(content)
  }, [updateDataFromResponse])

  // ============ Keyword Reassignment (Inc 13) ============

  const handleKeywordChange = useCallback(async (priorityId: string, keyword: CalendarKeyword) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('update_priority', {
      priority_id: priorityId,
      calendar_keyword: keyword,
    }) as { isError?: boolean }

    if (result?.isError) {
      throw new Error("Couldn't save. Try again.")
    }

    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)

    if (!content?.data) {
      throw new Error("Couldn't save. Try again.")
    }

    updateDataFromResponse(content)
  }, [updateDataFromResponse])

  // ============ Display Mode Handlers ============

  type OpenAIHost = {
    displayMode?: 'inline' | 'fullscreen'
    requestDisplayMode?: (opts: { mode: 'inline' | 'fullscreen' }) => void
    toolOutput?: unknown
  }

  // Display mode handlers - request host container change + update internal layout state
  // Mobile: request host fullscreen takeover. Desktop: CSS-only layout change (no host call).
  const handleExpandToFullscreen = useCallback(() => {
    if (isMobile) {
      try {
        if (
          window.openai?.requestDisplayMode &&
          (window.openai as OpenAIHost).displayMode !== 'fullscreen'
        ) {
          window.openai.requestDisplayMode({ mode: 'fullscreen' })
        }
      } catch { /* noop */ }
    } else {
      // Inc 89.10: desktop fullscreen is local-only; mark intent so handleSetGlobals
      // ignores stale host inline syncs until the user explicitly minimizes.
      desktopLocalFullscreenIntentRef.current = true
    }
    logDisplayModeChange('fullscreen', 'handleExpandToFullscreen', { isMobile })
    setDisplayMode('fullscreen')
    notifyHeight()
  }, [isMobile, notifyHeight])

  const handleMinimizeToInline = useCallback(() => {
    if (isMobile) {
      try {
        if (
          window.openai?.requestDisplayMode &&
          (window.openai as OpenAIHost).displayMode !== 'inline'
        ) {
          window.openai.requestDisplayMode({ mode: 'inline' })
        }
      } catch { /* noop */ }
    } else {
      // Inc 89.10: user explicitly closing local fullscreen — release the guard
      // so subsequent host inline syncs work normally.
      desktopLocalFullscreenIntentRef.current = false
    }
    logDisplayModeChange('inline', 'handleMinimizeToInline', { isMobile })
    setDisplayMode('inline')
    notifyHeight()
  }, [isMobile, notifyHeight])

  // On mobile: go fullscreen before opening the add form to avoid iOS host scroll-off-screen.
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

  // ============ Effects ============

  // Set document language for VoiceOver on mount (Inc 62)
  // Use full locale (e.g., 'de-DE') for precise voice selection, not just 'de'
  useEffect(() => {
    const rawLocale = (window.openai?.locale ?? 'en').replace(/_/g, '-')
    document.documentElement.lang = rawLocale
  }, [])

  // Inc 89: log initial displayMode at mount
  useEffect(() => {
    if (!PG_DIAG_FULLSCREEN) return
    reportWidgetDiagnostic({
      event: 'mount',
      data: {
        sid: diagSessionIdRef.current,
        initialDisplayMode: displayMode,
        hostMode: (window.openai as { displayMode?: string } | undefined)?.displayMode,
        availableDisplayModes: (window.openai as { availableDisplayModes?: unknown } | undefined)?.availableDisplayModes,
        hasRequestDisplayMode: typeof (window.openai as { requestDisplayMode?: unknown } | undefined)?.requestDisplayMode === 'function',
        widgetBuildTime: __WIDGET_BUILD_TIME__,  // injected by Vite — actual build moment
      },
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Initial load and listen for openai:set_globals
  useEffect(() => {
    loadData()

    const handleSetGlobals = () => {
      // Sync document language for VoiceOver (Inc 62)
      const rawLocale = (window.openai?.locale ?? 'en').replace(/_/g, '-')
      document.documentElement.lang = rawLocale

      // Sync displayMode from host (only after init to avoid layout flicker)
      if (isInitializedRef.current) {
        const hostMode = (window.openai as OpenAIHost | undefined)?.displayMode
        // Inc 89: log every set_globals event with host displayMode, regardless of whether we sync
        if (PG_DIAG_FULLSCREEN) {
          reportWidgetDiagnostic({
            event: 'set_globals',
            data: {
              sid: diagSessionIdRef.current,
              hostMode,
              ts: performance.now(),
            },
          })
        }
        if (hostMode === 'fullscreen' || hostMode === 'inline') {
          // Inc 89.10: desktop-local fullscreen intent guard.
          // On desktop, when the user has opened local fullscreen, host displayMode
          // stays 'inline' (because we never called requestDisplayMode). Any host
          // set_globals(inline) during this period is stale and would revert the
          // user's intended fullscreen. Mobile and host 'fullscreen' syncs are
          // never blocked.
          const isStaleDesktopInlineSync =
            hostMode === 'inline' &&
            !isMobile &&
            desktopLocalFullscreenIntentRef.current

          if (isStaleDesktopInlineSync) {
            // Log the ignored sync for dev-mode and v15 production verification.
            logDisplayModeChange('sync-ignored', 'handleSetGlobals.intentGuard', { hostMode })
          } else {
            // Inc 89: log the sync intent before it fires
            logDisplayModeChange('sync', 'handleSetGlobals.hostSync', { hostMode })
            setDisplayMode(prev => prev !== hostMode ? hostMode : prev)
          }
        }
      }

      // Sync bottom safe area inset (iOS input bar clearance, Inc 69)
      const bottom = (window.openai as any)?.safeArea?.insets?.bottom ?? 0
      setHostBottomInset(bottom)

      if (isInitializedRef.current) {
        handleToolOutputUpdate()
      } else {
        loadData()
      }
    }

    window.addEventListener('openai:set_globals', handleSetGlobals, { passive: true })
    return () => {
      window.removeEventListener('openai:set_globals', handleSetGlobals)
    }
  }, [loadData, handleToolOutputUpdate])

  // Notify host when error state changes (affects widget height)
  useEffect(() => {
    if (isInitialized) {
      notifyHeight()
    }
  }, [loadError, isInitialized, notifyHeight])

  // On mobile: when add form closes, return to inline — but only if fullscreen was entered
  // specifically for the add form. Does not collapse user-initiated fullscreen. (Inc 67)
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

  // On mobile: when edit mode closes, return to inline — only if fullscreen was entered
  // specifically for editing. Does not collapse user-initiated fullscreen. (Inc 71)
  useEffect(() => {
    if (!isInitialized) return

    // Only act on non-null → null transition
    if (wasEditingRef.current === null || editingPriorityId !== null) {
      wasEditingRef.current = editingPriorityId
      return
    }

    wasEditingRef.current = editingPriorityId

    if (isMobile && enteredFullscreenForEditRef.current) {
      enteredFullscreenForEditRef.current = false
      handleMinimizeToInline()
    }
  }, [editingPriorityId, isInitialized, isMobile, handleMinimizeToInline])

  // Persist edit state to widgetState (survives widget re-renders)
  useEffect(() => {
    if (window.openai?.setWidgetState) {
      const state: WidgetState = {}
      if (editingPriorityId) {
        state.editingPriorityId = editingPriorityId
      }
      if (isAddingPriority) {
        state.addFormOpen = true
      }
      if (awaitingOAuth) {
        state.awaitingOAuth = true
      }
      window.openai.setWidgetState(state)
    }
  }, [editingPriorityId, isAddingPriority, awaitingOAuth])

  // Loading state
  if (!isInitialized) {
    return (
      <div className="p-6 text-center text-sm text-secondary bg-surface-secondary rounded-xl">
        {t('loading')}
      </div>
    )
  }

  // ============ Pie Chart View ============
  // Renders when get_weekly_report returns data with non-empty slices
  // Empty slices (week before priorities existed) falls through to dashboard
  if (isPieChartData(data) && data.slices.length > 0) {
    return (
      <main
        role="main"
        aria-label="Time Allocation Pie Chart"
        className={`bg-surface-secondary rounded-2xl p-4 pb-2 ${CARD_MAX_WIDTH_CLASS}`}
        style={!isInline ? { paddingBottom: `calc(2rem + ${hostBottomInset}px)` } : undefined}
      >
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
  // Renders when get_priorities returns data with priorities
  const dashboardData = data as DashboardData | null
  const priorities = dashboardData?.priorities ?? []
  const activePriorities = priorities.filter(p => p.status === 'active')
  const sortedPriorities = sortPrioritiesByKeyword(activePriorities)
  const availableKeywords = dashboardData?.available_keywords ?? []

  // Extract active keywords for TimeAllocationBar legend
  // Only show keywords that have active priorities (e.g., if no P2 priority exists, don't show P2)
  const activeKeywords: CalendarKeyword[] = []
  const keywordSet = new Set(activePriorities.map(p => p.calendarKeyword))
  // Maintain P1 > P2 > P3 order
  if (keywordSet.has('P1')) activeKeywords.push('P1')
  if (keywordSet.has('P2')) activeKeywords.push('P2')
  if (keywordSet.has('P3')) activeKeywords.push('P3')

  // When editing or adding, don't allow starting another edit
  const canEdit = !editingPriorityId && !isAddingPriority

  return (
    <main
      role="main"
      aria-label="Priority Guardian Dashboard"
      className={`bg-surface-secondary rounded-2xl p-4 pb-2 ${CARD_MAX_WIDTH_CLASS}`}
      style={!isInline ? { paddingBottom: `calc(2rem + ${hostBottomInset}px)` } : undefined}
    >
      {/* Fullscreen header - only in fullscreen mode */}
      {!isInline && (
        <FullscreenHeader onMinimize={handleMinimizeToInline} />
      )}

      {loadError && (
        <div className="mb-4 p-3 text-sm text-danger bg-surface rounded-lg border border-danger-outline" role="alert">
          {loadError}
        </div>
      )}

      {/* Time Allocation Bar (shows calendar hours breakdown) */}
      {/* Only render when Google Calendar is connected (Inc 65) */}
      {dashboardData?.google_connected && (
        <TimeAllocationBar
          timeAllocation={timeAllocation}
          activeKeywords={activeKeywords}
          onRefresh={refreshData}
          isRefreshing={isRefreshing}
        />
      )}

      {/* Priority Cards (primary content) */}
      {/* inc_card_size_fix2.md: inline gets its own compact renderer
          (InlinePriorityRow) — DeadlineCard/FlexibleCard never mount in
          inline mode at all. Fullscreen's branch is unchanged. */}
      {sortedPriorities.length > 0 ? (
        isInline ? (
          <div className="flex flex-col gap-2">
            {sortedPriorities.map((priority) => (
              <InlinePriorityRow key={priority.id} priority={priority} />
            ))}
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            {sortedPriorities.map((priority) => (
              <PriorityCardWrapper
                key={`${priority.id}-${displayMode}`}
                priority={priority}
                priorities={activePriorities}
                isEditing={editingPriorityId === priority.id}
                canStartEdit={canEdit}
                defaultSectionsExpanded={!isInline}
                onStartEdit={() => {
                  if (isMobile && displayMode !== 'fullscreen') {
                    enteredFullscreenForEditRef.current = true
                    handleExpandToFullscreen()
                  }
                  setEditingPriorityId(priority.id)
                }}
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
        )
      ) : (
        <EmptyState />
      )}

      {/* Add Priority Section */}
      {isAddingPriority ? (
        <div className="mt-4">
          <AddPriorityForm
            availableKeywords={availableKeywords}
            onAdd={handleAddPriority}
            onCancel={() => setIsAddingPriority(false)}
          />
        </div>
      ) : (
        availableKeywords.length > 0 && canEdit && (
          <div className="mt-4">
            <AddPriorityButton onClick={handleOpenAddForm} />
          </div>
        )
      )}

      {/* Inline mode: Minimal calendar indicator + Expand button */}
      {isInline && (
        <>
          <CalendarConnectionMinimal connected={dashboardData?.google_connected ?? false} />
          <ExpandButton onClick={handleExpandToFullscreen} />
        </>
      )}

      {/* Fullscreen mode: Full Connection Status */}
      {!isInline && (
        <div className="mt-6">
          <ConnectionStatus
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
  priorities: Priority[]  // All priorities for keyword picker (Inc 13)
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
  onKeywordChange: (priorityId: string, keyword: CalendarKeyword) => Promise<void>  // Inc 13
  onToggleDeliverable: (deliverableId: string, done: boolean) => Promise<void>
  onRenameDeliverable: (deliverableId: string, name: string) => Promise<void>
  onDeleteDeliverable: (deliverableId: string) => Promise<void>
  onAddDeliverable: (priorityId: string, name: string) => Promise<void>
  // Goal handlers (Inc D)
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
        onStartEdit={canStartEdit ? onStartEdit : () => {}}
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
  // Flexible priorities have goals (Inc D)
  return (
    <FlexibleCard
      priority={priority}
      priorities={priorities}
      isEditing={isEditing}
      defaultGoalsExpanded={defaultSectionsExpanded}
      onStartEdit={canStartEdit ? onStartEdit : () => {}}
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
    <div className="p-6 text-center bg-surface rounded-xl border border-default">
      <p className="text-base font-medium text-default mb-2">{t('noPriorities')}</p>
      <p className="text-sm text-secondary">
        {t('noPrioritiesHint')}
      </p>
    </div>
  )
}

export default App

