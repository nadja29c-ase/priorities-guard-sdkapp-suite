import { useState, useEffect, useRef, useCallback } from 'react'
import { useDocumentTheme } from '@openai/apps-sdk-ui/theme'
import { Button } from '@openai/apps-sdk-ui/components/Button'
import type { Cluster } from './types'
import { getToolOutput, sortClustersByPriority } from './utils'
import { Header } from './components/Header'
import { ClusterCard } from './components/ClusterCard'
import { SaveModal } from './components/SaveModal'

function App() {
  const theme = useDocumentTheme()

  const [clusters, setClusters] = useState<Cluster[]>([])
  const [isInitialized, setIsInitialized] = useState(false)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [showSaved, setShowSaved] = useState(false)

  // Ref to avoid re-running effect on clusters change
  const isInitializedRef = useRef(false)

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

    try {
      if (window.openai?.callTool) {
        const result = await window.openai.callTool('save_board', {
          confirmed: true,
          clusters: clusters,
        })

        // Check if save was successful
        const content = result?.structuredContent ?? result?.result?.structuredContent ?? result
        if ((content as { saved?: boolean })?.saved === true) {
          setShowSaved(true)
          setTimeout(() => setShowSaved(false), 3000)
        }
      } else {
        console.warn('window.openai.callTool not available')
      }
    } catch (err) {
      console.error('Save failed:', err)
    } finally {
      setIsSaving(false)
      setIsModalOpen(false)
    }
  }

  // Sort clusters by priority for display
  const sortedClusters = sortClustersByPriority(clusters)

  // Apply theme class to document
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  // Loading state
  if (!isInitialized) {
    return (
      <div className="p-6 text-center text-sm text-secondary bg-surface-secondary rounded-xl">
        Loading...
      </div>
    )
  }

  return (
    <div className="bg-surface-secondary rounded-2xl px-8 py-6 -m-4">
      <Header />

      {sortedClusters.length > 0 ? (
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
          {sortedClusters.map((cluster, i) => (
            <ClusterCard key={i} cluster={cluster} />
          ))}
        </div>
      ) : (
        <div className="p-6 text-center text-sm text-secondary bg-surface rounded-xl">
          No saved board yet. Start one by sharing what's on your mind in the chat.
        </div>
      )}

      {/* Save button at bottom right */}
      <div className="flex justify-end items-center gap-3 mt-8 mr-4">
        {showSaved && (
          <span className="flex items-center gap-1 text-xs text-success font-medium">
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z" />
            </svg>
            Saved
          </span>
        )}
        <Button
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
      />
    </div>
  )
}

export default App
