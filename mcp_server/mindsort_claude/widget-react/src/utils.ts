/**
 * MindSort Claude Widget - Utilities
 *
 * Pure, platform-agnostic helpers.
 *
 * REUSED from clarity/widget-react/src/utils.ts:
 * - normalizeThoughtItem
 * - truncateText
 * - rankToNumber
 * - getBestThoughtItemRank, getEffectiveSubclusterRank, getEffectiveRank (inc 5)
 * - sortSubclustersByPriority (inc 5)
 *
 * NOT PORTED (OpenAI-specific):
 * - getToolOutput (window.openai)
 */

import type {
  Rank,
  ThoughtItem,
  ThoughtItemInput,
  Cluster,
  Subcluster,
} from './types'

/**
 * Normalize a thought item input to ThoughtItem object.
 * CRITICAL: Bare strings have no priority - always normalize before reading .priority.
 */
export function normalizeThoughtItem(item: ThoughtItemInput): ThoughtItem {
  if (typeof item === 'string') {
    return { text: item }
  }
  return item
}

/**
 * Truncate text with ellipsis for display.
 */
export function truncateText(text: string | undefined, maxLength = 80): string {
  if (!text || text.length <= maxLength) return text ?? ''
  return text.substring(0, maxLength).trim() + '...'
}

/**
 * Convert rank to numeric value for sorting.
 * P1 = 1, P2 = 2, P3 = 3, null/undefined = 999 (lowest)
 */
export function rankToNumber(rank: Rank | null | undefined): number {
  if (rank === 'P1') return 1
  if (rank === 'P2') return 2
  if (rank === 'P3') return 3
  return 999
}

// =============================================================================
// EFFECTIVE-RANK ORDERING (increment 5)
// =============================================================================
// Port of clarity/utils.ts effective-rank logic.
// Effective rank = min(own rank, best subcluster effective rank, best thought-item rank).
// This determines cluster/subcluster display order in BOTH inline and fullscreen.
//
// DESIGN DECISION: BADGES show OWN rank only. A cluster is only labeled P1 if
// explicitly prioritized — an inherited priority must not assert something the user
// never set. Matches OpenAI (ClusterCard uses cluster.priority?.rank for the badge,
// getEffectiveRank for sort). Tested in App.test.tsx "sorts first but shows no badge".
//
// Effective rank drives ORDER, and — since the condensed-row accent increment — also
// the LEFT-EDGE ACCENT on the condensed inline cluster row (App.tsx ClusterRowToggle),
// so a priority nested inside a collapsed cluster is visible at the top level. That
// accent is colour-only, so the inherited case also renders an sr-only text
// alternative. Accents elsewhere (subcluster rows, fullscreen cards) still read OWN
// rank. Do NOT "restore" the condensed row accent to own-rank — that reverts the fix.

/**
 * Get the best (highest priority / lowest number) rank among thought items.
 * Normalizes items first (bare strings have no priority).
 * Returns null if no items have a priority.
 */
export function getBestThoughtItemRank(items: ThoughtItemInput[]): Rank | null {
  let bestRank: Rank | null = null
  for (const item of items) {
    const normalized = normalizeThoughtItem(item)
    const itemRank = normalized.priority?.rank ?? null
    if (itemRank && (!bestRank || rankToNumber(itemRank) < rankToNumber(bestRank))) {
      bestRank = itemRank
    }
  }
  return bestRank
}

/**
 * Get effective rank for a subcluster.
 * Effective = min(own rank, best thought-item rank).
 * Returns null if neither exists.
 */
export function getEffectiveSubclusterRank(subcluster: Subcluster): Rank | null {
  const ownRank = subcluster.priority?.rank ?? null
  const bestItemRank = getBestThoughtItemRank(subcluster.thought_items ?? [])

  if (!ownRank && !bestItemRank) return null
  if (!ownRank) return bestItemRank
  if (!bestItemRank) return ownRank
  return rankToNumber(ownRank) <= rankToNumber(bestItemRank) ? ownRank : bestItemRank
}

/**
 * Get effective rank for a cluster.
 * Effective = min(own rank, best subcluster effective rank, best direct thought-item rank).
 * Returns null if none exist.
 */
export function getEffectiveRank(cluster: Cluster): Rank | null {
  const ownRank = cluster.priority?.rank ?? null
  const bestDirectItemRank = getBestThoughtItemRank(cluster.thought_items ?? [])

  // Best effective rank from subclusters
  let bestSubclusterRank: Rank | null = null
  for (const sub of cluster.subclusters ?? []) {
    const subEffectiveRank = getEffectiveSubclusterRank(sub)
    if (subEffectiveRank && (!bestSubclusterRank || rankToNumber(subEffectiveRank) < rankToNumber(bestSubclusterRank))) {
      bestSubclusterRank = subEffectiveRank
    }
  }

  // Find the best among all sources
  const candidates = [ownRank, bestSubclusterRank, bestDirectItemRank].filter((r): r is Rank => r !== null)
  if (candidates.length === 0) return null

  return candidates.reduce((best, current) =>
    rankToNumber(current) < rankToNumber(best) ? current : best
  )
}

