import { useState, useEffect, useRef, useCallback } from 'react'
import type { Priority, ToolOutputData, WidgetState, TimeAllocation, CalendarKeyword, DashboardData } from './types'
import { isPieChartData, isDashboardData } from './types'
import { getToolOutput, sortPrioritiesByKeyword, extractStructuredContent } from './utils'
import { ConnectionStatus } from './components/ConnectionStatus'
import { DeadlineCard } from './components/DeadlineCard'
import { FlexibleCard } from './components/FlexibleCard'
import { AddPriorityForm, AddPriorityButton } from './components/AddPriorityForm'
import { TimeAllocationBar } from './components/TimeAllocationBar'
import { PieChart } from './components/PieChart'
import { FullscreenHeader } from './components/FullscreenHeader'
import { ExpandButton } from './components/ExpandButton'
import { CalendarConnectionMinimal } from './components/CalendarConnectionMinimal'

type DisplayMode = 'inline' | 'fullscreen'

function App() {
  // Theme is handled automatically by SDK CSS via data-theme attribute

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

  // Display mode state (inline = collapsed sections, fullscreen = expanded)
  const [displayMode, setDisplayMode] = useState<DisplayMode>(() => {
    const mode = (window.openai as { displayMode?: string } | undefined)?.displayMode
    return mode === 'fullscreen' ? 'fullscreen' : 'inline'
  })

  const isInline = displayMode !== 'fullscreen'

  // Ref to avoid re-running effect on data change
  const isInitializedRef = useRef(false)

  // Notify host of height changes (for iOS scroll fix)
  const notifyHeight = useCallback(() => {
    requestAnimationFrame(() => {
      window.openai?.notifyIntrinsicHeight?.()
    })
  }, [])

  // Load data from window.openai.toolOutput
  const loadData = useCallback(() => {
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

    // Set timeAllocation from get_priorities response (clears when undefined after disconnect)
    // Only DashboardData has timeAllocation; PieChartData doesn't
    if (parsed && isDashboardData(parsed)) {
      setTimeAllocation(parsed.timeAllocation)
    }

    setIsInitialized(true)
    isInitializedRef.current = true

    // Notify host of new content height
    notifyHeight()
  }, [notifyHeight])

  // Update data from tool response
  // Note: CRUD responses don't include timeAllocation, only get_priorities does
  // So we only update timeAllocation when it's present in the response
  const updateDataFromResponse = useCallback((content: { data?: ToolOutputData } | null | undefined) => {
    if (content?.data) {
      setData(content.data)
      setLoadError(null)

      // Update timeAllocation (clears when undefined after disconnect)
      // Only DashboardData has timeAllocation; PieChartData doesn't
      if (isDashboardData(content.data)) {
        setTimeAllocation(content.data.timeAllocation)
      }

      notifyHeight()
    }
  }, [notifyHeight])

  // Refresh data by calling get_priorities
  const refreshData = useCallback(async () => {
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

  // Display mode handlers - only manage internal layout state
  // The host manages its own fullscreen container; we just expand/collapse content
  const handleExpandToFullscreen = useCallback(() => {
    setDisplayMode('fullscreen')
    notifyHeight()
  }, [notifyHeight])

  const handleMinimizeToInline = useCallback(() => {
    setDisplayMode('inline')
    notifyHeight()
  }, [notifyHeight])

  // ============ Effects ============

  // Initial load and listen for openai:set_globals
  useEffect(() => {
    loadData()

    const handleSetGlobals = () => {
      loadData()
    }

    window.addEventListener('openai:set_globals', handleSetGlobals, { passive: true })
    return () => {
      window.removeEventListener('openai:set_globals', handleSetGlobals)
    }
  }, [loadData])

  // Notify host when error state changes (affects widget height)
  useEffect(() => {
    if (isInitialized) {
      notifyHeight()
    }
  }, [loadError, isInitialized, notifyHeight])

  // Notify height when add form state changes
  useEffect(() => {
    if (isInitialized) {
      notifyHeight()
    }
  }, [isAddingPriority, isInitialized, notifyHeight])

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
      window.openai.setWidgetState(state)
    }
  }, [editingPriorityId, isAddingPriority])

  // Loading state
  if (!isInitialized) {
    return (
      <div className="p-6 text-center text-sm text-secondary bg-surface-secondary rounded-xl">
        Loading...
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
        className={`bg-surface-secondary rounded-2xl p-4 pb-2${!isInline ? ' max-w-2xl mx-auto' : ''}`}
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
      className={`bg-surface-secondary rounded-2xl p-4 pb-2${!isInline ? ' max-w-2xl mx-auto' : ''}`}
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
      <TimeAllocationBar
        timeAllocation={timeAllocation}
        activeKeywords={activeKeywords}
        onRefresh={refreshData}
        isRefreshing={isRefreshing}
      />

      {/* Priority Cards (primary content) */}
      {sortedPriorities.length > 0 ? (
        <div className="flex flex-col gap-5">
          {sortedPriorities.map((priority) => (
            <PriorityCardWrapper
              key={`${priority.id}-${displayMode}`}
              priority={priority}
              priorities={activePriorities}
              isEditing={editingPriorityId === priority.id}
              canStartEdit={canEdit}
              defaultSectionsExpanded={!isInline}
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
            <AddPriorityButton onClick={() => setIsAddingPriority(true)} />
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
            connectedAt={dashboardData?.google_connected_at}
            onRefresh={refreshData}
            isRefreshing={isRefreshing}
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
      <p className="text-base font-medium text-default mb-2">No Priorities Yet</p>
      <p className="text-sm text-secondary">
        Ask the assistant to help you set up your top priorities.
      </p>
    </div>
  )
}

export default App
