import { describe, it, expect } from 'vitest'
import {
  sortClustersByPriority,
  sortSubclustersByPriority,
  sortThoughtItemsByPriority,
  normalizeThoughtItem,
  truncateText,
  getEffectiveSubclusterRank,
  rankToNumber,
} from '../utils'
import type { Cluster, Subcluster, ThoughtItem, ThoughtItemInput } from '../types'

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

describe('normalizeThoughtItem', () => {
  it('handles string input', () => {
    const result = normalizeThoughtItem('Test item')
    expect(result).toEqual({ text: 'Test item' })
  })

  it('handles object input without priority', () => {
    const input: ThoughtItemInput = { text: 'Object item' }
    const result = normalizeThoughtItem(input)
    expect(result).toEqual({ text: 'Object item' })
  })

  it('handles object input with priority', () => {
    const input: ThoughtItemInput = { text: 'Priority item', priority: { rank: 'P1' } }
    const result = normalizeThoughtItem(input)
    expect(result).toEqual({ text: 'Priority item', priority: { rank: 'P1' } })
  })

  it('preserves undefined priority in object input', () => {
    const input: ThoughtItemInput = { text: 'No priority', priority: undefined }
    const result = normalizeThoughtItem(input)
    expect(result.text).toBe('No priority')
    expect(result.priority).toBeUndefined()
  })
})

describe('sortThoughtItemsByPriority', () => {
  it('orders P1 → P2 → P3 → unranked', () => {
    const items: ThoughtItem[] = [
      { text: 'Unranked' },
      { text: 'P3 item', priority: { rank: 'P3' } },
      { text: 'P1 item', priority: { rank: 'P1' } },
      { text: 'P2 item', priority: { rank: 'P2' } },
    ]

    const sorted = sortThoughtItemsByPriority(items)

    expect(sorted[0].text).toBe('P1 item')
    expect(sorted[1].text).toBe('P2 item')
    expect(sorted[2].text).toBe('P3 item')
    expect(sorted[3].text).toBe('Unranked')
  })

  it('does not mutate original array', () => {
    const original: ThoughtItem[] = [
      { text: 'Second', priority: { rank: 'P2' } },
      { text: 'First', priority: { rank: 'P1' } },
    ]

    const sorted = sortThoughtItemsByPriority(original)

    expect(original[0].text).toBe('Second')
    expect(sorted[0].text).toBe('First')
  })

  it('handles empty array', () => {
    const sorted = sortThoughtItemsByPriority([])
    expect(sorted).toEqual([])
  })

  it('handles all unranked items', () => {
    const items: ThoughtItem[] = [
      { text: 'A' },
      { text: 'B' },
      { text: 'C' },
    ]

    const sorted = sortThoughtItemsByPriority(items)

    // Order should be preserved for items with same (no) priority
    expect(sorted[0].text).toBe('A')
    expect(sorted[1].text).toBe('B')
    expect(sorted[2].text).toBe('C')
  })
})

describe('getEffectiveSubclusterRank', () => {
  it('returns own rank when no thought items have priority', () => {
    const subcluster: Subcluster = {
      subcluster_name: 'Test',
      sum_thought_items: 2,
      priority: { rank: 'P2' },
      thought_items: ['item1', 'item2'],
    }

    expect(getEffectiveSubclusterRank(subcluster)).toBe('P2')
  })

  it('returns null when no priority anywhere', () => {
    const subcluster: Subcluster = {
      subcluster_name: 'Test',
      sum_thought_items: 1,
      thought_items: ['item'],
    }

    expect(getEffectiveSubclusterRank(subcluster)).toBeNull()
  })

  it('returns thought item priority when subcluster has none', () => {
    const subcluster: Subcluster = {
      subcluster_name: 'Test',
      sum_thought_items: 1,
      thought_items: [{ text: 'item', priority: { rank: 'P1' } }],
    }

    expect(getEffectiveSubclusterRank(subcluster)).toBe('P1')
  })

  it('returns best priority between own and thought items', () => {
    const subcluster: Subcluster = {
      subcluster_name: 'Test',
      sum_thought_items: 2,
      priority: { rank: 'P3' },
      thought_items: [
        { text: 'item1', priority: { rank: 'P1' } },
        'item2',
      ],
    }

    expect(getEffectiveSubclusterRank(subcluster)).toBe('P1')
  })

  it('returns own rank when it beats thought item ranks', () => {
    const subcluster: Subcluster = {
      subcluster_name: 'Test',
      sum_thought_items: 1,
      priority: { rank: 'P1' },
      thought_items: [{ text: 'item', priority: { rank: 'P3' } }],
    }

    expect(getEffectiveSubclusterRank(subcluster)).toBe('P1')
  })
})

describe('rankToNumber', () => {
  it('returns 1 for P1', () => {
    expect(rankToNumber('P1')).toBe(1)
  })

  it('returns 2 for P2', () => {
    expect(rankToNumber('P2')).toBe(2)
  })

  it('returns 3 for P3', () => {
    expect(rankToNumber('P3')).toBe(3)
  })

  it('returns 999 for null', () => {
    expect(rankToNumber(null)).toBe(999)
  })

  it('returns 999 for undefined', () => {
    expect(rankToNumber(undefined)).toBe(999)
  })
})

describe('sortClustersByPriority with thought item priorities', () => {
  it('considers thought item priorities in effective rank', () => {
    const clusters: Cluster[] = [
      {
        cluster_name: 'No Priority',
        sum_thought_items: 1,
        thought_items: ['plain item'],
      },
      {
        cluster_name: 'Has P1 Item',
        sum_thought_items: 1,
        thought_items: [{ text: 'important', priority: { rank: 'P1' } }],
      },
    ]

    const sorted = sortClustersByPriority(clusters)

    expect(sorted[0].cluster_name).toBe('Has P1 Item')
    expect(sorted[1].cluster_name).toBe('No Priority')
  })

  it('considers subcluster thought item priorities', () => {
    const clusters: Cluster[] = [
      { cluster_name: 'No Priority', sum_thought_items: 1 },
      {
        cluster_name: 'Has Subcluster With P1 Item',
        sum_thought_items: 2,
        subclusters: [
          {
            subcluster_name: 'Sub',
            sum_thought_items: 1,
            thought_items: [{ text: 'urgent', priority: { rank: 'P1' } }],
          },
        ],
      },
    ]

    const sorted = sortClustersByPriority(clusters)

    expect(sorted[0].cluster_name).toBe('Has Subcluster With P1 Item')
    expect(sorted[1].cluster_name).toBe('No Priority')
  })
})