/**
 * Sort subclusters by effective rank (P1 → P2 → P3 → unranked).
 * No size tiebreaker (matches OpenAI; no established Claude behavior to preserve).
 *
 * SHARED: Used by both inline (extractDetailUnits) and fullscreen (FullscreenClusterCard).
 */
export function sortSubclustersByPriority(subclusters: Subcluster[]): Subcluster[] {
  return [...subclusters].sort((a, b) => {
    return rankToNumber(getEffectiveSubclusterRank(a)) - rankToNumber(getEffectiveSubclusterRank(b))
  })
}

/**
 * Calculate total thought count from clusters.
 * Uses sum_thought_items field (precomputed by enrich_clusters).
 */
export function getTotalThoughtCount(clusters: Cluster[]): number {
  return clusters.reduce((sum, c) => sum + (c.sum_thought_items ?? 0), 0)
}

/**
 * Sort clusters by EFFECTIVE rank for display (BOTH inline and fullscreen).
 *
 * Effective rank = min(own rank, best subcluster effective rank, best thought-item rank).
 * A cluster with no own rank but containing a P1 thought sorts as P1.
 *
 * Ordering: Effective rank ASC (P1 → P2 → P3 → unranked), then sum_thought_items DESC.
 *
 * INTENTIONAL DEVIATION from OpenAI: Claude keeps the size tiebreaker for equal-rank
 * clusters (larger first). OpenAI has no tiebreaker (array order). Decided in inc 5.
 *
 * SHARED: Used by BOTH inline and fullscreen via the single view-model.
 */
export function sortClustersForOverview(clusters: Cluster[]): Cluster[] {
  return [...clusters].sort((a, b) => {
    const rankA = rankToNumber(getEffectiveRank(a))
    const rankB = rankToNumber(getEffectiveRank(b))

    // Primary: effective rank (lower number = higher priority)
    if (rankA !== rankB) {
      return rankA - rankB
    }

    // Secondary (for equal effective rank): larger thought count first
    // INTENTIONAL DEVIATION: OpenAI has no tiebreaker; Claude sorts by size.
    const countA = a.sum_thought_items ?? 0
    const countB = b.sum_thought_items ?? 0
    return countB - countA
  })
}

/**
 * Truncate cluster list to fit MAX_INLINE_ROWS.
 *
 * Returns:
 * - visible: clusters to render (up to maxRows)
 * - overflow: number of hidden clusters (for "+N more" display)
 */
export function truncateClusters(
  clusters: Cluster[],
  maxRows: number
): { visible: Cluster[]; overflow: number } {
  if (clusters.length <= maxRows) {
    return { visible: clusters, overflow: 0 }
  }
  return {
    visible: clusters.slice(0, maxRows),
    overflow: clusters.length - maxRows,
  }
}

// =============================================================================
// SHARED VIEW-MODEL HELPERS (increment 2)
// =============================================================================
// These helpers ensure ONE model for both inline and fullscreen renderers.
// Do NOT duplicate this logic in components — call these helpers.

/**
 * Sort thought items by priority (P1 → P2 → P3 → unprioritized).
 * Normalizes items first (bare strings have no priority).
 *
 * SHARED: Used by both inline (extractDetailUnits) and fullscreen (FullscreenClusterCard,
 * FullscreenSubclusterCard). Do NOT duplicate this sort in components.
 */
export function sortThoughtsByPriority(items: ThoughtItemInput[]): ThoughtItem[] {
  const normalized = items.map(normalizeThoughtItem)
  return [...normalized].sort((a, b) => {
    return rankToNumber(a.priority?.rank) - rankToNumber(b.priority?.rank)
  })
}

/**
 * Rank color tokens for priority badges.
 * Uses Claude host tokens with hex fallbacks matching the compliance master.
 *
 * SHARED: Used by inline and fullscreen components. Do NOT duplicate these definitions.
 */
export const RANK_COLORS: Record<Rank, { bg: string; text: string; border: string }> = {
  P1: {
    bg: 'var(--color-background-danger, #FEE2E2)',
    text: 'var(--color-text-danger, #991B1B)',
    border: 'var(--color-border-danger, #DC2626)',
  },
  P2: {
    bg: 'var(--color-background-warning, #FEF3C7)',
    text: 'var(--color-text-warning, #92400E)',
    border: 'var(--color-border-warning, #D97706)',
  },
  P3: {
    bg: 'var(--color-background-info, #DBEAFE)',
    text: 'var(--color-text-info, #1E40AF)',
    border: 'var(--color-border-info, #3B82F6)',
  },
}
