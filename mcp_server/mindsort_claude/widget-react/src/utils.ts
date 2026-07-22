/**
 * MindSort Claude Widget - Utilities
 *
 * Pure, platform-agnostic helpers.
 *
 * REUSED from clarity/widget-react/src/utils.ts:
 * - normalizeThoughtItem
 * - truncateText
 * - rankToNumber
 *
 * FORBIDDEN (not imported):
 * - getEffectiveRank / getEffectiveSubclusterRank (wrong semantic for inline summary)
 * - getToolOutput (OpenAI-specific)
 */

import type {
  Rank,
  ThoughtItem,
  ThoughtItemInput,
  Cluster,
  PrioritizedEntity,
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

/**
 * Extract all own-level prioritized entities from clusters.
 *
 * OWN-LEVEL ONLY: Walks the tree and collects entities whose own priority.rank is set.
 * Does NOT roll child priorities up to parents (no getEffectiveRank).
 *
 * Data Rule 4: Does NOT assume unique ranks or <=3 - handles duplicates and >3.
 * Returns all found priorities, sorted by rank (P1 first).
 */
export function extractOwnLevelPriorities(clusters: Cluster[]): PrioritizedEntity[] {
  const priorities: PrioritizedEntity[] = []

  for (const cluster of clusters) {
    // Check cluster's own priority
    if (cluster.priority?.rank) {
      priorities.push({
        rank: cluster.priority.rank,
        text: cluster.cluster_name,
        breadcrumb: null, // Clusters are top-level
        entityType: 'cluster',
      })
    }

    // Check subclusters' own priorities
    const subclusters = cluster.subclusters ?? []
    for (const subcluster of subclusters) {
      if (subcluster.priority?.rank) {
        priorities.push({
          rank: subcluster.priority.rank,
          text: subcluster.subcluster_name,
          breadcrumb: cluster.cluster_name,
          entityType: 'subcluster',
        })
      }

      // Check thought items in subcluster (normalize first!)
      const subItems = (subcluster.thought_items ?? []).map(normalizeThoughtItem)
      for (const item of subItems) {
        if (item.priority?.rank) {
          priorities.push({
            rank: item.priority.rank,
            text: item.text,
            breadcrumb: `${cluster.cluster_name} › ${subcluster.subcluster_name}`,
            entityType: 'thought_item',
          })
        }
      }
    }

    // Check direct thought items in cluster (normalize first!)
    const directItems = (cluster.thought_items ?? []).map(normalizeThoughtItem)
    for (const item of directItems) {
      if (item.priority?.rank) {
        priorities.push({
          rank: item.priority.rank,
          text: item.text,
          breadcrumb: cluster.cluster_name,
          entityType: 'thought_item',
        })
      }
    }
  }

  // Sort by rank: P1 first, then P2, then P3
  // Stable sort within same rank (preserves insertion order)
  return priorities.sort((a, b) => rankToNumber(a.rank) - rankToNumber(b.rank))
}

/**
 * Calculate total thought count from clusters.
 * Uses sum_thought_items field (precomputed by enrich_clusters).
 */
export function getTotalThoughtCount(clusters: Cluster[]): number {
  return clusters.reduce((sum, c) => sum + (c.sum_thought_items ?? 0), 0)
}

/**
 * Sort clusters for inline overview display.
 *
 * Ordering: Prioritized clusters first (P1 → P2 → P3), then unprioritized
 * by sum_thought_items descending (largest first).
 *
 * Data Rule 4: Does NOT assume unique ranks or <=3 priorities.
 * Handles duplicates and >3 prioritized clusters.
 */
export function sortClustersForOverview(clusters: Cluster[]): Cluster[] {
  return [...clusters].sort((a, b) => {
    const rankA = rankToNumber(a.priority?.rank)
    const rankB = rankToNumber(b.priority?.rank)

    // Primary: prioritized first (lower rank number = higher priority)
    if (rankA !== rankB) {
      return rankA - rankB
    }

    // Secondary (for unprioritized or same rank): larger thought count first
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
