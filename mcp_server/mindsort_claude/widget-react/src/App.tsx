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
  sortThoughtsByPriority,
  sortSubclustersByPriority,
  getEffectiveRank,
  RANK_COLORS,
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

/**
 * INLINE_SHOW_ALL_ITEMS (inc 7 §3): when true, an expanded cluster renders ALL of
 * its detail units (no per-item capacity cap) and lets height auto-fit — the
 * published Anthropic guidance ("auto-fits to content, no nested scrolling") sets
 * no numeric height limit, so the old ~500px budget was self-imposed.
 *
 * PHASED / ROLLBACK: the capacity machinery (computeDetailCapacity, finalDetailCapacity,
 * OverflowActionRow, the ResizeObserver row-stripping) is kept DORMANT, not deleted.
 * Flip this to `false` to restore the capped behaviour in one line if prod validation
 * (manual C) shows the host CLIPS content or the CARD develops its own scrollbar
 * (nested scrolling — prohibited). Delete the dormant machinery only in a follow-up
 * increment, and only after prod confirms outcome (1): the PAGE scrolls, not the card.
 */
const INLINE_SHOW_ALL_ITEMS = true

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

  // (2) Thought items - priority-sorted via shared helper
  const sortedThoughts = sortThoughtsByPriority(cluster.thought_items ?? [])
  for (const thought of sortedThoughts) {
    units.push({
      type: 'thought',
      text: thought.text,
      priority: thought.priority,
    })
  }

  // (3) Subclusters - as named rows with count, NOT nested
  // Sorted by effective subcluster rank (inc 5) via shared helper
  const sortedSubclusters = sortSubclustersByPriority(cluster.subclusters ?? [])
  for (const sub of sortedSubclusters) {
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
  // `hostFullscreen` was a SECOND state variable tracked alongside displayMode, and it
  // could drift: setHostFullscreen(true) fired only from the initial getHostContext() read
  // at mount, so a host-granted fullscreen arriving later left displayMode='fullscreen'
  // with hostFullscreen=false. It is not tracked any more — after host negotiation the two
  // are the same fact, so it is derived where needed rather than stored.
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

  // In-flight guard for requestDisplayMode. A ref, not state: it must not trigger a
  // render, and it is read and written in the same tick. Cleared in `finally` so a
  // REJECTED request also releases it — clearing only on the success path would let one
  // failed request disable fullscreen permanently until remount.
  const displayModeRequestPendingRef = useRef(false)

  // Set once a mode has been negotiated with the host. Guards the one-shot baseline read
  // below: `requestDisplayMode` does NOT update the SDK's cached _hostContext (only a
  // hostcontextchanged notification does), so a late baseline read still carries the
  // 'inline' it was constructed with and would undo a fullscreen the host just granted.
  const displayModeNegotiatedRef = useRef(false)

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

      // THIS BLOCK REGISTERS HANDLERS, AND NOTHING ELSE.
      //
      // It previously also read the host-context baseline here — getHostContext() for
      // displayMode, availableDisplayModes, safeAreaInsets and platform. That was DEAD
      // CODE. useApp calls onAppCreated BEFORE `await connect()`, and `_hostContext` is
      // assigned inside connect() from the ui/initialize response; getHostContext() is
      // documented "Returns undefined if called before connection is established." So the
      // read always saw undefined, `availableDisplayModes` stayed [], the strict gate kept
      // "Open full board" hidden, and fullscreen was reachable only if the host happened to
      // send a later hostcontextchanged that carried availableDisplayModes — which the
      // protocol does not require. PG-Claude had the identical bug and fixed it the same
      // way (priority_guardian_claude/.../App.tsx:481-487).
      //
      // The baseline read now lives in the effect below, keyed on `app`, which useApp sets
      // only after connect() resolves. Handler registration MUST stay here: the host may
      // deliver a one-shot notification as soon as the handshake completes.

      // Register handler for host context changes (mode transitions, safe area, etc.)
      // Host context is authoritative; local state reconciles toward it.
      appInstance.onhostcontextchanged = (ctx) => {
        if (ctx.displayMode !== undefined) {
          const newMode: DisplayMode = ctx.displayMode === 'fullscreen' ? 'fullscreen' : 'inline'
          // RECONCILE ONLY — observe what the host already did and update local state.
          // Never call requestDisplayMode() from here: the host has ALREADY switched, so
          // requesting the mode it just reported asks it to redo its own work.
          setDisplayMode(newMode)
          // Focus restoration is handled by a useEffect on the displayMode transition and
          // is deliberately independent of display-mode REQUESTS.
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

  // ---------------------------------------------------------------------------
  // Host-context baseline read.
  //
  // Keyed on `app`, which useApp sets ONLY after `await connect()` resolves — so by the
  // time this runs the ui/initialize handshake is complete and getHostContext() has real
  // data. This is the whole point: the previous read ran in onAppCreated, before connect,
  // and always saw undefined, which left availableDisplayModes empty and the fullscreen
  // affordance permanently hidden on a host that never sent a follow-up notification.
  //
  // Ongoing updates stay with onhostcontextchanged, which writes per-field into the same
  // state. Anything that arrives before this effect runs is not lost: the handler is
  // registered pre-connect and writes to React state directly, and the SDK also merges the
  // notification into _hostContext, so the baseline read below reflects it either way.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!app) return

    const initial = app.getHostContext?.()
    if (!initial) return

    const initialMode: DisplayMode = initial.displayMode === 'fullscreen' ? 'fullscreen' : 'inline'

    // A negotiated mode outranks this snapshot — see displayModeNegotiatedRef.
    if (!displayModeNegotiatedRef.current) {
      setDisplayMode(initialMode)
    }

    // Seed per-field, falling back to what we already hold, so a host context that omits a
    // field cannot erase it.
    setHostContext((prev) => ({
      displayMode: displayModeNegotiatedRef.current ? prev.displayMode : initialMode,
      availableDisplayModes:
        (initial.availableDisplayModes as DisplayMode[] | undefined) ?? prev.availableDisplayModes,
      safeAreaInsets: initial.safeAreaInsets ?? prev.safeAreaInsets,
      platform: initial.platform ?? prev.platform,
    }))
  }, [app])

  // Inject host theme CSS variables (must pass hostContext for dark mode)
  useHostStyles(app, app?.getHostContext())

  // inc 6 §1 (width): stamp the current display mode on <html> so main.css can
  // scope the 600px #root cap to inline only. Fullscreen must fill its container;
  // the cap stays on every mode EXCEPT explicit fullscreen (see main.css). The
  // attribute lives on documentElement (sanctioned by §1: "#root/<html>") so the
  // mechanism is observable even where #root is not the mount node.
  //
  // useLayoutEffect (not useEffect): runs BEFORE paint, so a fullscreen-initial
  // mount (getHostContext() → 'fullscreen' in onAppCreated) never flashes the
  // capped/narrow board for a frame before widening.
  //
  // Cleanup REMOVES the attribute on unmount. Absent = inline-capped (the safe
  // default), so a widget that unmounts while fullscreen (Claude iOS teardown /
  // instance supersession) can't strand data-display-mode="fullscreen" on a
  // shared <html> and silently uncap a later inline card — the mirror-image bug.
  useLayoutEffect(() => {
    const root = document.documentElement
    if (!root) return
    root.setAttribute('data-display-mode', displayMode)
    return () => root.removeAttribute('data-display-mode')
  }, [displayMode])

  // Track previous displayMode for focus restoration
  const prevDisplayModeRef = useRef<DisplayMode>(displayMode)

  // Focus restoration: when displayMode transitions to inline, restore focus
  // to the opener button. Uses requestAnimationFrame to ensure the inline
  // tree has remounted before focusing (the button doesn't exist in fullscreen).
  useEffect(() => {
    const prevMode = prevDisplayModeRef.current
    prevDisplayModeRef.current = displayMode

    if (prevMode === 'fullscreen' && displayMode === 'inline') {
      // Schedule focus after the inline tree remounts
      requestAnimationFrame(() => {
        if (fullscreenOpenerRef.current) {
          fullscreenOpenerRef.current.focus()
        }
      })
    }
  }, [displayMode])

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

  // Visible detail units and overflow count.
  // inc 7 §3: under show-all, render EVERY unit and treat nothing as hidden. The
  // capacity slice stays computed above (dormant) so rollback is a one-line flag flip.
  const visibleDetailUnits = INLINE_SHOW_ALL_ITEMS
    ? detailUnits
    : detailUnits.slice(0, finalDetailCapacity)
  const hiddenDetailUnits = INLINE_SHOW_ALL_ITEMS
    ? []
    : detailUnits.slice(finalDetailCapacity)
  // N = hidden THOUGHT items + hidden SUBCLUSTERS (summary omission not counted)
  const overflowCount = hiddenDetailUnits.filter(
    (u) => u.type === 'thought' || u.type === 'subcluster'
  ).length
  // inc 7 §3: no overflow affordance while show-all is active (nothing is hidden).
  const hasDetailOverflow = INLINE_SHOW_ALL_ITEMS
    ? false
    : overflowCount > 0 || finalDetailCapacity === 0

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

        // inc 7 §3: while show-all is active the observer is DIAGNOSTIC ONLY — it logs
        // the height above but must NOT strip rows (setGuardedDetailCount). Height is
        // allowed to auto-fit; prod check C decides whether that page-scrolls (good),
        // clips (revert), or nested-scrolls (fix). Row-stripping stays wired for the
        // flag=false rollback path.
        if (INLINE_SHOW_ALL_ITEMS) return

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
  // Entry and exit are both HOST-NEGOTIATED: requestDisplayMode() asks, and the mode the
  // host RETURNS is authoritative. Local React state can select a fullscreen *layout*; it
  // cannot promote the app into host fullscreen. Only the host can do that, which is why
  // entry must ask rather than assume.
  //
  // (Superseded comment, do not restore: "Entry: LOCAL STATE only (setDisplayMode) - per
  // PG-Claude pattern ... verified 2026-07-22". That was wrong on both counts — it was
  // local-only, and PG-Claude does NOT do this: PG calls requestDisplayMode and applies
  // the returned mode. The stale claim is why entry never reached real host fullscreen.)

  // Expand to fullscreen - asks the host, applies the host's answer.
  const handleExpandToFullscreen = useCallback(async () => {
    // STRICT capability gate, deliberately NOT PG's permissive-when-absent variant: if the
    // host has not advertised fullscreen, stay inline and send nothing.
    if (isBridgeStale || !isFullscreenAvailable) return

    const app = appRef.current
    // No request method: remain inline. Never fake a local fullscreen — a fullscreen
    // layout inside an inline iframe is the divergence this increment removes.
    if (!app?.requestDisplayMode) return

    if (displayModeRequestPendingRef.current) return
    displayModeRequestPendingRef.current = true

    try {
      const result = await app.requestDisplayMode({ mode: 'fullscreen' })
      // THE RETURNED MODE DECIDES — not the fact that the promise resolved. A resolved
      // request may legitimately return 'inline'; treating resolution as success would
      // reproduce local-only fullscreen by a different route.
      displayModeNegotiatedRef.current = true
      setDisplayMode(result.mode === 'fullscreen' ? 'fullscreen' : 'inline')
    } catch {
      // Declined or failed: remain inline, cleanly.
      displayModeNegotiatedRef.current = true
      setDisplayMode('inline')
    } finally {
      displayModeRequestPendingRef.current = false
    }
  }, [isBridgeStale, isFullscreenAvailable])

  // There is deliberately NO exit handler. Returning to inline is the HOST's to initiate,
  // via the native close it renders in its own header in fullscreen — observed present,
  // and returning cleanly to the inline board, on both mobile and desktop (2026-08-17).
  // onhostcontextchanged then reports the change and reconciliation observes it.
  //
  // The former handleMinimizeToInline drove an app-owned Minimize button. Both are gone:
  // two exit affordances on one surface is duplicate chrome, and the app-owned one was the
  // 36px tap target as well. Do not reintroduce a requestDisplayMode({mode:'inline'}) call
  // from reconciliation — that asks the host to redo a switch it has already made.

  // Handle "Open full board" button click - enters fullscreen mode.
  // Button is only rendered when isFullscreenAvailable (capability-gated),
  // so this handler always has fullscreen available.
  const handleOpenFullBoard = useCallback(() => {
    void handleExpandToFullscreen()
  }, [handleExpandToFullscreen])

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
        safeAreaInsets={hostContext.safeAreaInsets}
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
          {clusterCount} cluster{clusterCount !== 1 ? 's' : ''} / {thoughtCount} item{thoughtCount !== 1 ? 's' : ''}
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

        {/* Open full board button - ONLY when host advertises fullscreen capability.
            Briefing: "do NOT render the fullscreen affordance" when unavailable;
            "a dead/no-op button is prohibited." The inline accordion is the
            intended experience on hosts without fullscreen. */}
        {isFullscreenAvailable && (
          <button
            ref={fullscreenOpenerRef}
            type="button"
            onClick={handleOpenFullBoard}
            style={{
              padding: '8px 12px',
              fontSize: '12px',
              fontWeight: 500,
              color: 'var(--color-text-info, #1E40AF)',
              background: 'transparent',
              border: 'none',
              borderRadius: 'var(--border-radius-md, 8px)',
              cursor: 'pointer',
              minHeight: '44px',
              minWidth: '44px',
            }}
            aria-label="Open full board in fullscreen"
          >
            {/* SVG arrow - no Unicode glyphs per briefing */}
            Open full board{' '}
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{ verticalAlign: 'middle', marginLeft: '2px' }}
              aria-hidden="true"
            >
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
        )}
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

  // Use shared RANK_COLORS from utils.ts
  const colors = rank ? RANK_COLORS[rank] : null

  // Accent line reads EFFECTIVE rank (own, or highest anywhere in the subtree) so a
  // priority living on a collapsed cluster's subcluster/item is visible at the top
  // level. Badge still reads OWN rank only — see the badge block below.
  const effectiveRank = getEffectiveRank(cluster)
  const borderColors = effectiveRank ? RANK_COLORS[effectiveRank] : null

  // The accent is colour-only, so the inherited case needs a text alternative
  // (compliance M2). Only for genuinely-inherited priority: an own-rank cluster
  // already announces its rank via the badge text and must not double-announce.
  const inheritedRank = effectiveRank && !hasPriority ? effectiveRank : null

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
        borderLeft: effectiveRank && borderColors
          ? `3px solid ${borderColors.border}`
          : `var(--border-width-regular, 0.5px) solid var(--color-border-tertiary, #E0DFDB)`,
        minHeight: `${LAYOUT.collapsedRowH}px`,
        cursor: 'pointer',
        textAlign: 'left',
        // Focus ring
        outline: 'none',
      }}
      // Focus ring via CSS-in-JS workaround (onFocus/onBlur for inline styles)
      onFocus={(e) => {
        e.currentTarget.style.boxShadow = '0 0 0 2px var(--color-ring-primary, #141413)'
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

      {/* Priority badge (only if OWN rank set) - TEXT conveys priority, not only color.
          DESIGN: Badge shows OWN rank only, not effective rank. A cluster is only labeled
          P1 if explicitly prioritized. Effective rank determines ORDER (via sortClustersForOverview).
          Matches OpenAI (ClusterCard uses cluster.priority?.rank for badge). */}
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

      {/* Text alternative for the accent line (compliance M2: text alternatives for
          visual content). The accent is the ONLY signal for inherited priority and
          colour alone is not accessible, so announce it. Rendered ONLY when the rank
          is inherited — an own-rank cluster already has the badge text above. */}
      {inheritedRank && (
        <span className="sr-only" style={{ position: 'absolute', width: '1px', height: '1px', padding: 0, margin: '-1px', overflow: 'hidden', clip: 'rect(0, 0, 0, 0)', whiteSpace: 'nowrap', border: 0, lineHeight: 'var(--font-text-xs-line-height, 1.4)' }}>
          contains {inheritedRank} priority
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
        {cluster.sum_thought_items ?? 0} item{(cluster.sum_thought_items ?? 0) !== 1 ? 's' : ''}
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

  // Use shared RANK_COLORS from utils.ts
  const colors = rank ? RANK_COLORS[rank] : null

  // Type-specific prefix for screen readers
  const typeLabel = unit.type === 'summary' ? 'Summary' :
                    unit.type === 'thought' ? 'Thought' : 'Subcluster'

  // inc 7 §1: thought rows carry a LEFT VERTICAL BAR marker (4px prioritized / 2px
  // otherwise), reusing FullscreenThoughtItem's exact weights + colours, in place of
  // the former circle icon. Summary/subcluster keep their SVG icons this increment.
  const isThought = unit.type === 'thought'
  const thoughtBar = isThought
    ? {
        borderLeft: `${hasPriority ? '4px' : '2px'} solid ${
          hasPriority
            ? colors?.border ?? 'var(--color-border-strong, #141413)'
            : 'var(--color-border-tertiary, #E0DFDB)'
        }`,
      }
    : {}

  // inc 7 (post-review): under show-all, detail rows WRAP to full text (parity with
  // FullscreenThoughtItem) — the whole point of removing the cap was to READ items, not
  // just list them. The fixed 36px height is load-bearing for the DORMANT capacity model
  // (computeDetailCapacity assumes detailRowH), so keep the 1-line clamp on the flag=false
  // rollback path and only un-clamp when show-all is active. Applies to all 3 row types.
  const rowSizing = INLINE_SHOW_ALL_ITEMS
    ? { minHeight: `${LAYOUT.detailRowH}px` }
    : { height: `${LAYOUT.detailRowH}px`, maxHeight: `${LAYOUT.detailRowH}px` }
  const textClamp = INLINE_SHOW_ALL_ITEMS
    ? { overflowWrap: 'anywhere' as const } // wrap; a long unbroken token can't overflow-scroll
    : { whiteSpace: 'nowrap' as const, overflow: 'hidden' as const, textOverflow: 'ellipsis' as const }

  return (
    <div
      style={{
        display: 'flex',
        // Top-align marker/badge with line 1 when text wraps; center for single-line clamp.
        alignItems: INLINE_SHOW_ALL_ITEMS ? 'flex-start' : 'center',
        gap: '8px',
        background: unit.type === 'summary'
          ? 'var(--color-background-tertiary, #FAFAF8)'
          : 'var(--color-background-primary, #FFFFFF)',
        borderRadius: 'var(--border-radius-sm, 6px)',
        padding: '8px 10px',
        ...rowSizing, // inc 7: fixed 36px when capped (rollback fidelity); minHeight + grow under show-all
        boxSizing: 'border-box', // CRITICAL: padding included in height, else 36+16=52px
        ...thoughtBar, // inc 7 §1: left bar for thought rows (marker parity w/ fullscreen)
      }}
      role="listitem"
      aria-label={`${typeLabel}: ${unit.text}${unit.count !== undefined ? `, ${unit.count} items` : ''}`}
    >
      {/* Type icon for summary/subcluster — monochrome SVG, NOT emoji (compliance).
          inc 7 §1: thought rows use the left bar above instead of an icon, so no
          icon column is rendered for thoughts. */}
      {!isThought && (
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
          {unit.type === 'subcluster' && (
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
            </svg>
          )}
        </span>
      )}

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

      {/* Content text - wraps to full text under show-all; 1-line ellipsis on rollback */}
      <span
        style={{
          flex: 1,
          fontSize: '12px',
          fontWeight: unit.type === 'summary' ? 400 : 500,
          color: unit.type === 'summary'
            ? 'var(--color-text-secondary, #3D3D3A)'
            : 'var(--color-text-primary, #141413)',
          ...textClamp, // inc 7: wrap under show-all / 1-line ellipsis when capped
          minWidth: 0,
          fontStyle: unit.type === 'summary' ? 'italic' : 'normal',
        }}
        title={unit.text} // Full text for accessibility (redundant under show-all, harmless)
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
          {unit.count} item{unit.count !== 1 ? 's' : ''}
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
        e.currentTarget.style.boxShadow = '0 0 0 2px var(--color-ring-primary, #141413)'
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
// VISUAL ALIGNMENT (inc_fullscreen_shell_primitives_alignment.md):
// - Grid: 240px min-width (matches OpenAI), 16px gap
// - Board container: secondary background, 16px radius, 32px horizontal / 24px vertical padding
// - Header: title + subtitle stacked, NO count (count removed for OpenAI parity)
// - Empty state: OpenAI copy
// - Auto-save footer: "Changes are saved automatically"
// - Safe-area insets: KEPT (Claude requirement, no OpenAI equivalent)
//
// READ-ONLY: No mutation controls, no CRUD calls, no edit handlers
// Performance target: 30 clusters / 300 thoughts / 60 subclusters
// Beyond target: virtualization via intersection observer
//
// INTENTIONAL ASYMMETRY: Inline card KEEPS its count; fullscreen has none.
// This matches OpenAI and is not a bug.

interface FullscreenBoardViewProps {
  clusters: Cluster[]
  safeAreaInsets: { top: number; bottom: number; left: number; right: number }
}

/**
 * Fullscreen full-board view.
 *
 * - Shows ALL clusters expanded (not accordion)
 * - Full summary text (no clamp)
 * - All thought items (priority-sorted)
 * - Subclusters as nested cards with their thoughts
 * - Tag PILLS (deferred from inline to here)
 * - NO app-owned exit control: the host renders a native close in its own header in
 *   fullscreen (observed on mobile and desktop 2026-08-17, returning cleanly to inline).
 *   This view is only reached when the host GRANTED fullscreen, so there is no state in
 *   which an app-owned fallback exit would be needed — a `!hostFullscreen` gate here was
 *   unreachable, which is why the prop and the header are gone rather than gated.
 * - Responsive grid layout (240px min, matches OpenAI)
 * - Header: title + subtitle, NO count (OpenAI parity)
 * - Auto-save footer at the end
 * - READ-ONLY: no mutation, no CRUD, no edit handlers
 */
function FullscreenBoardView({
  clusters,
  safeAreaInsets,
}: FullscreenBoardViewProps) {
  // Counts needed for virtualization check, NOT displayed in header (OpenAI parity)
  // INTENTIONAL ASYMMETRY: Inline card shows count; fullscreen header does not.
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
        // OpenAI: bg-surface-secondary rounded-2xl px-8 py-6 (tinted rounded card)
        // Safe-area insets: KEPT (Claude requirement, no OpenAI equivalent)
        width: '100%',
        background: 'var(--color-background-secondary, #F5F4ED)',
        // inc 6 §3: board container radius → --border-radius-xl (12px), off the
        // former 16px literal (no --border-radius-2xl token exists). Padding
        // tightened to 16px vertical / 20px horizontal + safe-area insets (kept).
        borderRadius: 'var(--border-radius-xl, 12px)',
        padding: `${safeAreaInsets.top + 16}px ${safeAreaInsets.right + 20}px ${safeAreaInsets.bottom + 16}px ${safeAreaInsets.left + 20}px`,
        boxSizing: 'border-box',
      }}
    >
      {/* No app-owned minimize header: the host's native close is the only exit.
          This was `{!hostFullscreen && <FullscreenHeader …>}`, which became unreachable
          once the app stopped faking fullscreen locally — this view renders only when the
          host granted fullscreen, so !hostFullscreen was false in every reachable state. */}

      {/* Board header: title + subtitle, NO count (OpenAI parity)
          INTENTIONAL ASYMMETRY: Inline card keeps count; fullscreen header has none. */}
      <div
        style={{
          marginBottom: '16px', // inc 6 §3: board header bottom margin 24→16
          // Was `!hostFullscreen ? '8px' : '0'` — the 8px only ever spaced the board header
          // below the removed minimize bar, so it resolves to the host-fullscreen value.
          paddingTop: '0',
        }}
      >
        <h1
          style={{
            fontSize: 'var(--font-text-sm-size, 14px)', // heading-sm (keep 14)
            lineHeight: 'var(--font-text-sm-line-height, 1.4)', // inc 6 §2: off 1.5
            fontWeight: 500, // COMPLIANCE: 500 max
            color: 'var(--color-text-primary, #141413)',
            margin: 0,
            marginBottom: '2px', // inc 6 §3: board title bottom margin 4→2
          }}
        >
          Your MindSort AI Board
        </h1>
        <p
          style={{
            fontSize: 'var(--font-text-xs-size, 12px)', // inc 6 §2: board subtitle 14→12
            lineHeight: 'var(--font-text-xs-line-height, 1.4)',
            color: 'var(--color-text-secondary, #3D3D3A)',
            margin: 0,
          }}
        >
          Your thoughts grouped into clusters. Use the chat to rename, split, or reprioritize them.
        </p>
      </div>

      {/* Large board indicator */}
      {needsVirtualization && (
        <div
          style={{
            padding: '12px 16px',
            marginBottom: '16px',
            background: 'var(--color-background-info, #EFF6FF)',
            borderRadius: 'var(--border-radius-md, 8px)',
            fontSize: 'var(--font-text-xs-size, 12px)', // inc 6 §2: large-board notice 13→12
            lineHeight: 'var(--font-text-xs-line-height, 1.4)',
            color: 'var(--color-text-info, #1E40AF)',
          }}
        >
          Large board detected. Clusters load as you scroll for best performance.
        </div>
      )}

      {/* Cluster grid - responsive layout (240px matches OpenAI) */}
      {clusters.length > 0 ? (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: '12px', // inc 6 §3: grid gap 16→12 (240px min kept — 3–4 cols at desktop)
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
                      fontSize: 'var(--font-text-xs-size, 12px)', // inc 6 §2: on-scale (was 13)
                      lineHeight: 'var(--font-text-xs-line-height, 1.4)',
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
        <div
          style={{
            padding: '24px',
            textAlign: 'center',
            fontSize: 'var(--font-text-sm-size, 14px)', // text-sm (keep, tokenized)
            lineHeight: 'var(--font-text-sm-line-height, 1.4)',
            color: 'var(--color-text-secondary, #3D3D3A)',
            background: 'var(--color-background-primary, #FFFFFF)',
            borderRadius: 'var(--border-radius-xl, 12px)',
          }}
        >
          No saved board yet. Start one by sharing what's on your mind in the chat.
        </div>
      )}

      {/* Auto-save footer (OpenAI parity) - FULLSCREEN ONLY */}
      <p
        style={{
          fontSize: 'var(--font-text-xs-size, 12px)', // text-xs (keep, tokenized)
          lineHeight: 'var(--font-text-xs-line-height, 1.4)',
          color: 'var(--color-text-secondary, #3D3D3A)',
          marginTop: '12px', // mt-3 (auto-save footer margin unchanged per §2/§4)
          textAlign: 'left',
        }}
      >
        Changes are saved automatically
      </p>
    </div>
  )
}

// =============================================================================
// FULLSCREEN CLUSTER CARD
// =============================================================================
// VISUAL ALIGNMENT: Matches OpenAI ClusterCard structure (inc_fullscreen_visual_alignment_openai.md)
// - Container: rounded-2xl (16px), p-5 (20px), shadow-lg, min-h-[120px], flex flex-col
//   ^ describes OpenAI's original. inc 6 (density) DEVIATES: radius 12px, p-3 (12px),
//     shadow-sm, no min-height. Structure/order unchanged; only sizes/spacing tightened.
// - Prioritized: border-l-4 + pl-6 (24px left padding)  [inc 6: pl 16px]
// - Header: name + badge on left, count pill on right
// - Order: header → summary → thoughts → subclusters → TAGS LAST
// - Count: outlined pill with number only + sr-only full text
//
// COMPLIANCE DEVIATIONS (kept from OpenAI):
// - fontWeight: 500 max (Anthropic guideline; OpenAI uses font-semibold/600)
// - Collapse indicators: SVG chevrons (not Unicode ▲/▼)
// - Styling: Claude tokens + inline styles (no Tailwind, no OpenAI SDK)
// - Focus ring: --color-ring-primary (Claude's ring token)
// - Collapsibility: NOT added (fullscreen shows everything expanded by design)
//
// PRODUCT DEVIATION (intentional, not compliance):
// - Summary: full text, no 100-char clamp (fullscreen has room)

interface FullscreenClusterCardProps {
  cluster: Cluster
}

/**
 * Full cluster card for fullscreen view.
 *
 * Shows:
 * - Header: name + priority badge on left, count pill on right
 * - Full summary (no clamp - product deviation)
 * - All thought items (priority-sorted)
 * - All subclusters as nested cards
 * - Tag PILLS at the END (OpenAI order)
 */
function FullscreenClusterCard({ cluster }: FullscreenClusterCardProps) {
  const hasPriority = !!cluster.priority?.rank
  const rank = cluster.priority?.rank
  const hasTags = (cluster.tags?.length ?? 0) > 0

  // Use shared RANK_COLORS and sortThoughtsByPriority from utils.ts
  const colors = rank ? RANK_COLORS[rank] : null
  const sortedThoughts = sortThoughtsByPriority(cluster.thought_items ?? [])
  // Sort subclusters by effective rank (inc 5) via shared helper
  const subclusters = sortSubclustersByPriority(cluster.subclusters ?? [])
  const thoughtCount = cluster.sum_thought_items ?? 0

  // Compute border styles to avoid shorthand/longhand conflicts (same pattern as subcluster)
  // OpenAI: border + border-default ALWAYS; when prioritized ALSO border-l-4 border-l-strong + pl-6
  const borderStyles = hasPriority && colors
    ? {
        borderLeft: `4px solid ${colors.border}`,
        borderTop: '1px solid var(--color-border-tertiary, #E0DFDB)',
        borderRight: '1px solid var(--color-border-tertiary, #E0DFDB)',
        borderBottom: '1px solid var(--color-border-tertiary, #E0DFDB)',
      }
    : {
        border: '1px solid var(--color-border-tertiary, #E0DFDB)',
      }

  return (
    <article
      aria-label={`Cluster: ${cluster.cluster_name}${hasPriority ? `, Priority ${rank?.replace('P', '')}` : ''}, ${thoughtCount} items`}
      style={{
        // OpenAI: rounded-2xl (16px), p-5 (20px), shadow-lg, min-h-[120px], flex flex-col
        // Cards are PRIMARY surface on SECONDARY board, with BORDER + shadow (figure/ground)
        background: 'var(--color-background-primary, #FFFFFF)',
        // inc 6 §3: radius → --border-radius-xl (12px) off the 16px literal.
        borderRadius: 'var(--border-radius-xl, 12px)',
        // inc 6 §3: padding 20→12 (16px left rail when prioritized, was 24).
        padding: hasPriority ? '12px 12px 12px 16px' : '12px',
        // inc 6 §3: minHeight 120px REMOVED (cards fit content, no forced stretch).
        display: 'flex',
        flexDirection: 'column',
        // inc 6 §3: shadow-lg → shadow-sm. Cards already carry a 1px border for
        // figure/ground on the tinted board; at reduced padding + 12px radius the
        // large lg blur read heavy and inflated inter-card spacing. sm keeps a
        // subtle lift. Flagged for Nadja's manual B/G visual confirmation.
        boxShadow: 'var(--shadow-sm, 0 1px 2px 0 rgba(0, 0, 0, 0.05))',
        ...borderStyles,
      }}
    >
      {/* Header row: name + badge LEFT, count pill RIGHT (OpenAI layout) */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: '8px',
          marginBottom: '8px', // inc 6 §3: header→content margin 12→8
        }}
      >
        {/* Left side: name + priority badge */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            flex: 1,
            minWidth: 0,
          }}
        >
          {/* Cluster name FIRST (OpenAI order) */}
          <h2
            style={{
              fontSize: 'var(--font-text-sm-size, 14px)', // text-sm (keep 14 — cluster heading)
              lineHeight: 'var(--font-text-sm-line-height, 1.4)',
              fontWeight: 500, // COMPLIANCE: 500 max (not font-semibold/600)
              color: 'var(--color-text-primary, #141413)',
              margin: 0,
              wordBreak: 'break-word',
              minWidth: 0,
            }}
          >
            {cluster.cluster_name || 'Untitled cluster'}
          </h2>

          {/* Priority badge AFTER name (OpenAI order)
              DESIGN: Badge shows OWN rank only, not effective rank. A cluster is only
              labeled P1 if explicitly prioritized. Effective rank determines ORDER
              (via sortClustersForOverview). Matches OpenAI (ClusterCard uses
              cluster.priority?.rank for badge, getEffectiveRank for sort).
              INTENTIONAL DEVIATION: Color-coded badges (P1 danger / P2 warning / P3 info).
              OpenAI uses Badge variant="solid" color="secondary" (neutral).
              Claude keeps RANK_COLORS to reinforce rank visually; priority is ALSO
              conveyed by badge TEXT ("P1") so it stays WCAG-compliant without color. */}
          {hasPriority && rank && colors && (
            <span
              aria-label={`Priority ${rank.replace('P', '')}`}
              style={{
                fontSize: 'var(--font-text-xs-size, 12px)', // keep 12 (tokenized)
                lineHeight: 'var(--font-text-xs-line-height, 1.4)',
                fontWeight: 500,
                padding: '1px 6px', // inc 6 §3: priority badge padding (cluster) 2px 8px → 1px 6px
                borderRadius: '4px',
                background: colors.bg,
                color: colors.text,
                flexShrink: 0,
              }}
            >
              {rank}
            </span>
          )}
        </div>

        {/* Right side: count pill (outlined, number only + sr-only text) */}
        <span role="text" aria-label={`${thoughtCount} items in this cluster`}>
          <span
            aria-hidden="true"
            style={{
              fontSize: 'var(--font-text-xs-size, 12px)', // count pill (cluster) keep 12
              lineHeight: 'var(--font-text-xs-line-height, 1.4)',
              fontWeight: 500,
              padding: '1px 6px', // inc 6 §3: count pill padding 2px 8px → 1px 6px
              borderRadius: 'var(--border-radius-full, 9999px)', // pill shape (tokenized)
              background: 'transparent',
              color: 'var(--color-text-secondary, #3D3D3A)',
              border: '1px solid var(--color-border-tertiary, #E0DFDB)',
              flexShrink: 0,
            }}
          >
            {thoughtCount}
          </span>
          <span className="sr-only" style={{ position: 'absolute', width: '1px', height: '1px', padding: 0, margin: '-1px', overflow: 'hidden', clip: 'rect(0, 0, 0, 0)', whiteSpace: 'nowrap', border: 0, lineHeight: 'var(--font-text-xs-line-height, 1.4)' }}>
            {thoughtCount} items
          </span>
        </span>
      </div>

      {/* Summary - full text, no clamp (PRODUCT DEVIATION: fullscreen has room) */}
      {cluster.summary && (
        <p
          style={{
            fontSize: 'var(--font-text-xs-size, 12px)', // inc 6 §2: cluster summary 13→12
            color: 'var(--color-text-secondary, #3D3D3A)',
            margin: '0 0 8px 0', // inc 6 §3: summary bottom margin 12→8
            lineHeight: 'var(--font-text-xs-line-height, 1.4)', // inc 6 §2: off 1.5
          }}
        >
          {cluster.summary}
        </p>
      )}

      {/* Thought items - priority sorted */}
      {sortedThoughts.length > 0 && (
        <ul
          role="list"
          style={{
            listStyle: 'none',
            margin: 0,
            padding: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: '4px', // inc 6 §3: thought list gap 8→4
          }}
          aria-label={`Items in ${cluster.cluster_name}`}
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
            marginTop: sortedThoughts.length > 0 ? '8px' : '0', // inc 6 §3: subcluster block top margin 12→8
            display: 'flex',
            flexDirection: 'column',
            gap: '8px', // inc 6 §3: subcluster card gap 12→8
          }}
        >
          {subclusters.map((subcluster) => (
            <FullscreenSubclusterCard key={subcluster.subcluster_name} subcluster={subcluster} />
          ))}
        </div>
      )}

      {/* Tags LAST (OpenAI order: mt-auto pt-4) */}
      {hasTags && (
        <div
          role="list"
          aria-label="Suggested actions"
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '8px',
            marginTop: 'auto',
            paddingTop: '10px', // inc 6 §3: tags padding-top (cluster) 16→10
          }}
        >
          {cluster.tags!.map((tag) => (
            <TagPill key={tag} tag={tag} />
          ))}
        </div>
      )}
    </article>
  )
}

