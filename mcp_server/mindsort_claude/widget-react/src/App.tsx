/**
 * MindSort Claude Widget - Cluster Overview with Inline Accordion + Fullscreen
 *
 * COMPLIANCE: This uses permitted in-place expand/collapse behavior (explicitly
 * listed under "Handle within your app" in the design guidelines) and does NOT
 * introduce navigation, breadcrumbs, nested views, or internal scrolling.
 *
 * DISPLAY MODES:
 * - Inline: Accordion expansion within 500px height limit (increment 1)
 * - Fullscreen: Full board view with all content expanded (increment 2)
 *
 * Host context is authoritative — local displayMode state only ever reconciles
 * toward host context. Host decides mode availability; widget adapts.
 *
 * Design: inc_inline_accordion_bounded.md (inline), inc_fullscreen_full_board_readonly.md (fullscreen)
 *
 * Data path: ontoolresult -> structuredContent.clusters
 */
import { useState, useEffect, useCallback, useRef, useLayoutEffect, useMemo } from 'react'
import {
  useApp,
  useHostStyles,
  App as McpApp,
  McpUiToolResultNotification,
} from '@modelcontextprotocol/ext-apps/react'

import type { Cluster, Subcluster, Rank } from './types'
import {
  getTotalThoughtCount,
  sortClustersForOverview,
  truncateClusters,
  normalizeThoughtItem,
  rankToNumber,
} from './utils'

// =============================================================================
// DISPLAY MODE TYPES
// =============================================================================

type DisplayMode = 'inline' | 'fullscreen'

interface HostContextState {
  displayMode: DisplayMode
  availableDisplayModes: DisplayMode[]
  safeAreaInsets: { top: number; bottom: number; left: number; right: number }
  platform: string | null
}

// =============================================================================
// LAYOUT MODEL CONSTANTS
// =============================================================================
// These are explicit CSS dimensions verified against the real Claude host.
// Every visible element belongs to exactly one term. No element is unaccounted.
//
// Heights are bounded (fixed height or max-height + 1-line clamp), not assumed.
// Post-deploy: verify via [MindSort Diagnostic] console logs.

export const LAYOUT = {
  /** Card padding: 16px top + 16px bottom */
  outerPadding: 32,
  /** Board header: "Your MindSort AI Board" + counts line */
  boardHeaderHeight: 44,
  /** Collapsed cluster row height (44px touch target + padding) */
  collapsedRowH: 48,
  /** Gap between collapsed rows */
  collapsedRowGap: 6,
  /** Expanded detail row height (1-line clamped content) */
  detailRowH: 36,
  /** Gap between detail rows */
  detailRowGap: 4,
  /** Gap between expanded detail and next collapsed row */
  sectionGap: 8,
  /** Overflow action row: "View remaining cluster content" (touch target) */
  overflowActionRowH: 44,
  /** Board-level overflow row: "+N more clusters" text height */
  boardOverflowRowH: 20,
  /** Footer: "Open full board" button area */
  actionFooterHeight: 56,
  /** Safety margin: target ≤480px to give host variance headroom */
  safetyMargin: 20,
  /** Maximum height limit per guidelines */
  maxHeight: 500,
  /** Target threshold (maxHeight - safetyMargin) */
  targetThreshold: 480,
} as const

/**
 * MAX_INLINE_ROWS: Maximum collapsed cluster rows before truncation.
 * Used when NO cluster is expanded.
 */
const MAX_INLINE_ROWS = 5

/**
 * MAX_INLINE_ROWS_EXPANDED: Maximum collapsed cluster rows when one is expanded.
 * Reduced to make room for expanded detail content.
 */
const MAX_INLINE_ROWS_EXPANDED = 3

// =============================================================================
// LAYOUT MODEL HELPERS (exported for unit testing)
// =============================================================================

/**
 * Represents a single unit of expanded detail content.
 * Used for deterministic capacity computation and rendering.
 */
export interface DetailUnit {
  type: 'summary' | 'thought' | 'subcluster'
  text: string
  priority?: { rank: 'P1' | 'P2' | 'P3' }
  /** For subclusters: thought count */
  count?: number
}

/**
 * Compute the final detail capacity for expanded cluster content.
 *
 * Uses the deterministic layout model with explicit terms.
 * Reserves overflow row height BEFORE computing final capacity.
 *
 * @param visibleCollapsedRows - Number of visible collapsed cluster rows
 * @param hasBoardOverflow - Whether "+N more clusters" is shown
 * @param totalContentUnits - Total units the expanded cluster has
 * @returns finalDetailCapacity (may be 0 for zero-capacity fallback)
 */
export function computeDetailCapacity(
  visibleCollapsedRows: number,
  hasBoardOverflow: boolean,
  totalContentUnits: number
): number {
  // Account for all fixed elements
  let fixed =
    LAYOUT.outerPadding +
    LAYOUT.boardHeaderHeight +
    LAYOUT.actionFooterHeight +
    LAYOUT.safetyMargin

  // Collapsed rows (including the expanded cluster's own header row)
  // Each row + gap, minus one gap for the last row
  const collapsedRowsTotal =
    visibleCollapsedRows * LAYOUT.collapsedRowH +
    Math.max(0, visibleCollapsedRows - 1) * LAYOUT.collapsedRowGap

  fixed += collapsedRowsTotal

  // Board-level overflow ("+N more clusters")
  if (hasBoardOverflow) {
    fixed += LAYOUT.boardOverflowRowH
  }

  // Section gap between expanded detail and rest
  fixed += LAYOUT.sectionGap

  // Available space for detail content
  let available = LAYOUT.targetThreshold - fixed

  // Provisional capacity (before overflow row reservation)
  const detailRowWithGap = LAYOUT.detailRowH + LAYOUT.detailRowGap
  const provisionalCapacity = Math.floor(available / detailRowWithGap)

  // If content exceeds provisional capacity, reserve overflow row height + gap before it
  if (totalContentUnits > provisionalCapacity) {
    // Reserve: overflowActionRowH + detailRowGap (gap between last detail row and overflow button)
    available -= LAYOUT.overflowActionRowH + LAYOUT.detailRowGap
    const finalCapacity = Math.floor(available / detailRowWithGap)
    return Math.max(0, finalCapacity)
  }

  return Math.max(0, provisionalCapacity)
}

/**
 * Extract detail units from a cluster in OpenAI order:
 * (1) summary → (2) thought items → (3) subclusters
 *
 * Thoughts are priority-sorted (P1 → P2 → P3 → unprioritized).
 * Subclusters are shown as named rows with count, NOT nested cards.
 * NO tag pills (tags are indicator-only on collapsed row).
 */
