import type { Cluster, Rank, Subcluster } from './types'

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
 * Priority ranking: P1 < P2 < P3 < null (lower = higher priority)
 */
function rankToNumber(rank: Rank | null | undefined): number {
  if (rank === 'P1') return 1
  if (rank === 'P2') return 2
  if (rank === 'P3') return 3
  return 999 // null/undefined = lowest priority
}

/**
 * Get effective rank for a cluster (min of own rank and best subcluster rank)
 */
function getEffectiveRank(cluster: Cluster): Rank | null {
  const ownRank = cluster.priority?.rank ?? null
  const subclusters = cluster.subclusters ?? []

  let bestSubclusterRank: Rank | null = null
  for (const sub of subclusters) {
    const subRank = sub.priority?.rank ?? null
    if (subRank && (!bestSubclusterRank || rankToNumber(subRank) < rankToNumber(bestSubclusterRank))) {
      bestSubclusterRank = subRank
    }
  }

  // Return whichever is higher priority (lower number)
  if (!ownRank && !bestSubclusterRank) return null
  if (!ownRank) return bestSubclusterRank
  if (!bestSubclusterRank) return ownRank
  return rankToNumber(ownRank) <= rankToNumber(bestSubclusterRank) ? ownRank : bestSubclusterRank
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
 * Sort subclusters by own rank
 */
export function sortSubclustersByPriority(subclusters: Subcluster[]): Subcluster[] {
  return [...subclusters].sort((a, b) => {
    const rankA = rankToNumber(a.priority?.rank ?? null)
    const rankB = rankToNumber(b.priority?.rank ?? null)
    return rankA - rankB
  })
}