// =============================================================================
// TAG PILL
// =============================================================================
// VISUAL ALIGNMENT: OpenAI TagPill uses Badge color="secondary" variant="soft"
// - Lowercase visible text (tag.toLowerCase())
// - Soft variant = filled tint, NO border
// - Accessible label uses ORIGINAL casing: "Suggested action: ${tag}"

interface TagPillProps {
  tag: string
}

/**
 * Tag pill component for fullscreen view.
 * Soft variant: filled tint, no border. Lowercase visible text.
 * Accessible label preserves original casing.
 */
function TagPill({ tag }: TagPillProps) {
  return (
    <span
      role="listitem"
      aria-label={`Suggested action: ${tag}`}
      style={{
        fontSize: 'var(--font-text-xs-size, 12px)', // inc 6 §2: tag pill 11→12
        lineHeight: 'var(--font-text-xs-line-height, 1.4)',
        fontWeight: 500,
        padding: '2px 6px', // inc 6 §3: tag pill padding 3px 8px → 2px 6px
        borderRadius: 'var(--border-radius-full, 9999px)', // inc 6 §3: was 12px literal
        // Soft variant: filled tint, NO border (OpenAI Badge variant="soft")
        background: 'var(--color-background-tertiary, #EDECEA)',
        color: 'var(--color-text-secondary, #3D3D3A)',
        whiteSpace: 'nowrap',
      }}
    >
      {tag.toLowerCase()}
    </span>
  )
}