export function extractDetailUnits(cluster: Cluster): DetailUnit[] {
  const units: DetailUnit[] = []

  // (1) Summary - 1 unit if present
  if (cluster.summary) {
    units.push({ type: 'summary', text: cluster.summary })
  }

  // (2) Thought items - priority-sorted
  const thoughts = (cluster.thought_items ?? []).map(normalizeThoughtItem)
  const sortedThoughts = [...thoughts].sort((a, b) => {
    return rankToNumber(a.priority?.rank) - rankToNumber(b.priority?.rank)
  })
  for (const thought of sortedThoughts) {
    units.push({
      type: 'thought',
      text: thought.text,
      priority: thought.priority,
    })
  }

  // (3) Subclusters - as named rows with count, NOT nested
  const subclusters = cluster.subclusters ?? []
  for (const sub of subclusters) {
    units.push({
      type: 'subcluster',
      text: sub.subcluster_name,
      count: sub.sum_thought_items,
      priority: sub.priority,
    })
  }

  return units
}

// =============================================================================
// PERFORMANCE CONSTANTS
// =============================================================================
// Fullscreen scale target: must remain responsive for boards up to this size.
// Beyond this, virtualization kicks in.
const FULLSCREEN_SCALE_TARGET = {
  maxClusters: 30,
  maxThoughts: 300,
  maxSubclusters: 60,
} as const

// =============================================================================
// MAIN APP COMPONENT
// =============================================================================

