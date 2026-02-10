import { useState, useEffect, useRef, useCallback } from 'react'
import type { Priority, ToolOutputData, WidgetState } from './types'
import { getToolOutput, sortPrioritiesByKeyword, extractStructuredContent } from './utils'
import { ConnectionStatus } from './components/ConnectionStatus'
import { DeadlineCard } from './components/DeadlineCard'
import { FlexibleCard } from './components/FlexibleCard'
import { AddPriorityForm, AddPriorityButton } from './components/AddPriorityForm'

function App() {
  // Theme is handled automatically by SDK CSS via data-theme attribute

  const [data, setData] = useState<ToolOutputData | null>(null)
  const [isInitialized, setIsInitialized] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)

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
    setIsInitialized(true)
    isInitializedRef.current = true

    // Notify host of new content height
    notifyHeight()
  }, [notifyHeight])

  // Update data from tool response
  const updateDataFromResponse = useCallback((content: { data?: ToolOutputData } | null | undefined) => {
    if (content?.data) {
      setData(content.data)
      setLoadError(null)
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
    desired_result?: string
  }) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('add_priority', priorityData)
    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)
    updateDataFromResponse(content)
    setIsAddingPriority(false)
  }, [updateDataFromResponse])

  const handleUpdatePriority = useCallback(async (priorityId: string, updates: {
    name?: string
    deadline?: string
    weekly_hour_target?: number
    checkpoint_date?: string
    desired_result?: string
  }) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('update_priority', {
      priority_id: priorityId,
      ...updates,
    })
    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)
    updateDataFromResponse(content)
    setEditingPriorityId(null)
  }, [updateDataFromResponse])

  const handleDeletePriority = useCallback(async (priorityId: string) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('delete_priority', {
      priority_id: priorityId,
      confirm: true,
    })
    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)
    updateDataFromResponse(content)
  }, [updateDataFromResponse])

  // ============ Deliverable CRUD Operations ============

  const handleAddDeliverable = useCallback(async (priorityId: string, name: string) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('add_deliverable', {
      priority_id: priorityId,
      name,
    })
    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)
    updateDataFromResponse(content)
  }, [updateDataFromResponse])

  const handleToggleDeliverable = useCallback(async (deliverableId: string, done: boolean) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('update_deliverable', {
      deliverable_id: deliverableId,
      done,
    })
    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)
    updateDataFromResponse(content)
  }, [updateDataFromResponse])

  const handleRenameDeliverable = useCallback(async (deliverableId: string, name: string) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('update_deliverable', {
      deliverable_id: deliverableId,
      name,
    })
    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)
    updateDataFromResponse(content)
  }, [updateDataFromResponse])

  const handleDeleteDeliverable = useCallback(async (deliverableId: string) => {
    if (!window.openai?.callTool) throw new Error('Tool calls not available')

    const result = await window.openai.callTool<{ data?: ToolOutputData }>('delete_deliverable', {
      deliverable_id: deliverableId,
      confirm: true,
    })
    const content = extractStructuredContent<{ data?: ToolOutputData }>(result)
    updateDataFromResponse(content)
  }, [updateDataFromResponse])

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

  const priorities = data?.priorities ?? []
  const activePriorities = priorities.filter(p => p.status === 'active')
  const sortedPriorities = sortPrioritiesByKeyword(activePriorities)
  const availableKeywords = data?.available_keywords ?? []

  // When editing or adding, don't allow starting another edit
  const canEdit = !editingPriorityId && !isAddingPriority

  return (
    <main
      role="main"
      aria-label="Priority Guardian Dashboard"
      className="bg-surface-secondary rounded-2xl px-6 py-5 -m-4"
    >
      {loadError && (
        <div className="mb-4 p-3 text-sm text-danger bg-surface rounded-lg border border-danger-outline" role="alert">
          {loadError}
        </div>
      )}

      {/* Priority Cards (primary content) */}
      {sortedPriorities.length > 0 ? (
        <div className="flex flex-col gap-4">
          {sortedPriorities.map((priority) => (
            <PriorityCardWrapper
              key={priority.id}
              priority={priority}
              isEditing={editingPriorityId === priority.id}
              canStartEdit={canEdit}
              onStartEdit={() => setEditingPriorityId(priority.id)}
              onCancelEdit={() => setEditingPriorityId(null)}
              onSavePriority={handleUpdatePriority}
              onDeletePriority={handleDeletePriority}
              onToggleDeliverable={handleToggleDeliverable}
              onRenameDeliverable={handleRenameDeliverable}
              onDeleteDeliverable={handleDeleteDeliverable}
              onAddDeliverable={handleAddDeliverable}
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

      {/* Connection Status (settings-level control, at bottom) */}
      <div className="mt-6">
        <ConnectionStatus
          connected={data?.google_connected ?? false}
          connectedAt={data?.google_connected_at}
          onRefresh={refreshData}
          isRefreshing={isRefreshing}
        />
      </div>
    </main>
  )
}

interface PriorityCardWrapperProps {
  priority: Priority
  isEditing: boolean
  canStartEdit: boolean
  onStartEdit: () => void
  onCancelEdit: () => void
  onSavePriority: (priorityId: string, data: Record<string, unknown>) => Promise<void>
  onDeletePriority: (priorityId: string) => Promise<void>
  onToggleDeliverable: (deliverableId: string, done: boolean) => Promise<void>
  onRenameDeliverable: (deliverableId: string, name: string) => Promise<void>
  onDeleteDeliverable: (deliverableId: string) => Promise<void>
  onAddDeliverable: (priorityId: string, name: string) => Promise<void>
}

function PriorityCardWrapper({
  priority,
  isEditing,
  canStartEdit,
  onStartEdit,
  onCancelEdit,
  onSavePriority,
  onDeletePriority,
  onToggleDeliverable,
  onRenameDeliverable,
  onDeleteDeliverable,
  onAddDeliverable,
}: PriorityCardWrapperProps) {
  if (priority.type === 'deadline') {
    return (
      <DeadlineCard
        priority={priority}
        isEditing={isEditing}
        onStartEdit={canStartEdit ? onStartEdit : () => {}}
        onCancelEdit={onCancelEdit}
        onSave={onSavePriority}
        onDelete={onDeletePriority}
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
      isEditing={isEditing}
      onStartEdit={canStartEdit ? onStartEdit : () => {}}
      onCancelEdit={onCancelEdit}
      onSave={onSavePriority}
      onDelete={onDeletePriority}
      onToggleDeliverable={onToggleDeliverable}
      onRenameDeliverable={onRenameDeliverable}
      onDeleteDeliverable={onDeleteDeliverable}
      onAddDeliverable={onAddDeliverable}
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
