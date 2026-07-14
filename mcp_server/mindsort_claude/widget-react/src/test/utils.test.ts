/**
 * Unit Tests for MindSort Claude Widget Utils
 *
 * These tests verify the pure utility functions used by the widget.
 * Each test documents "what bug would still pass this test?"
 */
import { describe, it, expect } from 'vitest'
import {
  normalizeThoughtItem,
  truncateText,
  rankToNumber,
  extractOwnLevelPriorities,
  getTotalThoughtCount,
  sortClustersForOverview,
  truncateClusters,
} from '../utils'
import type { Cluster, ThoughtItem } from '../types'

describe('normalizeThoughtItem', () => {
  it('converts bare string to ThoughtItem object', () => {
    // Bug that would pass: not handling string case
    const result = normalizeThoughtItem('hello')
    expect(result).toEqual({ text: 'hello' })
    expect(result.priority).toBeUndefined()
  })

  it('passes through object items unchanged', () => {
    // Bug that would pass: modifying the object
    const item: ThoughtItem = { text: 'test', priority: { rank: 'P1' } }
    const result = normalizeThoughtItem(item)
    expect(result).toBe(item) // Same reference
    expect(result.priority?.rank).toBe('P1')
  })
})

describe('truncateText', () => {
  it('returns short text unchanged', () => {
    // Bug that would pass: always truncating
    expect(truncateText('short', 80)).toBe('short')
  })

  it('truncates long text with ellipsis', () => {
    // Bug that would pass: not adding ellipsis
    const longText = 'a'.repeat(100)
    const result = truncateText(longText, 80)
    expect(result.length).toBeLessThanOrEqual(83) // 80 + '...'
    expect(result.endsWith('...')).toBe(true)
  })

  it('handles undefined/empty gracefully', () => {
    // Bug that would pass: throwing on undefined
    expect(truncateText(undefined)).toBe('')
    expect(truncateText('')).toBe('')
  })
})

describe('rankToNumber', () => {
  it('returns correct numeric values for ranks', () => {
    // Bug that would pass: wrong ordering
    expect(rankToNumber('P1')).toBe(1)
    expect(rankToNumber('P2')).toBe(2)
    expect(rankToNumber('P3')).toBe(3)
    expect(rankToNumber(null)).toBe(999)
    expect(rankToNumber(undefined)).toBe(999)
  })

  it('P1 < P2 < P3 for sorting', () => {
    // Bug that would pass: inverted order
    expect(rankToNumber('P1')).toBeLessThan(rankToNumber('P2'))
    expect(rankToNumber('P2')).toBeLessThan(rankToNumber('P3'))
    expect(rankToNumber('P3')).toBeLessThan(rankToNumber(null))
  })
})