function App() {
  // Board data from tool results
  const [clusters, setClusters] = useState<Cluster[]>([])
  const [isInitialized, setIsInitialized] = useState(false)
  const [isLoadingBoard, setIsLoadingBoard] = useState(false)

  // Accordion state: only ONE cluster expanded at a time (inline mode)
  const [expandedClusterId, setExpandedClusterId] = useState<string | null>(null)

  // ResizeObserver guard: current detail count for the expanded cluster
  // Used for monotonic decrement when host renders larger than expected
  const [guardedDetailCount, setGuardedDetailCount] = useState<number | null>(null)

  // Stale bridge detection
  const [isBridgeStale, setIsBridgeStale] = useState(false)

  // ==========================================================================
  // DISPLAY MODE STATE
  // ==========================================================================
  // Host context is authoritative; local state only reconciles toward it.
  const [displayMode, setDisplayMode] = useState<DisplayMode>('inline')
  const [hostFullscreen, setHostFullscreen] = useState(false)
  const [hostContext, setHostContext] = useState<HostContextState>({
    displayMode: 'inline',
    availableDisplayModes: [],
    safeAreaInsets: { top: 0, bottom: 0, left: 0, right: 0 },
    platform: null,
  })

  // App reference for bridge connection
  const appRef = useRef<McpApp | null>(null)

  // Ref for height guard diagnostic (500px limit verification)
  const inlineMainRef = useRef<HTMLElement | null>(null)

  // Ref for focus restoration on fullscreen exit
  const fullscreenOpenerRef = useRef<HTMLButtonElement | null>(null)

  // Helper to check if fullscreen is available from host
  const isFullscreenAvailable = hostContext.availableDisplayModes.includes('fullscreen')

  // MCP Apps bridge: useApp hook
  // Declares support for both inline AND fullscreen; host decides availability
  const { app } = useApp({
    appInfo: { name: 'MindSort', version: '1.0.0' },
    capabilities: {
      availableDisplayModes: ['inline', 'fullscreen'],
    },
    onAppCreated: useCallback((appInstance: McpApp) => {
      appRef.current = appInstance

      // Read initial host context for display mode sync
      const ctx = appInstance.getHostContext?.()
      if (ctx) {
        const initialMode: DisplayMode = ctx.displayMode === 'fullscreen' ? 'fullscreen' : 'inline'
        setDisplayMode(initialMode)
        if (initialMode === 'fullscreen') {
          setHostFullscreen(true)
        }
        setHostContext({
          displayMode: initialMode,
          availableDisplayModes: (ctx.availableDisplayModes as DisplayMode[]) ?? [],
          safeAreaInsets: ctx.safeAreaInsets ?? { top: 0, bottom: 0, left: 0, right: 0 },
          platform: ctx.platform ?? null,
        })
      }

      // Register handler for host context changes (mode transitions, safe area, etc.)
      appInstance.onhostcontextchanged = (ctx) => {
        if (ctx.displayMode !== undefined) {
          const newMode: DisplayMode = ctx.displayMode === 'fullscreen' ? 'fullscreen' : 'inline'
          setDisplayMode(newMode)
          if (newMode === 'inline') {
            setHostFullscreen(false)
            // Focus restoration: return focus to the opener button
            if (fullscreenOpenerRef.current) {
              fullscreenOpenerRef.current.focus()
            }
          }
        }
        if (ctx.availableDisplayModes !== undefined) {
          setHostContext((prev) => ({
            ...prev,
            availableDisplayModes: ctx.availableDisplayModes as DisplayMode[],
          }))
        }
        if (ctx.safeAreaInsets !== undefined) {
          setHostContext((prev) => ({
            ...prev,
            safeAreaInsets: ctx.safeAreaInsets as HostContextState['safeAreaInsets'],
          }))
        }
        if (ctx.platform !== undefined) {
          setHostContext((prev) => ({
            ...prev,
            platform: ctx.platform as string | null,
          }))
        }
      }

      // Register handler for incoming tool results
      appInstance.ontoolresult = (result: McpUiToolResultNotification['params']) => {
        try {
          // MindSort uses structuredContent.clusters (not .data)
          const resultClusters = result?.structuredContent?.clusters
          if (Array.isArray(resultClusters)) {
            // Validate clusters have required structure (strict type guard)
            // Must validate actual types, not just property existence, to prevent
            // runtime crashes on malformed data (e.g., cluster_name: null)
            const validClusters = resultClusters.filter(
              (c): c is Cluster =>
                c !== null &&
                typeof c === 'object' &&
                typeof (c as Record<string, unknown>).cluster_name === 'string' &&
                typeof (c as Record<string, unknown>).sum_thought_items === 'number'
            )
            setClusters(validClusters)
            setIsInitialized(true)
            // Reset accordion state on new data
            setExpandedClusterId(null)
            setGuardedDetailCount(null)
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

  // Sort and truncate clusters - memoized for performance
  const sortedClusters = useMemo(
    () => sortClustersForOverview(clusters),
    [clusters]
  )

  // Determine max rows based on accordion state
  // When expanded, we need to ensure the expanded cluster stays visible
  const maxRows = expandedClusterId ? MAX_INLINE_ROWS_EXPANDED : MAX_INLINE_ROWS

  // Compute visible clusters, ensuring expanded cluster is always included
  // BUG FIX: Without this, clicking cluster 4 or 5 (visible when collapsed)
  // would make it disappear when maxRows shrinks from 5 to 3
  const { visibleClusters, boardOverflow, expandedCluster } = useMemo(() => {
    if (!expandedClusterId) {
      // Not expanded: normal truncation
      const { visible, overflow } = truncateClusters(sortedClusters, maxRows)
      return { visibleClusters: visible, boardOverflow: overflow, expandedCluster: null }
    }

    // Find the expanded cluster in the full sorted list
    const expanded = sortedClusters.find((c) => c.cluster_name === expandedClusterId) ?? null

    if (!expanded) {
      // Expanded cluster no longer exists (data changed) - fall back to normal truncation
      const { visible, overflow } = truncateClusters(sortedClusters, maxRows)
      return { visibleClusters: visible, boardOverflow: overflow, expandedCluster: null }
    }

    // Build visible list: expanded cluster first, then fill remaining slots
    const expandedIndex = sortedClusters.indexOf(expanded)
    const otherClusters = sortedClusters.filter((_, i) => i !== expandedIndex)
    const remainingSlots = maxRows - 1 // Reserve 1 slot for expanded cluster
    const visibleOthers = otherClusters.slice(0, remainingSlots)

    // Final visible list: expanded cluster in its original position
    // (or at the end if it was beyond the truncation point)
    const visible = [...visibleOthers]
    const insertIndex = Math.min(expandedIndex, visible.length)
    visible.splice(insertIndex, 0, expanded)

    const overflow = sortedClusters.length - visible.length

    return { visibleClusters: visible, boardOverflow: overflow, expandedCluster: expanded }
  }, [sortedClusters, maxRows, expandedClusterId])

  // Compute detail units and capacity for expanded cluster
  const detailUnits = useMemo(
    () => (expandedCluster ? extractDetailUnits(expandedCluster) : []),
    [expandedCluster]
  )

  const computedCapacity = useMemo(() => {
    if (!expandedCluster) return 0
    return computeDetailCapacity(
      visibleClusters.length,
      boardOverflow > 0,
      detailUnits.length
    )
  }, [expandedCluster, visibleClusters.length, boardOverflow, detailUnits.length])

  // Final detail capacity: use guarded count if set (for ResizeObserver decrement),
  // otherwise use computed capacity
  const finalDetailCapacity =
    guardedDetailCount !== null
      ? Math.min(guardedDetailCount, computedCapacity)
      : computedCapacity

  // Visible detail units and overflow count
  const visibleDetailUnits = detailUnits.slice(0, finalDetailCapacity)
  const hiddenDetailUnits = detailUnits.slice(finalDetailCapacity)
  // N = hidden THOUGHT items + hidden SUBCLUSTERS (summary omission not counted)
  const overflowCount = hiddenDetailUnits.filter(
    (u) => u.type === 'thought' || u.type === 'subcluster'
  ).length
  const hasDetailOverflow = overflowCount > 0 || finalDetailCapacity === 0

  // Reset guarded count when cluster changes or collapses
  useEffect(() => {
    setGuardedDetailCount(null)
  }, [expandedClusterId])

  // ==========================================================================
  // ResizeObserver GUARD - monotonic decrement, strict termination
  // ==========================================================================
  // Primary layout is bounded by deterministic limits.
  // This guard handles host-rendering variance (fonts, accessibility text scaling).
  //
  // CRITICAL: Use refs for state values to avoid effect recreation cascade.
  // If deps included finalDetailCapacity/guardedDetailCount, each decrement would
  // recreate the observer, which fires on .observe(), causing a cascade that
  // over-strips detail rows on first paint.
  const expandedClusterIdRef = useRef(expandedClusterId)
  const finalDetailCapacityRef = useRef(finalDetailCapacity)
  const guardedDetailCountRef = useRef(guardedDetailCount)

  // Keep refs in sync
  useEffect(() => {
    expandedClusterIdRef.current = expandedClusterId
  }, [expandedClusterId])
  useEffect(() => {
    finalDetailCapacityRef.current = finalDetailCapacity
  }, [finalDetailCapacity])
  useEffect(() => {
    guardedDetailCountRef.current = guardedDetailCount
  }, [guardedDetailCount])

  useLayoutEffect(() => {
    if (!inlineMainRef.current || !isInitialized) return

    const target = LAYOUT.targetThreshold // ≤480px, not 500
    let rafId: number | null = null
    let isDisconnected = false

    const observer = new ResizeObserver((_entries) => {
      if (isDisconnected) return

      // Cancel any pending RAF
      if (rafId !== null) {
        cancelAnimationFrame(rafId)
      }

      rafId = requestAnimationFrame(() => {
        if (isDisconnected || !inlineMainRef.current) return

        const height = inlineMainRef.current.scrollHeight

        // Always log for diagnostic visibility
        console.log(
          `[MindSort Diagnostic] Inline main scrollHeight: ${height}px` +
            (height > LAYOUT.maxHeight ? ` — EXCEEDS ${LAYOUT.maxHeight}px LIMIT` : '') +
            (height > target ? ` — above ${target}px target` : '')
        )

        // Read current values from refs (not closure) to avoid stale reads
        const currentExpandedId = expandedClusterIdRef.current
        const currentCapacity = finalDetailCapacityRef.current
        const currentGuardedCount = guardedDetailCountRef.current

        // Only decrement if over target AND we have an expanded cluster
        if (height > target && currentExpandedId && currentCapacity > 0) {
          const nextCount = currentCapacity - 1

          // No-op if count unchanged (prevents thrash)
          if (nextCount !== currentGuardedCount) {
            setGuardedDetailCount(nextCount)
          }
        } else if (height > target && currentExpandedId && currentCapacity === 0) {
          // Zero-capacity reached but still over target - log the failure
          console.warn(
            `[MindSort Diagnostic] guard reached zero, card still exceeds target: ${height}px`
          )
        }
      })
    })

    observer.observe(inlineMainRef.current)

    return () => {
      isDisconnected = true
      if (rafId !== null) {
        cancelAnimationFrame(rafId)
      }
      observer.disconnect()
    }
  }, [isInitialized]) // Only depends on isInitialized - observer lifecycle decoupled from state

  // ==========================================================================
  // HANDLERS
  // ==========================================================================

  // Toggle cluster expansion (accordion: opening one closes the previous)
  const handleToggleCluster = useCallback((clusterId: string) => {
    setExpandedClusterId((prev) => (prev === clusterId ? null : clusterId))
  }, [])

  // ==========================================================================
  // DISPLAY MODE HANDLERS
  // ==========================================================================
  // Entry: LOCAL STATE only (setDisplayMode) - per PG-Claude pattern
  // Exit: requestDisplayMode({ mode: 'inline' }) with try/catch

  // Expand to fullscreen - LOCAL STATE only (no requestDisplayMode call on entry)
  // This is the pattern used by PG-Claude (verified 2026-07-22)
  const handleExpandToFullscreen = useCallback(() => {
    if (isBridgeStale || !isFullscreenAvailable) return
    setDisplayMode('fullscreen')
  }, [isBridgeStale, isFullscreenAvailable])

  // Minimize to inline - calls requestDisplayMode with try/catch
  // Reconciles from returned mode; never wedges on failure
  const handleMinimizeToInline = useCallback(async () => {
    setHostFullscreen(false)
    if (appRef.current?.requestDisplayMode) {
      try {
        const result = await appRef.current.requestDisplayMode({ mode: 'inline' })
        setDisplayMode(result.mode === 'fullscreen' ? 'fullscreen' : 'inline')
      } catch {
        // Silent — inline is the default, failure here is harmless
        // Host context will reconcile via onhostcontextchanged
        setDisplayMode('inline')
      }
    } else {
      setDisplayMode('inline')
    }
    // Focus restoration happens in onhostcontextchanged when host confirms exit
  }, [])

  // Handle "Open full board" button click
  // When fullscreen is available: enters fullscreen mode
  // When not available (fallback): calls load_saved_board (legacy behavior)
  const handleOpenFullBoard = useCallback(async () => {
    if (!appRef.current || isLoadingBoard) return

    // If fullscreen is available, use it
    if (isFullscreenAvailable) {
      handleExpandToFullscreen()
      return
    }

    // Fallback: call load_saved_board (for hosts without fullscreen)
    setIsLoadingBoard(true)
    try {
      await appRef.current.callServerTool({
        name: 'load_saved_board',
        arguments: {},
      })
    } catch (err) {
      console.error('MindSort widget: Error loading full board:', err)
    } finally {
      setIsLoadingBoard(false)
    }
  }, [isLoadingBoard, isFullscreenAvailable, handleExpandToFullscreen])

  // Handle "View remaining cluster content" overflow action
  const handleViewRemainingContent = useCallback(async () => {
    if (!appRef.current || isLoadingBoard || !expandedCluster) return

    setIsLoadingBoard(true)
    try {
      // CONFIRMED MECHANISM: callServerTool('load_saved_board', {})
      // No cluster-scoped tool exists. This renders the whole board.
      // The user will see all cluster contents including this one.
      await appRef.current.callServerTool({
        name: 'load_saved_board',
        arguments: {},
      })
    } catch (err) {
      console.error('MindSort widget: Error loading full board:', err)
    } finally {
      setIsLoadingBoard(false)
    }
  }, [isLoadingBoard, expandedCluster])

  // ==========================================================================
  // RENDER: Loading/Stale states
  // ==========================================================================

  // Stale session overlay - MUST be checked BEFORE loading state
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

  // Loading state
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

  // ==========================================================================
  // RENDER: Fullscreen mode
  // ==========================================================================
  if (displayMode === 'fullscreen') {
    return (
      <FullscreenBoardView
        clusters={sortedClusters}
        hostFullscreen={hostFullscreen}
        safeAreaInsets={hostContext.safeAreaInsets}
        onMinimize={handleMinimizeToInline}
      />
    )
  }

  // ==========================================================================
  // RENDER: Inline mode (main card)
  // ==========================================================================

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
            fontWeight: 500,
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: `${LAYOUT.collapsedRowGap}px` }}>
          {visibleClusters.map((cluster) => {
            const isExpanded = expandedClusterId === cluster.cluster_name
            const detailRegionId = `cluster-detail-${cluster.cluster_name.replace(/\s+/g, '-')}`

            return (
              <div key={cluster.cluster_name}>
                {/* Cluster row - now a toggle button */}
                <ClusterRowToggle
                  cluster={cluster}
                  isExpanded={isExpanded}
                  detailRegionId={detailRegionId}
                  onToggle={() => handleToggleCluster(cluster.cluster_name)}
                />

                {/* Expanded detail section */}
                {isExpanded && (
                  <div
                    id={detailRegionId}
                    role="list"
                    aria-label={`Details for ${cluster.cluster_name}`}
                    style={{
                      marginTop: `${LAYOUT.sectionGap}px`,
                      display: 'flex',
                      flexDirection: 'column',
                      gap: `${LAYOUT.detailRowGap}px`,
                    }}
                  >
                    {/* Detail rows - role="listitem" requires parent role="list" */}
                    {visibleDetailUnits.map((unit, index) => (
                      <DetailRow key={`${unit.type}-${index}`} unit={unit} />
                    ))}

                    {/* Zero-capacity fallback: show overflow action even with no detail rows */}
                    {/* Overflow control: "View remaining cluster content" */}
                    {hasDetailOverflow && (
                      <OverflowActionRow
                        clusterName={cluster.cluster_name}
                        overflowCount={overflowCount}
                        isLoading={isLoadingBoard}
                        onAction={handleViewRemainingContent}
                      />
                    )}
                  </div>
                )}
              </div>
            )
          })}
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
        {/* Board-level overflow indicator */}
        <span
          style={{
            fontSize: '12px',
            color: 'var(--color-text-tertiary, #73726C)',
          }}
        >
          {boardOverflow > 0 ? `+${boardOverflow} more cluster${boardOverflow !== 1 ? 's' : ''}` : ''}
        </span>

        {/* Open full board button - ref for focus restoration on fullscreen exit */}
        <button
          ref={fullscreenOpenerRef}
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
            minHeight: '44px',
            minWidth: '44px',
          }}
          aria-label={isFullscreenAvailable ? 'Open full board in fullscreen' : 'Open full board in conversation'}
        >
          {isLoadingBoard ? 'Loading...' : 'Open full board →'}
        </button>
      </div>
    </main>
  )
}

// =============================================================================
// CLUSTER ROW TOGGLE
// =============================================================================

interface ClusterRowToggleProps {
  cluster: Cluster
  isExpanded: boolean
  detailRegionId: string
  onToggle: () => void
}

/**
 * Cluster row as a toggle button for accordion expansion.
 *
 * Accessibility:
 * - Real button: Enter AND Space activate
 * - aria-expanded reflects state
 * - aria-controls references the detail region
 * - Focus ring using --color-ring-primary
 * - Priority expressed by badge TEXT (not only color)
 */
function ClusterRowToggle({
  cluster,
  isExpanded,
  detailRegionId,
  onToggle,
}: ClusterRowToggleProps) {
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
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={isExpanded}
      aria-controls={detailRegionId}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        width: '100%',
        background: 'var(--color-background-primary, #FFFFFF)',
        borderRadius: 'var(--border-radius-md, 8px)',
        padding: '10px 12px',
        border: `var(--border-width-regular, 0.5px) solid var(--color-border-tertiary, #E0DFDB)`,
        borderLeft: hasPriority && colors
          ? `3px solid ${colors.border}`
          : `var(--border-width-regular, 0.5px) solid var(--color-border-tertiary, #E0DFDB)`,
        minHeight: `${LAYOUT.collapsedRowH}px`,
        cursor: 'pointer',
        textAlign: 'left',
        // Focus ring
        outline: 'none',
      }}
      // Focus ring via CSS-in-JS workaround (onFocus/onBlur for inline styles)
      onFocus={(e) => {
        e.currentTarget.style.boxShadow = '0 0 0 2px var(--color-ring-primary, #3B82F6)'
      }}
      onBlur={(e) => {
        e.currentTarget.style.boxShadow = 'none'
      }}
    >
      {/* Expand/collapse indicator - SVG chevron (compliance: design-guidelines) */}
      <span
        aria-hidden="true"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--color-text-tertiary, #73726C)',
          flexShrink: 0,
          transition: 'transform 0.15s ease',
          transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
        }}
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </span>

      {/* Priority badge (only if prioritized) - TEXT conveys priority, not only color */}
      {hasPriority && rank && colors && (
        <span
          style={{
            fontSize: '11px',
            fontWeight: 500,
            padding: '2px 6px',
            borderRadius: '4px',
            background: colors.bg,
            color: colors.text,
            flexShrink: 0,
          }}
          // Screen reader: badge text "P1"/"P2"/"P3" conveys priority without color
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
          minWidth: 0,
        }}
        title={cluster.cluster_name} // Full text for truncated names
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
    </button>
  )
}