// =============================================================================
// FULLSCREEN THOUGHT ITEM
// =============================================================================
// VISUAL ALIGNMENT: Matches OpenAI ThoughtItem structure (inc_fullscreen_visual_alignment_openai.md)
// - Left priority bar (border-l-4 when prioritized, border-l-2 otherwise)
// - NO bullet icon, NO card background, NO border-radius
// - Text FIRST, priority badge AFTER text
// - size="small" variant for thoughts inside subclusters
//
// COMPLIANCE DEVIATIONS (kept from OpenAI):
// - fontWeight: 500 max (Anthropic guideline; OpenAI uses 600)
// - Styling: Claude tokens + inline styles (no Tailwind, no OpenAI SDK)

interface FullscreenThoughtItemProps {
  thought: { text: string; priority?: { rank: Rank } }
  size?: 'normal' | 'small'
}

/**
 * Thought item in fullscreen view.
 * Left priority bar, text first, badge after. No bullet, no card background.
 */
function FullscreenThoughtItem({ thought, size = 'normal' }: FullscreenThoughtItemProps) {
  const hasPriority = !!thought.priority?.rank
  const rank = thought.priority?.rank

  // Use shared RANK_COLORS from utils.ts
  const colors = rank ? RANK_COLORS[rank] : null

  // OpenAI ThoughtItem: border-l-4 border-l-strong when prioritized, border-l-2 border-default otherwise
  // Padding: pl-3 py-1 (normal), pl-2 py-0.5 (small)
  const borderWidth = hasPriority ? '4px' : '2px'
  const borderColor = hasPriority
    ? (colors?.border ?? 'var(--color-border-strong, #141413)')
    : 'var(--color-border-tertiary, #E0DFDB)'

  const isSmall = size === 'small'
  const paddingLeft = isSmall ? '8px' : '10px'   // inc 6 §3: normal pl 12→10 (small 8 kept)
  const paddingY = isSmall ? '1px' : '2px'        // inc 6 §3: py 4→2 (small 2→1)
  const fontSize = 'var(--font-text-xs-size, 12px)' // inc 6 §2: 12 for both (was 12/13)

  return (
    <li
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        paddingLeft,
        paddingTop: paddingY,
        paddingBottom: paddingY,
        borderLeft: `${borderWidth} solid ${borderColor}`,
        // NO background, NO border-radius (matches OpenAI)
      }}
    >
      {/* Text FIRST (OpenAI order) */}
      <span
        style={{
          flex: 1,
          fontSize,
          color: 'var(--color-text-primary, #141413)',
          lineHeight: 'var(--font-text-xs-line-height, 1.4)', // inc 6 §2: off 1.5
        }}
      >
        {thought.text}
      </span>

      {/* Priority badge AFTER text (OpenAI order) */}
      {hasPriority && rank && colors && (
        <span
          style={{
            fontSize: 'var(--font-text-xs-size, 12px)', // inc 6 §2: thought badge 9/10→12
            lineHeight: 'var(--font-text-xs-line-height, 1.4)',
            fontWeight: 500, // COMPLIANCE: 500 max (not 600)
            padding: '0 5px', // inc 6 §3: priority badge padding (thought) → 0 5px
            borderRadius: '3px',
            background: colors.bg,
            color: colors.text,
            flexShrink: 0,
          }}
        >
          {rank}
        </span>
      )}
    </li>
  )
}

