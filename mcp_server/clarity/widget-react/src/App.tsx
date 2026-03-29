import { useState, useEffect, useRef, useCallback } from 'react'
import type { Cluster } from './types'
import { getToolOutput, sortClustersByPriority } from './utils'
import { Header } from './components/Header'
import { ClusterCard } from './components/ClusterCard'

// Widget state persisted across re-renders via OpenAI SDK
interface MindSortWidgetState {
  scrollY: number
}

function App() {
  // Theme is handled automatically by SDK CSS via data-theme attribute

  const [clusters, setClusters] = useState<Cluster[]>([])
  const [isInitialized, setIsInitialized] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  // Track last processed toolOutput to detect updates
  const lastToolOutputRef = useRef<unknown>(null)

  const [defaultCollapsed, setDefaultCollapsed] = useState(false)

  // Notify host of height changes (for iOS scroll fix)
  const notifyHeight = useCallback(() => {
    requestAnimationFrame(() => {
      window.openai?.notifyIntrinsicHeight?.()
    })
  }, [])

  // Restore scroll position from widgetState after initialization
  useEffect(() => {
    if (!isInitialized) return
    const savedState = window.openai?.widgetState as MindSortWidgetState | undefined
    if (savedState?.scrollY) {
      requestAnimationFrame(() => {
        window.scrollTo(0, savedState.scrollY)
      })
    }
  }, [isInitialized])

  // Load clusters from window.openai.toolOutput
  const loadClusters = useCallback(() => {
    const t = window.openai?.toolOutput
    if (!t) return  // No data yet, wait for event

    // Skip if toolOutput hasn't changed since last render
    if (t === lastToolOutputRef.current) return
    lastToolOutputRef.current = t

    const { clusters: data, error } = getToolOutput()

    if (error) {
      setLoadError(error)
      console.error('MindSort AI widget load error:', error)
    } else {
      setLoadError(null)
    }

    setClusters(data)

    // Derive collapsed_by_default from toolOutput structuredContent
    const isMobile =
      (window.openai as any)?.userAgent?.device?.type === 'mobile' ||
      /iPhone|iPad|iPod|Android/.test(navigator?.userAgent || '')
    const collapsedByDefault = isMobile && (
      (t as any)?.result?.structuredContent?.collapsed_by_default === true ||
      (t as any)?.structuredContent?.collapsed_by_default === true ||
      (t as any)?.collapsed_by_default === true
    )
    setDefaultCollapsed(collapsedByDefault)

    setIsInitialized(true)

    // Notify host of new content height
    notifyHeight()
  }, [notifyHeight])

  // Initial load and listen for openai:set_globals
  useEffect(() => {
    loadClusters()

    const handleSetGlobals = () => {
      loadClusters()
    }

    window.addEventListener('openai:set_globals', handleSetGlobals, { passive: true })
    return () => {
      window.removeEventListener('openai:set_globals', handleSetGlobals)
    }
  }, [loadClusters])

  // Notify host when error state changes (affects widget height)
  useEffect(() => {
    if (isInitialized) {
      notifyHeight()
    }
  }, [loadError, isInitialized, notifyHeight])

  // Persist scroll position to widgetState
  useEffect(() => {
    if (!isInitialized) return

    let timeoutId: ReturnType<typeof setTimeout>

    const handleScroll = () => {
      // Debounce: only save after user stops scrolling for 150ms
      clearTimeout(timeoutId)
      timeoutId = setTimeout(() => {
        window.openai?.setWidgetState?.({
          scrollY: window.scrollY
        } satisfies MindSortWidgetState)
      }, 150)
    }

    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => {
      clearTimeout(timeoutId)
      window.removeEventListener('scroll', handleScroll)
    }
  }, [isInitialized])

  // Sort clusters by priority for display
  const sortedClusters = sortClustersByPriority(clusters)

  // Loading state (derive from ref, not separate state)
  if (!isInitialized) {
    return (
      <div className="p-6 text-center text-sm text-secondary bg-surface-secondary rounded-xl">
        Loading...
      </div>
    )
  }

  return (
    <main
      role="main"
      aria-label="MindSort AI Board"
      className="bg-surface-secondary rounded-2xl px-8 py-6 -m-4"
    >
      <Header />

      {loadError && (
        <div className="mb-4 p-3 text-sm text-danger bg-surface rounded-lg border border-danger-outline" role="alert">
          {loadError}
        </div>
      )}

      {sortedClusters.length > 0 ? (
        <div className="grid gap-4 grid-cols-[repeat(auto-fit,minmax(240px,1fr))]">
          {sortedClusters.map((cluster) => (
            <ClusterCard
              key={cluster.cluster_name}
              cluster={cluster}
              defaultCollapsed={defaultCollapsed}
              onToggle={notifyHeight}
            />
          ))}
        </div>
      ) : (
        <div className="p-6 text-center text-sm text-secondary bg-surface rounded-xl">
          No saved board yet. Start one by sharing what's on your mind in the chat.
        </div>
      )}

      {/* Auto-save indicator */}
      <p className="text-xs text-secondary mt-3 text-left">Changes are saved automatically</p>
    </main>
  )
}

export default App