describe('extractOwnLevelPriorities', () => {
  // Test 1: Own-level priorities only
  it('extracts own-level priorities from cluster, subcluster, and thought item', () => {
    // Bug that would pass: using getEffectiveRank (would roll up child to parent)
    const clusters: Cluster[] = [
      {
        cluster_name: 'Cluster with P1',
        sum_thought_items: 5,
        priority: { rank: 'P1' },
        subclusters: [
          {
            subcluster_name: 'Sub with P2',
            sum_thought_items: 3,
            priority: { rank: 'P2' },
            thought_items: [
              { text: 'Item with P3', priority: { rank: 'P3' } },
            ],
          },
        ],
      },
    ]

    const priorities = extractOwnLevelPriorities(clusters)

    expect(priorities).toHaveLength(3)

    // Verify each priority is attached to the correct entity
    expect(priorities[0]).toEqual({
      rank: 'P1',
      text: 'Cluster with P1',
      breadcrumb: null,
      entityType: 'cluster',
    })
    expect(priorities[1]).toEqual({
      rank: 'P2',
      text: 'Sub with P2',
      breadcrumb: 'Cluster with P1',
      entityType: 'subcluster',
    })
    expect(priorities[2]).toEqual({
      rank: 'P3',
      text: 'Item with P3',
      breadcrumb: 'Cluster with P1 › Sub with P2',
      entityType: 'thought_item',
    })
  })

  // Test 2: String thought-item safety
  it('handles bare string thought items without crashing', () => {
    // Bug that would pass: assuming all items have .priority (crash on string.priority)
    const clusters: Cluster[] = [
      {
        cluster_name: 'Test Cluster',
        sum_thought_items: 4,
        thought_items: [
          'bare string 1',
          'bare string 2',
          { text: 'object with priority', priority: { rank: 'P1' } },
          { text: 'object without priority' },
        ],
      },
    ]

    const priorities = extractOwnLevelPriorities(clusters)

    // Only the object with priority should be extracted
    expect(priorities).toHaveLength(1)
    expect(priorities[0].text).toBe('object with priority')
  })

  // Test 3: Defensive rank handling - duplicate ranks
  it('handles duplicate ranks without crashing or dropping', () => {
    // Bug that would pass: using rank as unique key (Map<Rank, Entity>)
    const clusters: Cluster[] = [
      {
        cluster_name: 'First P1',
        sum_thought_items: 1,
        priority: { rank: 'P1' },
      },
      {
        cluster_name: 'Second P1',
        sum_thought_items: 1,
        priority: { rank: 'P1' },
      },
    ]

    const priorities = extractOwnLevelPriorities(clusters)

    // MUST have both P1s
    expect(priorities).toHaveLength(2)
    expect(priorities.every(p => p.rank === 'P1')).toBe(true)
    expect(priorities.map(p => p.text)).toContain('First P1')
    expect(priorities.map(p => p.text)).toContain('Second P1')
  })

  // Test 3b: Defensive rank handling - more than 3 priorities
  it('handles more than 3 priorities without crashing', () => {
    // Bug that would pass: assuming max 3, array bounds error
    const clusters: Cluster[] = [
      { cluster_name: 'C1', sum_thought_items: 1, priority: { rank: 'P1' } },
      { cluster_name: 'C2', sum_thought_items: 1, priority: { rank: 'P1' } },
      { cluster_name: 'C3', sum_thought_items: 1, priority: { rank: 'P2' } },
      { cluster_name: 'C4', sum_thought_items: 1, priority: { rank: 'P3' } },
      { cluster_name: 'C5', sum_thought_items: 1, priority: { rank: 'P3' } },
    ]

    const priorities = extractOwnLevelPriorities(clusters)

    expect(priorities).toHaveLength(5)
  })

  // Test 4: Sort order
  it('sorts priorities P1 -> P2 -> P3', () => {
    // Bug that would pass: not sorting, or wrong sort order
    const clusters: Cluster[] = [
      { cluster_name: 'P3 Cluster', sum_thought_items: 1, priority: { rank: 'P3' } },
      { cluster_name: 'P1 Cluster', sum_thought_items: 1, priority: { rank: 'P1' } },
      { cluster_name: 'P2 Cluster', sum_thought_items: 1, priority: { rank: 'P2' } },
    ]

    const priorities = extractOwnLevelPriorities(clusters)

    expect(priorities[0].rank).toBe('P1')
    expect(priorities[1].rank).toBe('P2')
    expect(priorities[2].rank).toBe('P3')
  })

  // Test 5: Breadcrumb derivation
  it('derives correct breadcrumbs for each entity type', () => {
    // Bug that would pass: wrong breadcrumb path
    const clusters: Cluster[] = [
      {
        cluster_name: 'Work',
        sum_thought_items: 3,
        priority: { rank: 'P1' },
        subclusters: [
          {
            subcluster_name: 'Fundraising',
            sum_thought_items: 2,
            priority: { rank: 'P2' },
            thought_items: [
              { text: 'Email investor deck', priority: { rank: 'P3' } },
            ],
          },
        ],
      },
    ]

    const priorities = extractOwnLevelPriorities(clusters)

    // Cluster -> no breadcrumb
    expect(priorities[0].breadcrumb).toBeNull()
    expect(priorities[0].entityType).toBe('cluster')

    // Subcluster -> cluster name
    expect(priorities[1].breadcrumb).toBe('Work')
    expect(priorities[1].entityType).toBe('subcluster')

    // Thought item -> cluster › subcluster
    expect(priorities[2].breadcrumb).toBe('Work › Fundraising')
    expect(priorities[2].entityType).toBe('thought_item')
  })

  // Test 6: Empty state
  it('returns empty array when no priorities exist', () => {
    // Bug that would pass: returning undefined or throwing
    const clusters: Cluster[] = [
      { cluster_name: 'Unprioritized', sum_thought_items: 5 },
      { cluster_name: 'Also Unprioritized', sum_thought_items: 3 },
    ]

    const priorities = extractOwnLevelPriorities(clusters)

    expect(priorities).toEqual([])
  })

  it('returns empty array for empty clusters', () => {
    const priorities = extractOwnLevelPriorities([])
    expect(priorities).toEqual([])
  })

  // Test: Direct thought items in cluster (not in subcluster)
  it('extracts priorities from direct thought items in cluster', () => {
    // Bug that would pass: only checking subclusters
    const clusters: Cluster[] = [
      {
        cluster_name: 'Parent',
        sum_thought_items: 2,
        thought_items: [
          { text: 'Direct P1 item', priority: { rank: 'P1' } },
        ],
      },
    ]

    const priorities = extractOwnLevelPriorities(clusters)

    expect(priorities).toHaveLength(1)
    expect(priorities[0].text).toBe('Direct P1 item')
    expect(priorities[0].breadcrumb).toBe('Parent')
  })

  // Gap 1: Direct item breadcrumb when subclusters are ALSO present
  it('direct thought item has simple breadcrumb even with subcluster siblings', () => {
    // Bug that would pass: wrong breadcrumb for direct item when subclusters exist
    // The code processes subclusters before direct items; this pins the correct breadcrumb.
    const clusters: Cluster[] = [
      {
        cluster_name: 'Work',
        sum_thought_items: 5,
        subclusters: [
          {
            subcluster_name: 'Meetings',
            sum_thought_items: 2,
            priority: { rank: 'P2' },
          },
        ],
        thought_items: [
          { text: 'Direct task', priority: { rank: 'P1' } },
        ],
      },
    ]

    const priorities = extractOwnLevelPriorities(clusters)

    // After sorting: P1 (direct item) first, then P2 (subcluster)
    expect(priorities).toHaveLength(2)
    expect(priorities[0].rank).toBe('P1')
    expect(priorities[0].text).toBe('Direct task')
    // Direct item breadcrumb is just 'Work', NOT 'Work › Meetings'
    expect(priorities[0].breadcrumb).toBe('Work')
    expect(priorities[0].entityType).toBe('thought_item')

    // Subcluster has its own breadcrumb
    expect(priorities[1].rank).toBe('P2')
    expect(priorities[1].breadcrumb).toBe('Work')
    expect(priorities[1].entityType).toBe('subcluster')
  })
})

