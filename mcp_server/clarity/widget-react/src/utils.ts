import type { Cluster, Rank, Subcluster, ThoughtItem, ThoughtItemInput } from './types'

/**
 * Extract structuredContent from callTool result (tries multiple paths)
 */
export function extractStructuredContent<T>(result: unknown): T | undefined {
  if (!result || typeof result !== 'object') return undefined
  const r = result as Record<string, unknown>

  // Try: result.structuredContent
  if (r.structuredContent !== undefined) {
    return r.structuredContent as T
  }
  // Try: result.result.structuredContent
  if (r.result && typeof r.result === 'object') {
    const inner = r.result as Record<string, unknown>
    if (inner.structuredContent !== undefined) {
      return inner.structuredContent as T
    }
  }
  return undefined
}

/**
 * Get clusters from window.openai.toolOutput (tries multiple paths)
 */
export function getToolOutput(): Cluster[] {
  const t = window.openai?.toolOutput
  if (!t) return []

  // Try all known paths for clusters
  if (Array.isArray(t.result?.structuredContent?.clusters)) {
    return t.result.structuredContent.clusters
  } else if (Array.isArray(t.structuredContent?.clusters)) {
    return t.structuredContent.clusters
  } else if (Array.isArray(t.clusters)) {
    return t.clusters
  } else if (Array.isArray(t.data?.clusters)) {
    return t.data.clusters
  }
  return []
}

/**
 * Truncate text with ellipsis
 */
export function truncateText(text: string | undefined, maxLength = 80): string {
  if (!text || text.length <= maxLength) return text ?? ''
  return text.substring(0, maxLength).trim() + '...'
}

/**
 * Normalize a thought item input to ThoughtItem object
 */
export function normalizeThoughtItem(item: ThoughtItemInput): ThoughtItem {
  if (typeof item === 'string') {
    return { text: item }
  }
  return item
}

/**
 * Priority ranking: P1 < P2 < P3 < null (lower = higher priority)
 */
export function rankToNumber(rank: Rank | null | undefined): number {
  if (rank === 'P1') return 1
  if (rank === 'P2') return 2
  if (rank === 'P3') return 3
  return 999 // null/undefined = lowest priority
}

/**
 * Sort thought items by priority (P1 first, then P2, P3, then unranked)
 */
export function sortThoughtItemsByPriority(items: ThoughtItem[]): ThoughtItem[] {
  return [...items].sort((a, b) => {
    const rankA = rankToNumber(a.priority?.rank ?? null)
    const rankB = rankToNumber(b.priority?.rank ?? null)
    return rankA - rankB
  })
}

/**
 * Get best rank from an array of thought items
 */
function getBestThoughtItemRank(items: ThoughtItem[]): Rank | null {
  let bestRank: Rank | null = null
  for (const item of items) {
    const itemRank = item.priority?.rank ?? null
    if (itemRank && (!bestRank || rankToNumber(itemRank) < rankToNumber(bestRank))) {
      bestRank = itemRank
    }
  }
  return bestRank
}

/**
 * Get effective rank for a subcluster (own rank or best thought item rank)
 */
export function getEffectiveSubclusterRank(subcluster: Subcluster): Rank | null {
  const ownRank = subcluster.priority?.rank ?? null
  const items = (subcluster.thought_items ?? []).map(normalizeThoughtItem)
  const bestItemRank = getBestThoughtItemRank(items)

  // Return whichever is higher priority (lower number)
  if (!ownRank && !bestItemRank) return null
  if (!ownRank) return bestItemRank
  if (!bestItemRank) return ownRank
  return rankToNumber(ownRank) <= rankToNumber(bestItemRank) ? ownRank : bestItemRank
}

/**
 * Get effective rank for a cluster (min of own rank, best subcluster rank, and best thought item rank)
 */
function getEffectiveRank(cluster: Cluster): Rank | null {
  const ownRank = cluster.priority?.rank ?? null
  const subclusters = cluster.subclusters ?? []
  const directItems = (cluster.thought_items ?? []).map(normalizeThoughtItem)

  // Best rank from direct thought items
  const bestDirectItemRank = getBestThoughtItemRank(directItems)

  // Best rank from subclusters (including their thought items)
  let bestSubclusterRank: Rank | null = null
  for (const sub of subclusters) {
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
 * Sort clusters by effective rank (P1 first, then P2, P3, then unranked)
 */
export function sortClustersByPriority(clusters: Cluster[]): Cluster[] {
  return [...clusters].sort((a, b) => {
    const rankA = rankToNumber(getEffectiveRank(a))
    const rankB = rankToNumber(getEffectiveRank(b))
    return rankA - rankB
  })
}

/**
 * Sort subclusters by effective rank (own rank or best child priority)
 */
export function sortSubclustersByPriority(subclusters: Subcluster[]): Subcluster[] {
  return [...subclusters].sort((a, b) => {
    const rankA = rankToNumber(getEffectiveSubclusterRank(a))
    const rankB = rankToNumber(getEffectiveSubclusterRank(b))
    return rankA - rankB
  })
}
