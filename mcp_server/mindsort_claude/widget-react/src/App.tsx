/**
 * MindSort Claude Widget - Inline Cluster Overview
 *
 * INLINE-ONLY: Shows cluster overview with priorities-first ordering.
 * Replaces the priority-only view with a per-cluster list that is valuable
 * even when no priorities are set.
 *
 * Design: inc_inline_card_cluster_overview.md
 * - Header: "Your MindSort AI Board" + count summary
 * - Rows: one per cluster (badge, name, tag icon, thought count)
 * - Ordering: prioritized first (P1→P2→P3), then by size descending
 * - Truncation: MAX_INLINE_ROWS with "+N more clusters"
 * - Action: "Open full board →" (callServerTool)
 *
 * Data path: ontoolresult -> structuredContent.clusters
 */
import { useState, useEffect, useCallback, useRef, useLayoutEffect } from 'react'
import {
  useApp,
  useHostStyles,
  App as McpApp,
  McpUiToolResultNotification,
} from '@modelcontextprotocol/ext-apps/react'

import type { Cluster } from './types'
import {
  getTotalThoughtCount,
  sortClustersForOverview,
  truncateClusters,
} from './utils'

/**
 * MAX_INLINE_ROWS: Maximum cluster rows before truncation.
 *
 * Measured to fit within 500px height budget:
 * - Header: ~44px (title + summary)
 * - Footer: ~56px (overflow line + button)
 * - Padding: 32px (16px top + bottom)
 * - Available: ~368px
 * - Row height: ~48px (single line, 44pt touch target)
 * - Max rows: floor(368/48) ≈ 7
 *
 * Using 5 for conservative margin at varying font sizes.
 * The briefing's starting estimate was ~5; measurement confirms this is safe.
 */
const MAX_INLINE_ROWS = 5

function App() {
  // Board data from tool results
  const [clusters, setClusters] = useState<Cluster[]>([])
  const [isInitialized, setIsInitialized] = useState(false)
  const [isLoadingBoard, setIsLoadingBoard] = useState(false)

  // Stale bridge detection
  const [isBridgeStale, setIsBridgeStale] = useState(false)

  // App reference for bridge connection
  const appRef = useRef<McpApp | null>(null)

  // Ref for height guard diagnostic (500px limit verification)
  const inlineMainRef = useRef<HTMLElement | null>(null)

  // MCP Apps bridge: useApp hook
  // CRITICAL: availableDisplayModes is ['inline'] ONLY - no fullscreen yet
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

  // Height guard diagnostic - verify inline card ≤500px
  // Runs after render when clusters change; logs violation for post-deploy verification
  useLayoutEffect(() => {
    if (!inlineMainRef.current || !isInitialized) return

    const height = inlineMainRef.current.scrollHeight
    const limit = 500

    // Always log for diagnostic visibility
    console.log(
      `[MindSort Diagnostic] Inline main scrollHeight: ${height}px` +
        (height > limit ? ` — EXCEEDS ${limit}px LIMIT` : '')
    )

    if (height > limit) {
      console.warn(
        `[MindSort Diagnostic] Height violation: ${height}px > ${limit}px. ` +
          `Reduce MAX_INLINE_ROWS or row height.`
      )
    }
  }, [isInitialized, clusters])

  // Handle "Open full board" button click
  const handleOpenFullBoard = useCallback(async () => {
    if (!appRef.current || isLoadingBoard) return

    setIsLoadingBoard(true)
    try {
      // Call load_saved_board to render the full board in conversation
      // This is a real action per PG-Claude's proven pattern
      await appRef.current.callServerTool({
        name: 'load_saved_board',
        arguments: {},
      })
    } catch (err) {
      console.error('MindSort widget: Error loading full board:', err)
    } finally {
      setIsLoadingBoard(false)
    }
  }, [isLoadingBoard])

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
          borderRadius: 'var(--border-radius-xl, 12px)',
        }}
      >
        <p style={{ marginBottom: '8px', fontWeight: 500 }}>
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
          borderRadius: 'var(--border-radius-xl, 12px)',
        }}
      >
        Loading...
      </div>
    )
  }

  // Sort and truncate clusters
  const sortedClusters = sortClustersForOverview(clusters)
  const { visible: visibleClusters, overflow } = truncateClusters(sortedClusters, MAX_INLINE_ROWS)
  const clusterCount = clusters.length
  const thoughtCount = getTotalThoughtCount(clusters)

  return (
    <main
      ref={inlineMainRef}
      role="main"
      aria-label="MindSort AI Board Overview"
      style={{
        width: '100%',
        background: 'var(--color-background-secondary, #F5F4ED)',
        borderRadius: 'var(--border-radius-xl, 12px)',
        padding: '16px',
        touchAction: 'pan-y',
        overscrollBehavior: 'contain',
      }}
    >
      {/* Header: Title + Count Summary */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          marginBottom: '12px',
        }}
      >
        <h2
          style={{
            fontSize: '14px',
            fontWeight: 500, // Guideline: two weights only (400, 500)
            color: 'var(--color-text-primary, #141413)',
            margin: 0,
          }}
        >
          Your MindSort AI Board
        </h2>
        <span
          style={{
            fontSize: '12px',
            color: 'var(--color-text-tertiary, #73726C)',
          }}
        >
          {clusterCount} cluster{clusterCount !== 1 ? 's' : ''} · {thoughtCount} thought{thoughtCount !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Cluster list */}
      {visibleClusters.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {visibleClusters.map((cluster, index) => (
            <ClusterRow key={`${cluster.cluster_name}-${index}`} cluster={cluster} />
          ))}
        </div>
      ) : (
        <p
          style={{
            fontSize: '13px',
            color: 'var(--color-text-tertiary, #73726C)',
            textAlign: 'center',
            padding: '16px 0',
          }}
        >
          No clusters yet. Start organizing your thoughts!
        </p>
      )}

      {/* Footer: Overflow count + Open full board button */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginTop: '12px',
        }}
      >
        {/* Overflow indicator */}
        <span
          style={{
            fontSize: '12px',
            color: 'var(--color-text-tertiary, #73726C)',
          }}
        >
          {overflow > 0 ? `+${overflow} more cluster${overflow !== 1 ? 's' : ''}` : ''}
        </span>

        {/* Open full board button */}
        <button
          type="button"
          onClick={handleOpenFullBoard}
          disabled={isLoadingBoard}
          style={{
            padding: '8px 12px',
            fontSize: '12px',
            fontWeight: 500,
            color: 'var(--color-text-info, #1E40AF)',
            background: 'transparent',
            border: 'none',
            borderRadius: 'var(--border-radius-md, 8px)',
            cursor: isLoadingBoard ? 'wait' : 'pointer',
            opacity: isLoadingBoard ? 0.6 : 1,
            minHeight: '44px', // Touch target
            minWidth: '44px',
          }}
          aria-label="Open full board in conversation"
        >
          {isLoadingBoard ? 'Loading...' : 'Open full board →'}
        </button>
      </div>
    </main>
  )
}

