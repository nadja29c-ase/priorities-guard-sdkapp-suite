// Data contract (unchanged from original widget)

export type Rank = 'P1' | 'P2' | 'P3'

// Thought item types - accepts both string and object formats
export interface ThoughtItem {
  text: string
  priority?: { rank: Rank }
}

export type ThoughtItemInput = string | ThoughtItem

export interface Subcluster {
  subcluster_name: string
  thought_items?: ThoughtItemInput[]
  sum_thought_items: number
  tags?: string[]
  priority?: { rank: Rank }
}

export interface Cluster {
  cluster_name: string
  thought_items?: ThoughtItemInput[]
  subclusters?: Subcluster[]
  sum_thought_items: number
  tags?: string[]
  priority?: { rank: Rank }
  summary?: string
}

// window.openai API types
declare global {
  interface Window {
    openai?: {
      theme?: 'light' | 'dark'
      toolOutput?: {
        result?: {
          structuredContent?: {
            clusters?: Cluster[]
          }
        }
        structuredContent?: {
          clusters?: Cluster[]
        }
        clusters?: Cluster[]
        data?: {
          clusters?: Cluster[]
        }
      }
      callTool?: <T = unknown>(name: string, args: Record<string, unknown>) => Promise<{
        structuredContent?: T
        result?: { structuredContent?: T }
      }>
    }
  }
}

export {}
