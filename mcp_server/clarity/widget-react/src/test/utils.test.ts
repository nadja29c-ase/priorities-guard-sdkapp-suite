import { describe, it, expect } from 'vitest'
import { sortClustersByPriority, sortSubclustersByPriority, truncateText } from '../utils'
import type { Cluster, Subcluster } from '../types'

describe('sortClustersByPriority', () => {
  it('sorts P1 first, then P2, P3, then unprioritized', () => {
    const clusters: Cluster[] = [
      { cluster_name: 'No Priority', sum_thought_items: 1 },
      { cluster_name: 'P3 Task', sum_thought_items: 1, priority: { rank: 'P3' } },
      { cluster_name: 'P1 Task', sum_thought_items: 1, priority: { rank: 'P1' } },
      { cluster_name: 'P2 Task', sum_thought_items: 1, priority: { rank: 'P2' } },
    ]

    const sorted = sortClustersByPriority(clusters)

    expect(sorted[0].cluster_name).toBe('P1 Task')
    expect(sorted[1].cluster_name).toBe('P2 Task')
    expect(sorted[2].cluster_name).toBe('P3 Task')
    expect(sorted[3].cluster_name).toBe('No Priority')
  })

  it('considers subcluster priorities for effective rank', () => {
    const clusters: Cluster[] = [
      { cluster_name: 'No Priority', sum_thought_items: 1 },
      {
        cluster_name: 'Has P1 Subcluster',
        sum_thought_items: 2,
        subclusters: [
          { subcluster_name: 'Sub', sum_thought_items: 1, priority: { rank: 'P1' } },
        ],
      },
    ]

    const sorted = sortClustersByPriority(clusters)

    expect(sorted[0].cluster_name).toBe('Has P1 Subcluster')
    expect(sorted[1].cluster_name).toBe('No Priority')
  })

  it('does not mutate original array', () => {
    const original: Cluster[] = [
      { cluster_name: 'B', sum_thought_items: 1, priority: { rank: 'P2' } },
      { cluster_name: 'A', sum_thought_items: 1, priority: { rank: 'P1' } },
    ]

    const sorted = sortClustersByPriority(original)

    expect(original[0].cluster_name).toBe('B')
    expect(sorted[0].cluster_name).toBe('A')
  })
})

describe('sortSubclustersByPriority', () => {
  it('sorts subclusters by priority rank', () => {
    const subclusters: Subcluster[] = [
      { subcluster_name: 'No Priority', sum_thought_items: 1 },
      { subcluster_name: 'P2', sum_thought_items: 1, priority: { rank: 'P2' } },
      { subcluster_name: 'P1', sum_thought_items: 1, priority: { rank: 'P1' } },
    ]

    const sorted = sortSubclustersByPriority(subclusters)

    expect(sorted[0].subcluster_name).toBe('P1')
    expect(sorted[1].subcluster_name).toBe('P2')
    expect(sorted[2].subcluster_name).toBe('No Priority')
  })
})

describe('truncateText', () => {
  it('returns text unchanged if under limit', () => {
    expect(truncateText('short text', 80)).toBe('short text')
  })

  it('truncates text with ellipsis if over limit', () => {
    const longText = 'a'.repeat(100)
    const result = truncateText(longText, 80)

    expect(result.length).toBe(83) // 80 chars + '...'
    expect(result.endsWith('...')).toBe(true)
  })

  it('handles undefined gracefully', () => {
    expect(truncateText(undefined, 80)).toBe('')
  })

  it('handles empty string', () => {
    expect(truncateText('', 80)).toBe('')
  })
})