describe('getTotalThoughtCount', () => {
  // Test 7: Counts
  it('sums thought counts from all clusters', () => {
    // Bug that would pass: re-walking tree instead of using sum_thought_items
    const clusters: Cluster[] = [
      { cluster_name: 'A', sum_thought_items: 10 },
      { cluster_name: 'B', sum_thought_items: 7 },
      { cluster_name: 'C', sum_thought_items: 25 },
    ]

    expect(getTotalThoughtCount(clusters)).toBe(42)
  })

  it('handles clusters with missing sum_thought_items', () => {
    // Bug that would pass: throwing on undefined
    const clusters: Cluster[] = [
      { cluster_name: 'A', sum_thought_items: 10 },
      { cluster_name: 'B' } as Cluster, // Missing sum_thought_items
    ]

    expect(getTotalThoughtCount(clusters)).toBe(10)
  })

  it('returns 0 for empty clusters', () => {
    expect(getTotalThoughtCount([])).toBe(0)
  })
})

// Test 8: Truncation (already covered in truncateText tests above)

// ============================================================================
// Tests for cluster overview helpers (inc_inline_card_cluster_overview)
// ============================================================================

describe('sortClustersForOverview', () => {
  // Test 1: Prioritized-first ordering (P1 → P2 → P3, then unprioritized)
  it('sorts prioritized clusters before unprioritized', () => {
    // Bug that would pass: sorting only by size (ignoring priority)
    const clusters: Cluster[] = [
      { cluster_name: 'Big Unprioritized', sum_thought_items: 100 },
      { cluster_name: 'P2 Cluster', sum_thought_items: 5, priority: { rank: 'P2' } },
      { cluster_name: 'P1 Cluster', sum_thought_items: 3, priority: { rank: 'P1' } },
    ]

    const sorted = sortClustersForOverview(clusters)

    expect(sorted[0].cluster_name).toBe('P1 Cluster')
    expect(sorted[1].cluster_name).toBe('P2 Cluster')
    expect(sorted[2].cluster_name).toBe('Big Unprioritized')
  })

  it('sorts P1 → P2 → P3 within prioritized clusters', () => {
    // Bug that would pass: inverted priority order
    const clusters: Cluster[] = [
      { cluster_name: 'P3', sum_thought_items: 1, priority: { rank: 'P3' } },
      { cluster_name: 'P1', sum_thought_items: 1, priority: { rank: 'P1' } },
      { cluster_name: 'P2', sum_thought_items: 1, priority: { rank: 'P2' } },
    ]

    const sorted = sortClustersForOverview(clusters)

    expect(sorted.map(c => c.cluster_name)).toEqual(['P1', 'P2', 'P3'])
  })

  it('sorts unprioritized clusters by sum_thought_items descending', () => {
    // Bug that would pass: sorting ascending or not sorting unprioritized tail
    const clusters: Cluster[] = [
      { cluster_name: 'Small', sum_thought_items: 3 },
      { cluster_name: 'Large', sum_thought_items: 50 },
      { cluster_name: 'Medium', sum_thought_items: 15 },
    ]

    const sorted = sortClustersForOverview(clusters)

    expect(sorted.map(c => c.cluster_name)).toEqual(['Large', 'Medium', 'Small'])
  })

  // Test 2: Edge cases - no priorities (pure size-desc)
  it('handles all unprioritized clusters (pure size-desc)', () => {
    // Bug that would pass: crashing on no priorities
    const clusters: Cluster[] = [
      { cluster_name: 'A', sum_thought_items: 10 },
      { cluster_name: 'B', sum_thought_items: 50 },
      { cluster_name: 'C', sum_thought_items: 25 },
    ]

    const sorted = sortClustersForOverview(clusters)

    expect(sorted.map(c => c.cluster_name)).toEqual(['B', 'C', 'A'])
  })

  // Test 2b: Edge case - all prioritized
  it('handles all prioritized clusters', () => {
    // Bug that would pass: assuming some unprioritized always exist
    const clusters: Cluster[] = [
      { cluster_name: 'P2', sum_thought_items: 1, priority: { rank: 'P2' } },
      { cluster_name: 'P1', sum_thought_items: 1, priority: { rank: 'P1' } },
    ]

    const sorted = sortClustersForOverview(clusters)

    expect(sorted.map(c => c.cluster_name)).toEqual(['P1', 'P2'])
  })

  // Test 2c: Edge case - duplicate ranks
  it('handles duplicate ranks (secondary sort by size)', () => {
    // Bug that would pass: using rank as unique key
    const clusters: Cluster[] = [
      { cluster_name: 'Small P1', sum_thought_items: 5, priority: { rank: 'P1' } },
      { cluster_name: 'Large P1', sum_thought_items: 50, priority: { rank: 'P1' } },
    ]

    const sorted = sortClustersForOverview(clusters)

    // Same rank → larger first
    expect(sorted[0].cluster_name).toBe('Large P1')
    expect(sorted[1].cluster_name).toBe('Small P1')
  })

  // Test 2d: Edge case - more than 3 priorities
  it('handles more than 3 prioritized clusters', () => {
    // Bug that would pass: assuming max 3 priorities
    const clusters: Cluster[] = [
      { cluster_name: 'C1', sum_thought_items: 1, priority: { rank: 'P1' } },
      { cluster_name: 'C2', sum_thought_items: 2, priority: { rank: 'P1' } },
      { cluster_name: 'C3', sum_thought_items: 1, priority: { rank: 'P2' } },
      { cluster_name: 'C4', sum_thought_items: 1, priority: { rank: 'P3' } },
      { cluster_name: 'C5', sum_thought_items: 2, priority: { rank: 'P3' } },
    ]

    const sorted = sortClustersForOverview(clusters)

    expect(sorted).toHaveLength(5)
    // P1s first (larger first within rank), then P2, then P3s (larger first)
    expect(sorted[0].cluster_name).toBe('C2') // P1, 2 items
    expect(sorted[1].cluster_name).toBe('C1') // P1, 1 item
    expect(sorted[2].cluster_name).toBe('C3') // P2
    expect(sorted[3].cluster_name).toBe('C5') // P3, 2 items
    expect(sorted[4].cluster_name).toBe('C4') // P3, 1 item
  })

  it('returns empty array for empty input', () => {
    expect(sortClustersForOverview([])).toEqual([])
  })

  it('does not mutate original array', () => {
    // Bug that would pass: in-place sort
    const clusters: Cluster[] = [
      { cluster_name: 'B', sum_thought_items: 1 },
      { cluster_name: 'A', sum_thought_items: 10 },
    ]
    const original = [...clusters]

    sortClustersForOverview(clusters)

    expect(clusters).toEqual(original) // Unchanged
  })
})

