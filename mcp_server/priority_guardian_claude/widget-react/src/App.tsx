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

  // Stale bridge detection — if onAppCreated never fires, widget is from old session
  const [isBridgeStale, setIsBridgeStale] = useState(false)

  // App reference for CRUD operations
  const appRef = useRef<McpApp | null>(null)

  // Timestamp of last CRUD operation — suppress stale ontoolresult for 1500ms after
  const lastCrudAtRef = useRef(0)

  const isInline = displayMode !== 'fullscreen'

  // MCP Apps bridge: useApp hook to receive tool results
  const { app } = useApp({
    appInfo: { name: 'Priority Guardian', version: '1.0.0' },
    capabilities: {},
    onAppCreated: useCallback((appInstance: McpApp) => {
      appRef.current = appInstance

      // Set initial display mode from app
      const hostContext = appInstance.getHostContext()
      if (hostContext?.displayMode === 'fullscreen') {
        setDisplayMode('fullscreen')
      }

      // Register handler for incoming tool results
      appInstance.ontoolresult = (result: McpUiToolResultNotification['params']) => {
        // Guard against stale get_priorities echoes after CRUD.
        // Note: McpUiToolResultNotification carries no tool name (CallToolResult only),
        // so we cannot filter by tool name — timestamp window is the correct approach.
        if (Date.now() - lastCrudAtRef.current < 1500) return

        try {
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
          }
        } catch (err) {
          console.error('PG Claude widget: Error processing tool result:', err)
          setLoadError('Failed to load dashboard data.')
          setIsInitialized(true)
        }
      }

      // Listen for display mode changes from host via context changes
      // ctx is a partial update — only changed fields are present
      appInstance.onhostcontextchanged = (ctx) => {
        if (ctx.displayMode !== undefined) {
          setDisplayMode(ctx.displayMode === 'fullscreen' ? 'fullscreen' : 'inline')
        }
      }
    }, []),
  })

  // Inject host theme CSS variables
  useHostStyles(app)

  // Store app reference
  useEffect(() => {
    if (app) {
      appRef.current = app
    }
  }, [app])

  // Stale bridge detection — if onAppCreated hasn't fired within 3s, session is stale
  useEffect(() => {
    const timeout = setTimeout(() => {
      if (!appRef.current) {
        setIsBridgeStale(true)
      }
    }, 3000)
    return () => clearTimeout(timeout)
  }, [])

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
      setLoadError('Failed to refresh. Please try again.')
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
    // Always expand locally first for immediate UI response
    setDisplayMode('fullscreen')
    // On mobile only: also request host fullscreen if available.
    // On desktop: local expand is sufficient and preferred (avoids unnecessary host fullscreen).
    // This specifically targets iOS scroll trapping — host fullscreen gives the widget
    // its own scroll context separate from the chat page.
    if (appRef.current?.requestDisplayMode) {
      const ctx = appRef.current.getHostContext()
      const isMobile = ctx?.platform === 'mobile'
      if (isMobile && ctx?.availableDisplayModes?.includes('fullscreen')) {
        try {
          await appRef.current.requestDisplayMode({ mode: 'fullscreen' })
        } catch {
          // Silent — local fullscreen already set above
        }
      }
    }
  }, [isBridgeStale])

  const handleMinimizeToInline = useCallback(async () => {
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

  // Loading state
  if (!isInitialized) {
    return (
      <div style={{
        padding: '24px',
        textAlign: 'center',
        fontSize: '14px',
        color: 'var(--color-text-secondary, #5c5c5c)',
        background: 'var(--color-background-secondary, #f9f9f9)',
        borderRadius: '12px',
      }}>
        {t('loading')}
      </div>
    )
  }

  // Stale session overlay — bridge never connected, widget is from previous session
  if (isBridgeStale) {
    return (
      <div style={{
        padding: '24px',
        textAlign: 'center',
        color: 'var(--color-text-secondary, #5c5c5c)',
        fontSize: '13px',
        lineHeight: '1.5',
        background: 'var(--color-background-secondary, #f9f9f9)',
        borderRadius: '12px',
      }}>
        <p style={{ marginBottom: '8px', fontWeight: 600 }}>
          {t('widgetSessionExpired')}
        </p>
        <p style={{ margin: 0 }}>{t('widgetSessionExpiredHint')}</p>
      </div>
    )
  }

  // ============ Pie Chart View ============
  if (isPieChartData(data) && data.slices.length > 0) {
    return (
      <main
        role="main"
        aria-label="Time Allocation Pie Chart"
        style={{
          borderRadius: '16px',
          padding: '16px',
          background: 'var(--color-background-secondary, #f9f9f9)',
          touchAction: 'pan-y',
          overscrollBehavior: 'contain',
          ...(isInline ? {} : { maxWidth: '672px', marginLeft: 'auto', marginRight: 'auto' }),
        }}
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
          background: 'var(--color-background-secondary, #f9f9f9)',
          borderRadius: '16px',
          padding: '16px',
          touchAction: 'pan-y',
          overscrollBehavior: 'contain',
        }}
      >
        {loadError && (
          <div style={{
            marginBottom: '16px',
            padding: '12px',
            fontSize: '14px',
            color: 'var(--color-text-danger, #dc2626)',
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
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
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
            color: 'var(--color-text-tertiary, #8c8c8c)',
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
  return (
    <main
      role="main"
      aria-label="Priority Guardian Dashboard"
      style={{
        borderRadius: '16px',
        padding: '16px',
        maxWidth: '672px',
        marginLeft: 'auto',
        marginRight: 'auto',
        background: 'var(--color-background-secondary, #f9f9f9)',
        touchAction: 'pan-y',
        overscrollBehavior: 'contain',
      }}
    >
      {/* Fullscreen header with minimize button */}
      <FullscreenHeader onMinimize={handleMinimizeToInline} />

      {loadError && (
        <div
          style={{
            marginBottom: '16px',
            padding: '12px',
            fontSize: '14px',
            color: 'var(--color-text-danger, #dc2626)',
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
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
        <div style={{ marginTop: '24px' }}>
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
      border: '1px solid var(--color-border, #e5e5e5)',
    }}>
      <p style={{ fontSize: '16px', fontWeight: 500, color: 'var(--color-text-primary, #0d0d0d)', marginBottom: '8px' }}>
        {t('noPriorities')}
      </p>
      <p style={{ fontSize: '14px', color: 'var(--color-text-secondary, #5c5c5c)' }}>
        {t('noPrioritiesHint')}
      </p>
    </div>
  )
}

export default App
