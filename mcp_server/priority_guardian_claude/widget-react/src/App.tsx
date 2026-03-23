import { useState, useEffect, useCallback } from 'react'
import { useApp, useHostStyles, App, McpUiToolResultNotification } from '@modelcontextprotocol/ext-apps/react'

import type { Priority, DashboardData, CalendarKeyword } from './types'
import { sortPrioritiesByKeyword } from './utils'
import { setLocale, t } from './i18n'
import { DeadlineCard } from './components/DeadlineCard'
import { FlexibleCard } from './components/FlexibleCard'
import { TimeAllocationBar } from './components/TimeAllocationBar'

/**
 * Priority Guardian Dashboard - Claude Widget
 *
 * Display-only widget for Claude MCP Apps.
 * Uses useApp hook to receive tool result data via app.ontoolresult.
 * Uses useHostStyles to inject Claude theme CSS variables.
 *
 * No CRUD operations - all data is read-only.
 */
function App() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [isInitialized, setIsInitialized] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  // MCP Apps bridge: useApp hook to receive tool results
  // onAppCreated callback fires once app object is ready
  const { app } = useApp({
    appInfo: { name: 'Priority Guardian', version: '1.0.0' },
    capabilities: {},
    onAppCreated: useCallback((appInstance: App) => {
      // Register handler for incoming tool results
      appInstance.ontoolresult = (result: McpUiToolResultNotification['params']) => {
        try {
          // Extract data from result.structuredContent.data (MCP Apps pattern)
          const structuredContent = result?.structuredContent
          if (structuredContent?.data) {
            const dashboardData = structuredContent.data as DashboardData

            // Set locale from data if present (i18n)
            if (dashboardData.locale) {
              setLocale(dashboardData.locale)
            }

            setData(dashboardData)
            setLoadError(null)
            setIsInitialized(true)
          }
        } catch (err) {
          console.error('PG Claude widget: Error processing tool result:', err)
          setLoadError('Failed to load dashboard data.')
          setIsInitialized(true)
        }
      }
    }, []),
  })

  // Inject host theme CSS variables
  useHostStyles(app)

  // Sync locale on data changes
  useEffect(() => {
    if (data?.locale) {
      setLocale(data.locale)
    }
  }, [data?.locale])

  // Loading state
  if (!isInitialized) {
    return (
      <div style={{
        padding: '24px',
        textAlign: 'center',
        fontSize: '14px',
        color: 'var(--color-text-secondary, #5c5c5c)',
        background: 'var(--color-background-secondary, #f9f9f9)',
        borderRadius: '12px',
      }}>
        {t('loading')}
      </div>
    )
  }

  // Error state
  if (loadError) {
    return (
      <div style={{
        marginBottom: '16px',
        padding: '12px',
        fontSize: '14px',
        color: 'var(--color-text-danger, #dc2626)',
        background: 'var(--color-background-primary, #fff)',
        borderRadius: '8px',
        border: '1px solid var(--color-border-danger, #fecaca)',
      }} role="alert">
        {loadError}
      </div>
    )
  }

  // No data yet
  if (!data) {
    return (
      <div style={{
        padding: '24px',
        textAlign: 'center',
        background: 'var(--color-background-primary, #fff)',
        borderRadius: '12px',
        border: '1px solid var(--color-border, #e5e5e5)',
      }}>
        <p style={{ fontSize: '16px', fontWeight: 500, color: 'var(--color-text-primary, #0d0d0d)', marginBottom: '8px' }}>
          {t('noPriorities')}
        </p>
        <p style={{ fontSize: '14px', color: 'var(--color-text-secondary, #5c5c5c)' }}>
          {t('noPrioritiesHint')}
        </p>
      </div>
    )
  }

  // Dashboard View
  const priorities = data.priorities ?? []
  const activePriorities = priorities.filter(p => p.status === 'active')
  const sortedPriorities = sortPrioritiesByKeyword(activePriorities)

  // Extract active keywords for TimeAllocationBar legend
  const activeKeywords: CalendarKeyword[] = []
  const keywordSet = new Set(activePriorities.map(p => p.calendarKeyword))
  if (keywordSet.has('P1')) activeKeywords.push('P1')
  if (keywordSet.has('P2')) activeKeywords.push('P2')
  if (keywordSet.has('P3')) activeKeywords.push('P3')

  return (
    <main
      role="main"
      aria-label="Priority Guardian Dashboard"
      style={{
        background: 'var(--color-background-secondary, #f9f9f9)',
        borderRadius: '16px',
        padding: '24px',
      }}
    >
      {/* Time Allocation Bar (shows calendar hours breakdown) */}
      {data.google_connected && (
        <TimeAllocationBar
          timeAllocation={data.timeAllocation}
          activeKeywords={activeKeywords}
        />
      )}

      {/* Priority Cards */}
      {sortedPriorities.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
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

interface PriorityCardProps {
  priority: Priority
}

function PriorityCard({ priority }: PriorityCardProps) {
  if (priority.type === 'deadline') {
    return <DeadlineCard priority={priority} defaultDeliverablesExpanded={false} />
  }
  return <FlexibleCard priority={priority} defaultGoalsExpanded={false} />
}

function EmptyState() {
  return (
    <div style={{
      padding: '24px',
      textAlign: 'center',
      background: 'var(--color-background-primary, #fff)',
      borderRadius: '12px',
      border: '1px solid var(--color-border, #e5e5e5)',
    }}>
      <p style={{ fontSize: '16px', fontWeight: 500, color: 'var(--color-text-primary, #0d0d0d)', marginBottom: '8px' }}>
        {t('noPriorities')}
      </p>
      <p style={{ fontSize: '14px', color: 'var(--color-text-secondary, #5c5c5c)' }}>
        {t('noPrioritiesHint')}
      </p>
    </div>
  )
}

export default App
