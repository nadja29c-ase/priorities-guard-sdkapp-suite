import { useState, useEffect, useRef, useCallback } from 'react'
import type { Cluster } from './types'
import { extractStructuredContent, getToolOutput, sortClustersByPriority } from './utils'
import { Header } from './components/Header'
import { ClusterCard } from './components/ClusterCard'
import { SaveModal } from './components/SaveModal'
import { Button } from '@openai/apps-sdk-ui/components/Button'
import { Check } from '@openai/apps-sdk-ui/components/Icon'

function App() {
  // Theme is handled automatically by SDK CSS via data-theme attribute

  const [clusters, setClusters] = useState<Cluster[]>([])
  const [isInitialized, setIsInitialized] = useState(false)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [showSaved, setShowSaved] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Ref to avoid re-running effect on clusters change
  const isInitializedRef = useRef(false)

  // Ref for Save button focus restoration after modal closes
  const saveButtonRef = useRef<HTMLButtonElement>(null)

  // Load clusters from window.openai.toolOutput
  const loadClusters = useCallback(() => {
    if (isInitializedRef.current) return

    const t = window.openai?.toolOutput
    if (!t) return  // No data yet, wait for event

    const data = getToolOutput()
    setClusters(data)
    setIsInitialized(true)
    isInitializedRef.current = true
  }, [])

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

  // Handle save
  const handleSave = async () => {
    if (isSaving || clusters.length === 0) return

    setIsSaving(true)
    setSaveError(null)

    try {
      if (window.openai?.callTool) {
        const result = await window.openai.callTool<{ saved?: boolean }>('save_board', {
          confirmed: true,
          clusters: clusters,
        })

        // Check if save was successful
        const content = extractStructuredContent<{ saved?: boolean }>(result)
        if (content?.saved === true) {
          setShowSaved(true)
        }
      } else {
        console.warn('window.openai.callTool not available')
      }
    } catch (err) {
      console.error('Save failed:', err)
      setSaveError('Save failed. Please try again.')
    } finally {
      setIsSaving(false)
      setIsModalOpen(false)
      // Restore focus to Save button after modal closes (defer to allow DOM update)
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
      className="bg-gray-100 rounded-2xl px-8 py-6 -m-4"
    >
      <Header />

      {saveError && (
        <div className="mb-4 p-3 text-sm text-red-700 bg-red-50 rounded-lg">
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
      <div className="sticky bottom-0 pt-4 pb-2 bg-gray-100 flex justify-end items-center">
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
          onClick={() => setIsModalOpen(true)}
          disabled={clusters.length === 0}
        >
          Save
        </Button>
      </div>

      <SaveModal
        isOpen={isModalOpen}
        onCancel={() => setIsModalOpen(false)}
        onConfirm={handleSave}
        isSaving={isSaving}
        triggerRef={saveButtonRef}
      />
    </main>
  )
}

export default App