// =============================================================================
// FULLSCREEN SUBCLUSTER CARD
// =============================================================================
// VISUAL ALIGNMENT: Matches OpenAI SubclusterCard structure (inc_fullscreen_visual_alignment_openai.md)
// - Container: rounded-lg (8px), p-3 (12px), surface background
// - Left accent: border-l-4 ONLY when prioritized (NOT always-on)
// - Header: name + badge on left, count pill on right
// - Order: header → thoughts → TAGS LAST (mt-auto pt-2)
// - Count: outlined pill with number only + sr-only full text
// - Thoughts: size="small" variant
//
// COMPLIANCE DEVIATIONS (kept from OpenAI):
// - fontWeight: 500 max (Anthropic guideline; OpenAI uses font-medium which is 500 anyway)
// - Styling: Claude tokens + inline styles (no Tailwind, no OpenAI SDK)

interface FullscreenSubclusterCardProps {
  subcluster: Subcluster
}

/**
 * Subcluster as nested card in fullscreen view.
 * Shows: name + badge left, count pill right, thoughts (small), tags LAST.
 */
function FullscreenSubclusterCard({ subcluster }: FullscreenSubclusterCardProps) {
  const hasPriority = !!subcluster.priority?.rank
  const rank = subcluster.priority?.rank
  const hasTags = (subcluster.tags?.length ?? 0) > 0

  // Use shared RANK_COLORS and sortThoughtsByPriority from utils.ts
  const colors = rank ? RANK_COLORS[rank] : null
  const sortedThoughts = sortThoughtsByPriority(subcluster.thought_items ?? [])
  const thoughtCount = subcluster.sum_thought_items ?? sortedThoughts.length

  // Compute border styles to avoid shorthand/longhand conflicts
  const borderStyles = hasPriority && colors
    ? {
        borderLeft: `4px solid ${colors.border}`,
        borderTop: 'none',
        borderRight: 'none',
        borderBottom: 'none',
      }
    : {
        border: '1px solid var(--color-border-tertiary, #E0DFDB)',
      }

  return (
    <div
      aria-label={`Subcluster: ${subcluster.subcluster_name}`}
      style={{
        // OpenAI: rounded-lg (8px), p-3 (12px), bg-surface
        // NOTE: --border-radius-lg is 10px in Anthropic tokens; use --border-radius-md for 8px
        // SECONDARY background for tonal nesting contrast against PRIMARY cluster card (inc 5)
        background: 'var(--color-background-secondary, #F5F4ED)',
        borderRadius: 'var(--border-radius-md, 8px)',
        padding: '10px', // inc 6 §3: subcluster card padding 12→10
        display: 'flex',
        flexDirection: 'column',
        // OpenAI: border-l-4 border-l-strong ONLY when prioritized, otherwise border-subtle (no left accent)
        ...borderStyles,
      }}
    >
      {/* Header: name + badge LEFT, count pill RIGHT (OpenAI layout) */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: '8px',
          marginBottom: sortedThoughts.length > 0 || hasTags ? '6px' : '0', // inc 6 §3: subcluster header bottom margin 8→6
        }}
      >
        {/* Left side: name + priority badge */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            flex: 1,
            minWidth: 0,
          }}
        >
          {/* Subcluster name FIRST (OpenAI order) */}
          <h4
            style={{
              fontSize: 'var(--font-text-xs-size, 12px)', // inc 6 §2: subcluster name 14→12 (subordinate to cluster name)
              lineHeight: 'var(--font-text-xs-line-height, 1.4)',
              fontWeight: 500, // font-medium
              color: 'var(--color-text-primary, #141413)',
              margin: 0,
              wordBreak: 'break-word',
              minWidth: 0,
            }}
          >
            {subcluster.subcluster_name || 'Untitled'}
          </h4>

          {/* Priority badge AFTER name (OpenAI order) */}
          {hasPriority && rank && colors && (
            <span
              style={{
                fontSize: 'var(--font-text-xs-size, 12px)', // inc 6 §2: subcluster badge 10→12
                lineHeight: 'var(--font-text-xs-line-height, 1.4)',
                fontWeight: 500,
                padding: '0 5px', // inc 6 §3: priority badge padding (subcluster) → 0 5px
                borderRadius: '3px',
                background: colors.bg,
                color: colors.text,
                flexShrink: 0,
              }}
            >
              {rank}
            </span>
          )}
        </div>

        {/* Right side: count pill (outlined, number only + sr-only text) */}
        <span role="text" aria-label={`${thoughtCount} items in this subcluster`}>
          <span
            aria-hidden="true"
            style={{
              fontSize: 'var(--font-text-xs-size, 12px)', // inc 6 §2: count pill (subcluster) 11→12
              lineHeight: 'var(--font-text-xs-line-height, 1.4)',
              fontWeight: 500,
              padding: '1px 6px', // inc 6 §3: count pill padding (kept 1px 6px)
              borderRadius: 'var(--border-radius-full, 9999px)', // pill shape (tokenized)
              background: 'transparent',
              color: 'var(--color-text-secondary, #3D3D3A)',
              border: '1px solid var(--color-border-tertiary, #E0DFDB)',
              flexShrink: 0,
            }}
          >
            {thoughtCount}
          </span>
          <span className="sr-only" style={{ position: 'absolute', width: '1px', height: '1px', padding: 0, margin: '-1px', overflow: 'hidden', clip: 'rect(0, 0, 0, 0)', whiteSpace: 'nowrap', border: 0, lineHeight: 'var(--font-text-xs-line-height, 1.4)' }}>
            {thoughtCount} items
          </span>
        </span>
      </div>

      {/* Thoughts - using size="small" variant (OpenAI: ThoughtItem size="small") */}
      {sortedThoughts.length > 0 && (
        <ul
          role="list"
          style={{
            listStyle: 'none',
            margin: 0,
            padding: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: '3px', // inc 6 §3: subcluster thought list gap 4→3
          }}
        >
          {sortedThoughts.map((thought, index) => (
            <FullscreenThoughtItem
              key={`sub-thought-${index}`}
              thought={thought}
              size="small"
            />
          ))}
        </ul>
      )}

      {/* Tags LAST (OpenAI order: mt-auto pt-2) */}
      {hasTags && (
        <div
          role="list"
          aria-label="Suggested actions"
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '6px', // gap-1.5
            marginTop: 'auto',
            paddingTop: '6px', // inc 6 §3: tags padding-top (subcluster) 8→6
          }}
        >
          {subcluster.tags!.map((tag) => (
            <TagPill key={tag} tag={tag} />
          ))}
        </div>
      )}
    </div>
  )
}

export default App
