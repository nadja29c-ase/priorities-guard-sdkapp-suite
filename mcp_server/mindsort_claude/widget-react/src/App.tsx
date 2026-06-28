/**
 * MindSort Claude Widget - Inline Priority Summary
 *
 * INLINE-ONLY: No fullscreen, no CRUD, no display mode switching.
 * Shows own-level priorities with breadcrumbs and count line.
 *
 * Data path: ontoolresult -> structuredContent.clusters
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import {
  useApp,
  useHostStyles,
  App as McpApp,
  McpUiToolResultNotification,
} from '@modelcontextprotocol/ext-apps/react'

import type { Cluster, PrioritizedEntity } from './types'
import { extractOwnLevelPriorities, getTotalThoughtCount, truncateText } from './utils'

function App() {
  // Board data from tool results
  const [clusters, setClusters] = useState<Cluster[]>([])
  const [isInitialized, setIsInitialized] = useState(false)

  // Stale bridge detection
  const [isBridgeStale, setIsBridgeStale] = useState(false)

  // App reference for bridge connection
  const appRef = useRef<McpApp | null>(null)

  // MCP Apps bridge: useApp hook
  // CRITICAL: availableDisplayModes is ['inline'] ONLY - no fullscreen
  const { app } = useApp({
    appInfo: { name: 'MindSort', version: '1.0.0' },
    capabilities: {
      availableDisplayModes: ['inline'],
    },
    onAppCreated: useCallback((appInstance: McpApp) => {
      appRef.current = appInstance

      // Register handler for incoming tool results
      appInstance.ontoolresult = (result: McpUiToolResultNotification['params']) => {
        try {
          // MindSort uses structuredContent.clusters (not .data)
          const resultClusters = result?.structuredContent?.clusters
          if (Array.isArray(resultClusters)) {
            // Validate clusters have required structure
            const validClusters = resultClusters.filter(
              (c): c is Cluster =>
                c !== null && typeof c === 'object' && 'cluster_name' in c
            )
            setClusters(validClusters)
            setIsInitialized(true)
          }
        } catch (err) {
          console.error('MindSort widget: Error processing tool result:', err)
          setIsInitialized(true)
        }
      }
    }, []),
  })

  // Inject host theme CSS variables (must pass hostContext for dark mode)
  useHostStyles(app, app?.getHostContext())

  // Stale bridge detection - if onAppCreated hasn't fired within 3s
  useEffect(() => {
    const timeout = setTimeout(() => {
      if (!appRef.current) {
        setIsBridgeStale(true)
      }
    }, 3000)
    return () => clearTimeout(timeout)
  }, [])

  // Stale session overlay - MUST be checked BEFORE loading state.
  // If the bridge never connects, isInitialized stays false forever,
  // but we still need to show the stale overlay after 3s timeout.
  if (isBridgeStale) {
    return (
      <div
        style={{
          padding: '24px',
          textAlign: 'center',
          color: 'var(--color-text-secondary, #3D3D3A)',
          fontSize: '12px',
          lineHeight: '1.5',
          background: 'var(--color-background-secondary, #F5F4ED)',
          borderRadius: '12px',
        }}
      >
        <p style={{ marginBottom: '8px', fontWeight: 600 }}>
          Session expired
        </p>
        <p style={{ margin: 0 }}>
          Ask again to see your current board.
        </p>
      </div>
    )
  }

  // Loading state - checked AFTER stale, so stale wins if bridge never connects
  if (!isInitialized) {
    return (
      <div
        style={{
          padding: '24px',
          textAlign: 'center',
          fontSize: '14px',
          color: 'var(--color-text-secondary, #3D3D3A)',
          background: 'var(--color-background-secondary, #F5F4ED)',
          borderRadius: '12px',
        }}
      >
        Loading...
      </div>
    )
  }

  // Extract own-level priorities (sorted P1 -> P2 -> P3)
  const priorities = extractOwnLevelPriorities(clusters)
  const clusterCount = clusters.length
  const thoughtCount = getTotalThoughtCount(clusters)

  return (
    <main
      role="main"
      aria-label="MindSort Priority Summary"
      style={{
        width: '100%',
        background: 'var(--color-background-secondary, #F5F4ED)',
        borderRadius: '16px',
        padding: '16px',
        touchAction: 'pan-y',
        overscrollBehavior: 'contain',
      }}
    >
      {/* Header */}
      <h2
        style={{
          fontSize: '14px',
          fontWeight: 600,
          color: 'var(--color-text-primary, #141413)',
          marginBottom: '12px',
        }}
      >
        Priorities
      </h2>

      {/* Priority list or empty state */}
      {priorities.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {priorities.map((entity, index) => (
            <PriorityRow key={`${entity.rank}-${index}`} entity={entity} />
          ))}
        </div>
      ) : null}

      {/* Count line */}
      <p
        style={{
          fontSize: '12px',
          color: 'var(--color-text-tertiary, #73726C)',
          marginTop: '12px',
        }}
      >
        {clusterCount} cluster{clusterCount !== 1 ? 's' : ''} &middot;{' '}
        {thoughtCount} thought{thoughtCount !== 1 ? 's' : ''}
        {priorities.length === 0 && ' \u00B7 none prioritized yet'}
      </p>
    </main>
  )
}

/**
 * Single priority row: rank badge + entity text + breadcrumb
 */
function PriorityRow({ entity }: { entity: PrioritizedEntity }) {
  const rankColors: Record<string, { bg: string; text: string }> = {
    P1: { bg: 'var(--color-background-danger, #FEE2E2)', text: 'var(--color-text-danger, #991B1B)' },
    P2: { bg: 'var(--color-background-warning, #FEF3C7)', text: 'var(--color-text-warning, #92400E)' },
    P3: { bg: 'var(--color-background-info, #DBEAFE)', text: 'var(--color-text-info, #1E40AF)' },
  }
  const colors = rankColors[entity.rank] ?? rankColors.P3

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '8px',
        background: 'var(--color-background-primary, #FFFFFF)',
        borderRadius: '8px',
        padding: '10px 12px',
        border: '1px solid var(--color-border-primary, rgba(31,30,29,0.1))',
      }}
    >
      {/* Rank badge */}
      <span
        style={{
          fontSize: '11px',
          fontWeight: 600,
          padding: '2px 6px',
          borderRadius: '4px',
          background: colors.bg,
          color: colors.text,
          flexShrink: 0,
        }}
      >
        {entity.rank}
      </span>

      {/* Entity text + breadcrumb */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <p
          style={{
            fontSize: '13px',
            fontWeight: 500,
            color: 'var(--color-text-primary, #141413)',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {truncateText(entity.text, 60)}
        </p>

        {/* Breadcrumb (only for subclusters and thought items) */}
        {entity.breadcrumb && (
          <p
            style={{
              fontSize: '11px',
              color: 'var(--color-text-tertiary, #73726C)',
              marginTop: '2px',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {truncateText(entity.breadcrumb, 50)}
          </p>
        )}
      </div>
    </div>
  )
}

export default App