/**
 * Single cluster row: badge (if prioritized) + name + tag icon + thought count
 *
 * - Prioritized clusters get a left-accent border in the rank color
 * - Tag icon (muted) shown when cluster has tags
 * - Single-line layout with ellipsis truncation
 */
function ClusterRow({ cluster }: { cluster: Cluster }) {
  const hasPriority = !!cluster.priority?.rank
  const rank = cluster.priority?.rank
  const hasTags = (cluster.tags?.length ?? 0) > 0

  // Rank colors matching PG-Claude and compliance master token reference
  const rankColors: Record<string, { bg: string; text: string; border: string }> = {
    P1: {
      bg: 'var(--color-background-danger, #F7ECEC)',
      text: 'var(--color-text-danger, #7F2C28)',
      border: 'var(--color-border-danger, #A73D39)',
    },
    P2: {
      bg: 'var(--color-background-warning, #F6EEDF)',
      text: 'var(--color-text-warning, #5A4815)',
      border: 'var(--color-border-warning, #805C1F)',
    },
    P3: {
      bg: 'var(--color-background-info, #D6E4F6)',
      text: 'var(--color-text-info, #3266AD)',
      border: 'var(--color-border-info, #4682D5)',
    },
  }
  const colors = rank ? rankColors[rank] : null

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        background: 'var(--color-background-primary, #FFFFFF)',
        borderRadius: 'var(--border-radius-md, 8px)',
        padding: '10px 12px',
        border: `var(--border-width-regular, 0.5px) solid var(--color-border-tertiary, rgba(31,30,29,0.15))`,
        // Left accent border for prioritized clusters
        borderLeft: hasPriority && colors
          ? `3px solid ${colors.border}`
          : `var(--border-width-regular, 0.5px) solid var(--color-border-tertiary, rgba(31,30,29,0.15))`,
        minHeight: '44px', // Touch target compliance
      }}
    >
      {/* Priority badge (only if prioritized) */}
      {hasPriority && rank && colors && (
        <span
          style={{
            fontSize: '11px',
            fontWeight: 500, // Guideline: two weights only (400, 500)
            padding: '2px 6px',
            borderRadius: '4px',
            background: colors.bg,
            color: colors.text,
            flexShrink: 0,
          }}
        >
          {rank}
        </span>
      )}

      {/* Cluster name - fills available space, single line with ellipsis */}
      <span
        style={{
          flex: 1,
          fontSize: '13px',
          fontWeight: 500,
          color: 'var(--color-text-primary, #141413)',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          minWidth: 0, // Required for text-overflow in flex child
        }}
      >
        {cluster.cluster_name}
      </span>

      {/* Tag indicator (monochrome outlined icon, not emoji) */}
      {hasTags && (
        <span
          aria-label="has action tags"
          title="Has action tags"
          style={{
            display: 'flex',
            alignItems: 'center',
            color: 'var(--color-text-tertiary, #73726C)',
            flexShrink: 0,
          }}
        >
          {/* Outlined tag icon - stroke="currentColor" inherits muted color */}
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            {/* Tag shape: angled rectangle with circle */}
            <path d="M12 2H2v10l9.29 9.29a1 1 0 0 0 1.42 0l6.58-6.58a1 1 0 0 0 0-1.42L12 2Z" />
            <circle cx="7" cy="7" r="1.5" fill="currentColor" stroke="none" />
          </svg>
        </span>
      )}

      {/* Thought count */}
      <span
        style={{
          fontSize: '12px',
          color: 'var(--color-text-tertiary, #73726C)',
          flexShrink: 0,
          whiteSpace: 'nowrap',
        }}
      >
        {cluster.sum_thought_items ?? 0} thought{(cluster.sum_thought_items ?? 0) !== 1 ? 's' : ''}
      </span>
    </div>
  )
}

export default App
