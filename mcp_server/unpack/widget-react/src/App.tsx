import { useState, useEffect, useCallback } from 'react'
import { Button } from '@openai/apps-sdk-ui/components/Button'
import { Check } from '@openai/apps-sdk-ui/components/Icon'
import type { UnpackData } from './types'
import { getToolOutput, copyToClipboard } from './utils'
import { Header } from './components/Header'
import { ClusterCard } from './components/ClusterCard'

function App() {
  const [data, setData] = useState<UnpackData | null>(null)
  const [isInitialized, setIsInitialized] = useState(false)
  const [copied, setCopied] = useState(false)

  const notifyHeight = useCallback(() => {
    requestAnimationFrame(() => {
      window.openai?.notifyIntrinsicHeight?.()
    })
  }, [])

  const loadData = useCallback(() => {
    const output = getToolOutput()
    if (output) {
      setData(output)
      setIsInitialized(true)
      notifyHeight()
    }
  }, [notifyHeight])

  useEffect(() => {
    loadData()
    window.addEventListener('openai:set_globals', loadData, { passive: true })
    return () => window.removeEventListener('openai:set_globals', loadData)
  }, [loadData])

  const handleCopy = async () => {
    if (!data?.summary_markdown) return
    const success = await copyToClipboard(data.summary_markdown)
    if (success) {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  if (!isInitialized || !data) {
    return (
      <div className="p-6 text-center text-sm text-secondary bg-surface-secondary rounded-xl">
        Loading...
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
        <div className="mt-4 p-4 bg-surface rounded-xl border border-default">
          <h3 className="text-sm font-semibold text-default mb-2">Other Questions</h3>
          <div className="space-y-2">
            {data.unclustered.map((q, i) => (
              <div
                key={i}
                className="text-sm text-secondary pl-3 border-l-2 border-default"
              >
                {q}
              </div>
            ))}
          </div>
          <p className="text-xs text-secondary italic mt-2">
            These questions didn't fit a clear theme.
          </p>
        </div>
      )}

      {/* Copy Summary Button */}
      <div className="sticky bottom-0 pt-4 pb-2 bg-surface-secondary">
        <div className="flex items-center gap-3">
          <Button
            color="primary"
            variant="outline"
            onClick={handleCopy}
            aria-label="Copy summary to clipboard"
          >
            {copied ? 'Copied!' : 'Copy Summary'}
          </Button>
          {copied && (
            <span className="flex items-center gap-1 text-xs text-success">
              <Check className="w-3.5 h-3.5" aria-hidden="true" />
            </span>
          )}
        </div>
      </div>
    </main>
  )
}

export default App