// =============================================================================
// DETAIL ROW
// =============================================================================

interface DetailRowProps {
  unit: DetailUnit
}

/**
 * Single row in expanded detail section.
 *
 * - Summary: 1-line clamped, tertiary text
 * - Thought: 1-line clamped, optional priority badge
 * - Subcluster: name + count, optional priority badge
 *
 * All have fixed height via max-height + 1-line clamp.
 * Full text preserved via title attribute for accessibility.
 */
function DetailRow({ unit }: DetailRowProps) {
  const hasPriority = !!unit.priority?.rank
  const rank = unit.priority?.rank

  const rankColors: Record<string, { bg: string; text: string }> = {
    P1: {
      bg: 'var(--color-background-danger, #F7ECEC)',
      text: 'var(--color-text-danger, #7F2C28)',
    },
    P2: {
      bg: 'var(--color-background-warning, #F6EEDF)',
      text: 'var(--color-text-warning, #5A4815)',
    },
    P3: {
      bg: 'var(--color-background-info, #D6E4F6)',
      text: 'var(--color-text-info, #3266AD)',
    },
  }
  const colors = rank ? rankColors[rank] : null

  // Type-specific prefix for screen readers
  const typeLabel = unit.type === 'summary' ? 'Summary' :
                    unit.type === 'thought' ? 'Thought' : 'Subcluster'

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        background: unit.type === 'summary'
          ? 'var(--color-background-tertiary, #FAFAF8)'
          : 'var(--color-background-primary, #FFFFFF)',
        borderRadius: 'var(--border-radius-sm, 6px)',
        padding: '8px 10px',
        height: `${LAYOUT.detailRowH}px`,
        maxHeight: `${LAYOUT.detailRowH}px`,
        boxSizing: 'border-box', // CRITICAL: padding included in height, else 36+16=52px
      }}
      role="listitem"
      aria-label={`${typeLabel}: ${unit.text}${unit.count !== undefined ? `, ${unit.count} thoughts` : ''}`}
    >
      {/* Type icon - monochrome SVG, NOT emoji (compliance: design-guidelines) */}
      <span
        aria-hidden="true"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--color-text-tertiary, #73726C)',
          flexShrink: 0,
          width: '16px',
        }}
      >
        {unit.type === 'summary' && (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <path d="M14 2v6h6" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </svg>
        )}
        {unit.type === 'thought' && (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <circle cx="12" cy="12" r="3" />
          </svg>
        )}
        {unit.type === 'subcluster' && (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
        )}
      </span>

      {/* Priority badge for thoughts/subclusters */}
      {hasPriority && rank && colors && unit.type !== 'summary' && (
        <span
          style={{
            fontSize: '10px',
            fontWeight: 500,
            padding: '1px 4px',
            borderRadius: '3px',
            background: colors.bg,
            color: colors.text,
            flexShrink: 0,
          }}
        >
          {rank}
        </span>
      )}

      {/* Content text - 1-line clamp */}
      <span
        style={{
          flex: 1,
          fontSize: '12px',
          fontWeight: unit.type === 'summary' ? 400 : 500,
          color: unit.type === 'summary'
            ? 'var(--color-text-secondary, #3D3D3A)'
            : 'var(--color-text-primary, #141413)',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          minWidth: 0,
          fontStyle: unit.type === 'summary' ? 'italic' : 'normal',
        }}
        title={unit.text} // Full text for accessibility
      >
        {unit.text}
      </span>

      {/* Subcluster count */}
      {unit.type === 'subcluster' && unit.count !== undefined && (
        <span
          style={{
            fontSize: '11px',
            color: 'var(--color-text-tertiary, #73726C)',
            flexShrink: 0,
            whiteSpace: 'nowrap',
          }}
        >
          {unit.count} thought{unit.count !== 1 ? 's' : ''}
        </span>
      )}
    </div>
  )
}

