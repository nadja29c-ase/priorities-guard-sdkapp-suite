import { useState, useEffect, useCallback } from 'react'
import type { UnpackData } from './types'
import { getToolOutput } from './utils'
import { Header } from './components/Header'
import { ClusterCard } from './components/ClusterCard'

function App() {
  const [data, setData] = useState<UnpackData | null>(null)
  const [isInitialized, setIsInitialized] = useState(false)

  const notifyHeight = useCallback(() => {
    requestAnimationFrame(() => {
      window.openai?.notifyIntrinsicHeight?.()
    })
  }, [])

  const loadData = useCallback(() => {
    const output = getToolOutput()
    setIsInitialized(true)
    if (output) {
      setData(output)
    }
    notifyHeight()
  }, [notifyHeight])

  useEffect(() => {
    loadData()
    window.addEventListener('openai:set_globals', loadData, { passive: true })
    return () => window.removeEventListener('openai:set_globals', loadData)
  }, [loadData])

  if (!isInitialized) {
    return (
      <div className="p-6 text-center text-sm text-secondary bg-surface-secondary rounded-xl">
        Loading...
      </div>
    )
  }

  if (!data) {
    return (
      <div className="p-6 text-center text-sm text-secondary bg-surface-secondary rounded-xl">
        Unable to load summary.
      </div>
    )
  }

  return (
    <main
      role="main"
      aria-label="Unpack Summary"
      className="bg-surface-secondary rounded-2xl px-8 py-6 -m-4"
    >
      <Header problemStatement={data.problem_statement} />

      {/* Cluster Cards */}
      {data.clusters.length > 0 ? (
        <div className="grid gap-4 grid-cols-[repeat(auto-fit,minmax(240px,1fr))]">
          {data.clusters.map((cluster) => (
            <ClusterCard key={cluster.id} cluster={cluster} />
          ))}
        </div>
      ) : (
        <div className="p-6 text-center text-sm text-secondary bg-surface rounded-xl">
          No clusters to display.
        </div>
      )}

      {/* Unclustered Questions */}
      {data.unclustered.length > 0 && (
        <div className="mt-4 p-5 bg-surface-secondary rounded-2xl border border-default shadow-lg">
          <h3 className="text-sm font-semibold text-default mb-3">Other Questions</h3>
          <div className="space-y-2">
            {data.unclustered.map((q, i) => (
              <div
                key={i}
                className="text-sm text-default pl-3 border-l-2 border-default"
              >
                {q}
              </div>
            ))}
          </div>
        </div>
      )}
    </main>
  )
}

export default App
