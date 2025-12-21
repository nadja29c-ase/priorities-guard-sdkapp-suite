import { useState, useEffect, useRef, useCallback } from 'react'
import { useDocumentTheme } from '@openai/apps-sdk-ui/theme'
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

    const data = getToolOutput()
    if (data.length > 0) {
      setClusters(data)
      setIsInitialized(true)
      isInitializedRef.current = true
    }
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
    <>
      <Header
        canSave={clusters.length > 0}
        showSaved={showSaved}
        onSaveClick={() => setIsModalOpen(true)}
      />

      {sortedClusters.length > 0 ? (
        <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
          {sortedClusters.map((cluster, i) => (
            <ClusterCard key={i} cluster={cluster} />
          ))}
        </div>
      ) : (
        <div className="p-6 text-center text-sm text-secondary bg-surface-secondary rounded-xl">
          No clusters to display
        </div>
      )}

      <SaveModal
        isOpen={isModalOpen}
        onCancel={() => setIsModalOpen(false)}
        onConfirm={handleSave}
        isSaving={isSaving}
      />
    </>
  )
}

export default App