// =============================================================================
// OVERFLOW ACTION ROW
// =============================================================================

interface OverflowActionRowProps {
  clusterName: string
  overflowCount: number
  isLoading: boolean
  onAction: () => void
}

/**
 * "View remaining cluster content" overflow control.
 *
 * Fixed height, single line, touch-target compliant.
 * Accessible name includes cluster name.
 * Calls load_saved_board (renders whole board).
 *
 * N = hidden THOUGHT items + hidden SUBCLUSTERS
 * (summary omission is not counted as "remaining content")
 */
function OverflowActionRow({
  clusterName,
  overflowCount,
  isLoading,
  onAction,
}: OverflowActionRowProps) {
  // Build count string (optional, fits on one line)
  const countStr = overflowCount > 0 ? ` (${overflowCount} more)` : ''

  return (
    <button
      type="button"
      onClick={onAction}
      disabled={isLoading}
      aria-label={`View remaining content in ${clusterName}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '6px',
        width: '100%',
        height: `${LAYOUT.overflowActionRowH}px`,
        minHeight: `${LAYOUT.overflowActionRowH}px`,
        padding: '8px 12px',
        fontSize: '12px',
        fontWeight: 500,
        color: 'var(--color-text-info, #1E40AF)',
        background: 'var(--color-background-info, #EFF6FF)',
        border: 'none',
        borderRadius: 'var(--border-radius-md, 8px)',
        cursor: isLoading ? 'wait' : 'pointer',
        opacity: isLoading ? 0.6 : 1,
        outline: 'none',
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
      }}
      onFocus={(e) => {
        e.currentTarget.style.boxShadow = '0 0 0 2px var(--color-ring-primary, #3B82F6)'
      }}
      onBlur={(e) => {
        e.currentTarget.style.boxShadow = 'none'
      }}
    >
      {isLoading ? 'Loading...' : `View remaining cluster content${countStr}`}
    </button>
  )
}

// =============================================================================
// FULLSCREEN BOARD VIEW
// =============================================================================
// Renders the full board (all clusters, all thoughts, all subclusters, tag pills)
// READ-ONLY: No mutation controls, no CRUD calls, no edit handlers
// Performance target: 30 clusters / 300 thoughts / 60 subclusters
// Beyond target: virtualization via intersection observer

interface FullscreenBoardViewProps {
  clusters: Cluster[]
  hostFullscreen: boolean
  safeAreaInsets: { top: number; bottom: number; left: number; right: number }
  onMinimize: () => void
}

/**
 * Fullscreen full-board view.
 *
 * - Shows ALL clusters expanded (not accordion)
 * - Full summary text (no clamp)
 * - All thought items (priority-sorted)
 * - Subclusters as nested cards with their thoughts
 * - Tag PILLS (deferred from inline to here)
 * - Native fullscreen close not duplicated (gated on hostFullscreen)
 * - Responsive grid layout
 * - READ-ONLY: no mutation, no CRUD, no edit handlers
 */
function FullscreenBoardView({
  clusters,
  hostFullscreen,
  safeAreaInsets,
  onMinimize,
}: FullscreenBoardViewProps) {
  const clusterCount = clusters.length
  const thoughtCount = getTotalThoughtCount(clusters)

  // Virtualization: for large boards, only render clusters in viewport
  // Track which clusters are visible via intersection observer
  const [visibleClusterIds, setVisibleClusterIds] = useState<Set<string>>(new Set())
  const observerRef = useRef<IntersectionObserver | null>(null)
  const clusterRefs = useRef<Map<string, HTMLElement>>(new Map())

  // Check if board exceeds scale target (needs virtualization)
  const totalSubclusters = clusters.reduce(
    (sum, c) => sum + (c.subclusters?.length ?? 0),
    0
  )
  const needsVirtualization =
    clusterCount > FULLSCREEN_SCALE_TARGET.maxClusters ||
    thoughtCount > FULLSCREEN_SCALE_TARGET.maxThoughts ||
    totalSubclusters > FULLSCREEN_SCALE_TARGET.maxSubclusters

  // Set up intersection observer for virtualization
  useEffect(() => {
    if (!needsVirtualization) {
      // No virtualization needed - all clusters visible
      setVisibleClusterIds(new Set(clusters.map((c) => c.cluster_name)))
      return
    }

    // Create observer for lazy rendering
    observerRef.current = new IntersectionObserver(
      (entries) => {
        setVisibleClusterIds((prev) => {
          const next = new Set(prev)
          for (const entry of entries) {
            const clusterId = entry.target.getAttribute('data-cluster-id')
            if (clusterId) {
              if (entry.isIntersecting) {
                next.add(clusterId)
              }
              // Don't remove - once rendered, keep rendered for scroll stability
            }
          }
          return next
        })
      },
      { rootMargin: '200px' } // Pre-load 200px before entering viewport
    )

    // Observe all cluster placeholders
    clusterRefs.current.forEach((el) => {
      observerRef.current?.observe(el)
    })

    return () => {
      observerRef.current?.disconnect()
    }
  }, [needsVirtualization, clusters])

  // Register cluster ref for intersection observer
  const registerClusterRef = useCallback((clusterId: string, el: HTMLElement | null) => {
    if (el) {
      clusterRefs.current.set(clusterId, el)
      if (observerRef.current) {
        observerRef.current.observe(el)
      }
    }
  }, [])

  return (
    <div
      role="main"
      aria-label="MindSort AI Full Board"
      style={{
        width: '100%',
        minHeight: '100vh',
        background: 'var(--color-background-primary, #FFFFFF)',
        padding: `${safeAreaInsets.top + 16}px ${safeAreaInsets.right + 16}px ${safeAreaInsets.bottom + 16}px ${safeAreaInsets.left + 16}px`,
        boxSizing: 'border-box',
      }}
    >
      {/* Fullscreen header with minimize button - only when NOT host-provided fullscreen */}
      {!hostFullscreen && (
        <FullscreenHeader onMinimize={onMinimize} />
      )}

      {/* Board header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          marginBottom: '24px',
          paddingTop: !hostFullscreen ? '8px' : '0',
        }}
      >
        <h1
          style={{
            fontSize: '20px',
            fontWeight: 500,
            color: 'var(--color-text-primary, #141413)',
            margin: 0,
          }}
        >
          Your MindSort AI Board
        </h1>
        <span
          style={{
            fontSize: '14px',
            color: 'var(--color-text-tertiary, #73726C)',
          }}
        >
          {clusterCount} cluster{clusterCount !== 1 ? 's' : ''} · {thoughtCount} thought{thoughtCount !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Large board indicator */}
      {needsVirtualization && (
        <div
          style={{
            padding: '12px 16px',
            marginBottom: '16px',
            background: 'var(--color-background-info, #EFF6FF)',
            borderRadius: 'var(--border-radius-md, 8px)',
            fontSize: '13px',
            color: 'var(--color-text-info, #1E40AF)',
          }}
        >
          Large board detected. Clusters load as you scroll for best performance.
        </div>
      )}

      {/* Cluster grid - responsive layout */}
      {clusters.length > 0 ? (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '16px',
          }}
        >
          {clusters.map((cluster) => {
            const isVisible = !needsVirtualization || visibleClusterIds.has(cluster.cluster_name)
            return (
              <div
                key={cluster.cluster_name}
                ref={(el) => needsVirtualization && registerClusterRef(cluster.cluster_name, el)}
                data-cluster-id={cluster.cluster_name}
                style={{
                  minHeight: isVisible ? 'auto' : '200px', // Placeholder height for virtualization
                }}
              >
                {isVisible ? (
                  <FullscreenClusterCard cluster={cluster} />
                ) : (
                  // Placeholder for virtualized cluster
                  <div
                    style={{
                      height: '200px',
                      background: 'var(--color-background-secondary, #F5F4ED)',
                      borderRadius: 'var(--border-radius-xl, 12px)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: 'var(--color-text-tertiary, #73726C)',
                      fontSize: '13px',
                    }}
                  >
                    Loading {cluster.cluster_name}...
                  </div>
                )}
              </div>
            )
          })}
        </div>
      ) : (
        <p
          style={{
            fontSize: '14px',
            color: 'var(--color-text-tertiary, #73726C)',
            textAlign: 'center',
            padding: '48px 0',
          }}
        >
          No clusters yet. Start organizing your thoughts!
        </p>
      )}
    </div>
  )
}

// =============================================================================
// FULLSCREEN HEADER
// =============================================================================

interface FullscreenHeaderProps {
  onMinimize: () => void
}

/**
 * Fullscreen header with minimize button.
 * Only rendered when !hostFullscreen (host does NOT provide native close).
 * Keyboard accessible: Enter/Space activate.
 */
function FullscreenHeader({ onMinimize }: FullscreenHeaderProps) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'flex-end',
        marginBottom: '8px',
      }}
    >
      <button
        type="button"
        onClick={onMinimize}
        aria-label="Minimize to inline view"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '8px 12px',
          fontSize: '13px',
          fontWeight: 500,
          color: 'var(--color-text-secondary, #3D3D3A)',
          background: 'var(--color-background-secondary, #F5F4ED)',
          border: 'none',
          borderRadius: 'var(--border-radius-md, 8px)',
          cursor: 'pointer',
          minHeight: '36px',
          outline: 'none',
        }}
        onFocus={(e) => {
          e.currentTarget.style.boxShadow = '0 0 0 2px var(--color-ring-primary, #3B82F6)'
        }}
        onBlur={(e) => {
          e.currentTarget.style.boxShadow = 'none'
        }}
      >
        {/* Minimize icon - SVG chevron down */}
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
          <polyline points="6 9 12 15 18 9" />
        </svg>
        Minimize
      </button>
    </div>
  )
}

// =============================================================================
// FULLSCREEN CLUSTER CARD
// =============================================================================

interface FullscreenClusterCardProps {
  cluster: Cluster
}

/**
 * Full cluster card for fullscreen view.
 *
 * Shows:
 * - Header: name, priority badge, thought count
 * - Full summary (no clamp)
 * - All thought items (priority-sorted)
 * - All subclusters as nested cards
 * - Tag PILLS (full pills, not just indicator)
 */
function FullscreenClusterCard({ cluster }: FullscreenClusterCardProps) {
  const hasPriority = !!cluster.priority?.rank
  const rank = cluster.priority?.rank
  const hasTags = (cluster.tags?.length ?? 0) > 0

  // Rank colors
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

  // Get thoughts sorted by priority
  const thoughts = (cluster.thought_items ?? []).map(normalizeThoughtItem)
  const sortedThoughts = [...thoughts].sort((a, b) => {
    return rankToNumber(a.priority?.rank) - rankToNumber(b.priority?.rank)
  })

  const subclusters = cluster.subclusters ?? []

  return (
    <article
      aria-label={`Cluster: ${cluster.cluster_name}`}
      style={{
        background: 'var(--color-background-secondary, #F5F4ED)',
        borderRadius: 'var(--border-radius-xl, 12px)',
        padding: '16px',
        borderLeft: hasPriority && colors
          ? `4px solid ${colors.border}`
          : 'none',
      }}
    >
      {/* Header row: name, priority badge, thought count */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          marginBottom: '12px',
        }}
      >
        {/* Priority badge */}
        {hasPriority && rank && colors && (
          <span
            style={{
              fontSize: '12px',
              fontWeight: 500,
              padding: '2px 8px',
              borderRadius: '4px',
              background: colors.bg,
              color: colors.text,
              flexShrink: 0,
            }}
          >
            {rank}
          </span>
        )}

        {/* Cluster name */}
        <h2
          style={{
            flex: 1,
            fontSize: '15px',
            fontWeight: 500,
            color: 'var(--color-text-primary, #141413)',
            margin: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {cluster.cluster_name}
        </h2>

        {/* Thought count */}
        <span
          style={{
            fontSize: '13px',
            color: 'var(--color-text-tertiary, #73726C)',
            flexShrink: 0,
          }}
        >
          {cluster.sum_thought_items ?? 0} thought{(cluster.sum_thought_items ?? 0) !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Tag pills - FULL PILLS, not just indicator */}
      {hasTags && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '6px',
            marginBottom: '12px',
          }}
          aria-label="Action tags"
        >
          {cluster.tags!.map((tag) => (
            <TagPill key={tag} tag={tag} />
          ))}
        </div>
      )}

      {/* Summary - full text, no clamp */}
      {cluster.summary && (
        <p
          style={{
            fontSize: '13px',
            fontStyle: 'italic',
            color: 'var(--color-text-secondary, #3D3D3A)',
            margin: '0 0 12px 0',
            lineHeight: 1.5,
          }}
        >
          {cluster.summary}
        </p>
      )}

      {/* Thought items - priority sorted */}
      {sortedThoughts.length > 0 && (
        <ul
          style={{
            listStyle: 'none',
            margin: 0,
            padding: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
          }}
          aria-label={`Thoughts in ${cluster.cluster_name}`}
        >
          {sortedThoughts.map((thought, index) => (
            <FullscreenThoughtItem key={`thought-${index}`} thought={thought} />
          ))}
        </ul>
      )}

      {/* Subclusters as nested cards */}
      {subclusters.length > 0 && (
        <div
          style={{
            marginTop: sortedThoughts.length > 0 ? '16px' : '0',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
          }}
        >
          {subclusters.map((subcluster) => (
            <FullscreenSubclusterCard key={subcluster.subcluster_name} subcluster={subcluster} />
          ))}
        </div>
      )}
    </article>
  )
}

// =============================================================================
// TAG PILL
// =============================================================================

interface TagPillProps {
  tag: string
}

/**
 * Tag pill component for fullscreen view.
 * Uses Claude tokens (surfaces/text/border), NOT hardcoded colors.
 */
function TagPill({ tag }: TagPillProps) {
  return (
    <span
      role="listitem"
      aria-label={`Tag: ${tag}`}
      style={{
        fontSize: '11px',
        fontWeight: 500,
        padding: '3px 8px',
        borderRadius: '12px',
        background: 'var(--color-background-tertiary, #EDECEA)',
        color: 'var(--color-text-secondary, #3D3D3A)',
        border: '1px solid var(--color-border-tertiary, #E0DFDB)',
        whiteSpace: 'nowrap',
      }}
    >
      {tag}
    </span>
  )
}

// =============================================================================
// FULLSCREEN THOUGHT ITEM
// =============================================================================

interface FullscreenThoughtItemProps {
  thought: { text: string; priority?: { rank: Rank } }
}

/**
 * Thought item in fullscreen view.
 * Full text (no clamp), optional priority badge.
 */
function FullscreenThoughtItem({ thought }: FullscreenThoughtItemProps) {
  const hasPriority = !!thought.priority?.rank
  const rank = thought.priority?.rank

  const rankColors: Record<string, { bg: string; text: string }> = {
    P1: {
      bg: 'var(--color-background-danger, #F7ECEC)',
      text: 'var(--color-text-danger, #7F2C28)',
    },
    P2: {
      bg: 'var(--color-background-warning, #F6EEDF)',
      text: 'var(--color-text-warning, #5A4815)',
    },
    P3: {
      bg: 'var(--color-background-info, #D6E4F6)',
      text: 'var(--color-text-info, #3266AD)',
    },
  }
  const colors = rank ? rankColors[rank] : null

  return (
    <li
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '8px',
        padding: '8px 12px',
        background: 'var(--color-background-primary, #FFFFFF)',
        borderRadius: 'var(--border-radius-md, 8px)',
      }}
    >
      {/* Bullet icon */}
      <span
        aria-hidden="true"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--color-text-tertiary, #73726C)',
          flexShrink: 0,
          marginTop: '3px',
        }}
      >
        <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
          <circle cx="12" cy="12" r="4" />
        </svg>
      </span>

      {/* Priority badge */}
      {hasPriority && rank && colors && (
        <span
          style={{
            fontSize: '10px',
            fontWeight: 500,
            padding: '1px 5px',
            borderRadius: '3px',
            background: colors.bg,
            color: colors.text,
            flexShrink: 0,
          }}
        >
          {rank}
        </span>
      )}

      {/* Thought text - full, no clamp */}
      <span
        style={{
          flex: 1,
          fontSize: '13px',
          color: 'var(--color-text-primary, #141413)',
          lineHeight: 1.5,
        }}
      >
        {thought.text}
      </span>
    </li>
  )
}

// =============================================================================
// FULLSCREEN SUBCLUSTER CARD
// =============================================================================

interface FullscreenSubclusterCardProps {
  subcluster: Subcluster
}

/**
 * Subcluster as nested card in fullscreen view.
 * Shows: name, priority badge, thought count, all thoughts.
 */
function FullscreenSubclusterCard({ subcluster }: FullscreenSubclusterCardProps) {
  const hasPriority = !!subcluster.priority?.rank
  const rank = subcluster.priority?.rank
  const hasTags = (subcluster.tags?.length ?? 0) > 0

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

  // Get thoughts sorted by priority
  const thoughts = (subcluster.thought_items ?? []).map(normalizeThoughtItem)
  const sortedThoughts = [...thoughts].sort((a, b) => {
    return rankToNumber(a.priority?.rank) - rankToNumber(b.priority?.rank)
  })

  return (
    <div
      aria-label={`Subcluster: ${subcluster.subcluster_name}`}
      style={{
        background: 'var(--color-background-primary, #FFFFFF)',
        borderRadius: 'var(--border-radius-md, 8px)',
        padding: '12px',
        borderLeft: hasPriority && colors
          ? `3px solid ${colors.border}`
          : '3px solid var(--color-border-tertiary, #E0DFDB)',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          marginBottom: sortedThoughts.length > 0 || hasTags ? '10px' : '0',
        }}
      >
        {/* Folder icon */}
        <span
          aria-hidden="true"
          style={{
            display: 'flex',
            alignItems: 'center',
            color: 'var(--color-text-tertiary, #73726C)',
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
        </span>

        {/* Priority badge */}
        {hasPriority && rank && colors && (
          <span
            style={{
              fontSize: '10px',
              fontWeight: 500,
              padding: '1px 5px',
              borderRadius: '3px',
              background: colors.bg,
              color: colors.text,
              flexShrink: 0,
            }}
          >
            {rank}
          </span>
        )}

        {/* Subcluster name */}
        <span
          style={{
            flex: 1,
            fontSize: '13px',
            fontWeight: 500,
            color: 'var(--color-text-primary, #141413)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {subcluster.subcluster_name}
        </span>

        {/* Thought count */}
        <span
          style={{
            fontSize: '12px',
            color: 'var(--color-text-tertiary, #73726C)',
            flexShrink: 0,
          }}
        >
          {subcluster.sum_thought_items} thought{subcluster.sum_thought_items !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Tag pills */}
      {hasTags && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '4px',
            marginBottom: sortedThoughts.length > 0 ? '10px' : '0',
          }}
        >
          {subcluster.tags!.map((tag) => (
            <TagPill key={tag} tag={tag} />
          ))}
        </div>
      )}

      {/* Thoughts */}
      {sortedThoughts.length > 0 && (
        <ul
          style={{
            listStyle: 'none',
            margin: 0,
            padding: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
          }}
        >
          {sortedThoughts.map((thought, index) => (
            <li
              key={`sub-thought-${index}`}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '6px',
                fontSize: '12px',
                color: 'var(--color-text-primary, #141413)',
                lineHeight: 1.4,
              }}
            >
              <span
                aria-hidden="true"
                style={{
                  color: 'var(--color-text-tertiary, #73726C)',
                  marginTop: '4px',
                }}
              >
                •
              </span>
              {thought.priority?.rank && (
                <span
                  style={{
                    fontSize: '9px',
                    fontWeight: 500,
                    padding: '0 4px',
                    borderRadius: '2px',
                    background: rankColors[thought.priority.rank]?.bg,
                    color: rankColors[thought.priority.rank]?.text,
                    flexShrink: 0,
                  }}
                >
                  {thought.priority.rank}
                </span>
              )}
              <span>{thought.text}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default App
