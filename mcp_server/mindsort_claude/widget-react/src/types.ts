/**
 * MindSort Claude Widget - Data Types
 *
 * Data contract for board structure. Reuses Cluster/Subcluster/ThoughtItem
 * from the shared schema (mirrors clarity/widget-react/src/types.ts).
 *
 * NOTE: Does NOT include window.openai types - this is a Claude widget.
 */

export type Rank = 'P1' | 'P2' | 'P3'

/**
 * Thought item in object form (has text, may have priority)
 */
export interface ThoughtItem {
  text: string
  priority?: { rank: Rank }
}

/**
 * Thought item input - can be a bare string OR an object.
 * CRITICAL: A bare string has no priority and cannot carry one.
 * Always normalize before reading .priority.
 */
export type ThoughtItemInput = string | ThoughtItem

/**
 * Subcluster within a cluster
 */
export interface Subcluster {
  subcluster_name: string
  thought_items?: ThoughtItemInput[]
  sum_thought_items: number
  tags?: string[]
  priority?: { rank: Rank }
}

/**
 * Top-level cluster
 */
export interface Cluster {
  cluster_name: string
  thought_items?: ThoughtItemInput[]
  subclusters?: Subcluster[]
  sum_thought_items: number
  tags?: string[]
  priority?: { rank: Rank }
  summary?: string
}

