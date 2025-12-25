import { useState, useEffect, useRef, useCallback } from 'react'
import type { Cluster } from './types'
import { extractStructuredContent, getToolOutput, sortClustersByPriority } from './utils'
import { Header } from './components/Header'
import { ClusterCard } from './components/ClusterCard'
import { Button } from '@openai/apps-sdk-ui/components/Button'
import { Check } from '@openai/apps-sdk-ui/components/Icon'

function App() {
  // Theme is handled automatically by SDK CSS via data-theme attribute

  const [clusters, setClusters] = useState<Cluster[]>([])
  const [isInitialized, setIsInitialized] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [showSaved, setShowSaved] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Ref to avoid re-running effect on clusters change
  const isInitializedRef = useRef(false)

  // Ref for Save button focus management
  const saveButtonRef = useRef<HTMLButtonElement>(null)

  // Notify host of height changes (for iOS scroll fix)
  const notifyHeight = useCallback(() => {
    requestAnimationFrame(() => {
      window.openai?.notifyIntrinsicHeight?.()
    })
  }, [])

  // Log widgetState on mount (infrastructure for future state persistence)
  useEffect(() => {
    if (window.openai?.widgetState) {
      console.debug('Clarity: widgetState available', window.openai.widgetState)
    }
  }, [])

  // Load clusters from window.openai.toolOutput
  const loadClusters = useCallback(() => {
    if (isInitializedRef.current) return

    const t = window.openai?.toolOutput
    if (!t) return  // No data yet, wait for event

    const data = getToolOutput()
    setShowSaved(false)  // Reset stale indicator on new data load
    setClusters(data)
    setIsInitialized(true)
    isInitializedRef.current = true

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
  }, [saveError, isInitialized, notifyHeight])

  // Handle save
  const handleSave = async () => {
    if (isSaving || clusters.length === 0) return

    setIsSaving(true)
    setSaveError(null)

    try {
      if (window.openai?.callTool) {
        const result = await window.openai.callTool<{ saved?: boolean }>('save_board', {
          clusters: clusters,
        })

        // Check if save was successful
        const content = extractStructuredContent<{ saved?: boolean }>(result)
        if (content?.saved === true) {
          setShowSaved(true)
          // Clear after 3 seconds
          setTimeout(() => setShowSaved(false), 3000)
        }
      } else {
        console.warn('window.openai.callTool not available')
      }
    } catch (err) {
      console.error('Save failed:', err)
      setSaveError('Save failed. Please try again.')
    } finally {
      setIsSaving(false)
      // Restore focus to Save button after async save completes
      setTimeout(() => saveButtonRef.current?.focus(), 0)
    }
  }

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
      aria-label="Clarity Board"
      className="bg-surface-secondary rounded-2xl px-8 py-6 -m-4"
    >
      <Header />

      {saveError && (
        <div className="mb-4 p-3 text-sm text-danger bg-surface rounded-lg border border-danger-outline">
          {saveError}
        </div>
      )}

      {sortedClusters.length > 0 ? (
        <div className="grid gap-4 grid-cols-[repeat(auto-fit,minmax(240px,1fr))]">
          {sortedClusters.map((cluster) => (
            <ClusterCard key={cluster.cluster_name} cluster={cluster} />
          ))}
        </div>
      ) : (
        <div className="p-6 text-center text-sm text-secondary bg-surface rounded-xl">
          No saved board yet. Start one by sharing what's on your mind in the chat.
        </div>
      )}

      {/* Sticky Save button - always visible at bottom */}
      <div className="sticky bottom-0 pt-4 pb-2 bg-surface-secondary">
        <div className="flex justify-start items-center">
          {showSaved && (
            <span
              className="flex items-center gap-1 text-xs text-success font-medium mr-3"
              aria-live="polite"
            >
              <Check className="w-3.5 h-3.5" aria-hidden="true" />
              Saved
            </span>
          )}
          <Button
            ref={saveButtonRef}
            color="primary"
            variant="solid"
            onClick={handleSave}
            disabled={clusters.length === 0 || isSaving}
            aria-label={clusters.length === 0 ? "Save board (no items to save)" : "Save board"}
          >
            {isSaving ? 'Saving...' : 'Save'}
          </Button>
        </div>
        <p className="text-xs text-secondary mt-1 text-left">Only 1 board can be saved</p>
      </div>
    </main>
  )
}

export default App
