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