describe('truncateClusters', () => {
  const MAX_ROWS = 5

  // Test 3: No overflow case
  it('returns all clusters when count <= maxRows', () => {
    // Bug that would pass: always truncating
    const clusters: Cluster[] = [
      { cluster_name: 'A', sum_thought_items: 1 },
      { cluster_name: 'B', sum_thought_items: 2 },
      { cluster_name: 'C', sum_thought_items: 3 },
    ]

    const result = truncateClusters(clusters, MAX_ROWS)

    expect(result.visible).toHaveLength(3)
    expect(result.overflow).toBe(0)
  })

  it('returns all clusters when count equals maxRows exactly', () => {
    // Bug that would pass: off-by-one (truncating at exact boundary)
    const clusters: Cluster[] = Array.from({ length: 5 }, (_, i) => ({
      cluster_name: `C${i}`,
      sum_thought_items: i,
    }))

    const result = truncateClusters(clusters, MAX_ROWS)

    expect(result.visible).toHaveLength(5)
    expect(result.overflow).toBe(0)
  })

  // Test 3b: Overflow case
  it('truncates when count > maxRows', () => {
    // Bug that would pass: not truncating
    const clusters: Cluster[] = Array.from({ length: 8 }, (_, i) => ({
      cluster_name: `C${i}`,
      sum_thought_items: i,
    }))

    const result = truncateClusters(clusters, MAX_ROWS)

    expect(result.visible).toHaveLength(5)
    expect(result.overflow).toBe(3) // 8 - 5 = 3
  })

  it('preserves order of visible clusters', () => {
    // Bug that would pass: reordering during truncation
    const clusters: Cluster[] = [
      { cluster_name: 'First', sum_thought_items: 1 },
      { cluster_name: 'Second', sum_thought_items: 2 },
      { cluster_name: 'Third', sum_thought_items: 3 },
      { cluster_name: 'Fourth', sum_thought_items: 4 },
      { cluster_name: 'Fifth', sum_thought_items: 5 },
      { cluster_name: 'Sixth', sum_thought_items: 6 },
    ]

    const result = truncateClusters(clusters, MAX_ROWS)

    expect(result.visible.map(c => c.cluster_name)).toEqual([
      'First', 'Second', 'Third', 'Fourth', 'Fifth'
    ])
  })

  it('returns empty visible array for empty input', () => {
    const result = truncateClusters([], MAX_ROWS)

    expect(result.visible).toEqual([])
    expect(result.overflow).toBe(0)
  })

  // Ensures row cap guarantees 500px limit
  it('never returns more than maxRows visible clusters', () => {
    // Bug that would pass: a cap set higher than measured budget
    const clusters: Cluster[] = Array.from({ length: 100 }, (_, i) => ({
      cluster_name: `C${i}`,
      sum_thought_items: i,
    }))

    const result = truncateClusters(clusters, MAX_ROWS)

    expect(result.visible.length).toBeLessThanOrEqual(MAX_ROWS)
    expect(result.overflow).toBe(95) // 100 - 5
  })
})

// Meta test: Verify getEffectiveRank is NOT in utils
describe('forbidden functions', () => {
  it('does NOT export getEffectiveRank', async () => {
    // Bug that would pass: using getEffectiveRank for extraction
    const utils = await import('../utils')
    expect('getEffectiveRank' in utils).toBe(false)
  })

  it('does NOT export getEffectiveSubclusterRank', async () => {
    const utils = await import('../utils')
    expect('getEffectiveSubclusterRank' in utils).toBe(false)
  })
})
