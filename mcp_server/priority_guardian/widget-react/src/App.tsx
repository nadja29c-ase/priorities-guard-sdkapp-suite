import { useState, useEffect, useRef, useCallback } from 'react'
import type { Priority, ToolOutputData } from './types'
import { getToolOutput, sortPrioritiesByKeyword, extractStructuredContent } from './utils'
import { ConnectionStatus } from './components/ConnectionStatus'
import { DeadlineCard } from './components/DeadlineCard'
import { FlexibleCard } from './components/FlexibleCard'

function App() {
  // Theme is handled automatically by SDK CSS via data-theme attribute

  const [data, setData] = useState<ToolOutputData | null>(null)
  const [isInitialized, setIsInitialized] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)

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

  // Refresh data by calling get_priorities
  const refreshData = useCallback(async () => {
    if (!window.openai?.callTool) return

    setIsRefreshing(true)
    try {
      const result = await window.openai.callTool<{ data?: ToolOutputData }>('get_priorities', {})
      const content = extractStructuredContent<{ data?: ToolOutputData }>(result)
      if (content?.data) {
        setData(content.data)
        setLoadError(null)
      }
    } catch (err) {
      console.error('Failed to refresh data:', err)
      setLoadError('Failed to refresh. Please try again.')
    } finally {
      setIsRefreshing(false)
      notifyHeight()
    }
  }, [notifyHeight])

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

  return (
    <main
      role="main"
      aria-label="Priority Guardian Dashboard"
      className="bg-surface-secondary rounded-2xl px-6 py-5 -m-4"
    >
      {/* Connection Status Header */}
      <ConnectionStatus
        connected={data?.google_connected ?? false}
        connectedAt={data?.google_connected_at}
        onRefresh={refreshData}
        isRefreshing={isRefreshing}
      />

      {loadError && (
        <div className="mb-4 p-3 text-sm text-danger bg-surface rounded-lg border border-danger-outline" role="alert">
          {loadError}
        </div>
      )}

      {/* Priority Cards */}
      {sortedPriorities.length > 0 ? (
        <div className="flex flex-col gap-4">
          {sortedPriorities.map((priority) => (
            <PriorityCard key={priority.id} priority={priority} />
          ))}
        </div>
      ) : (
        <EmptyState />
      )}
    </main>
  )
}

function PriorityCard({ priority }: { priority: Priority }) {
  if (priority.type === 'deadline') {
    return <DeadlineCard priority={priority} />
  }
  return <FlexibleCard priority={priority} />
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
