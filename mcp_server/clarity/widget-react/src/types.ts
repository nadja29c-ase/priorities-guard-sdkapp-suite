// Data contract (unchanged from original widget)

export interface Subcluster {
  subcluster_name: string
  thought_items?: string[]
  sum_thought_items: number
  tags?: string[]
  priority?: { rank: 'P1' | 'P2' | 'P3' }
}

export interface Cluster {
  cluster_name: string
  thought_items?: string[]
  subclusters?: Subcluster[]
  sum_thought_items: number
  tags?: string[]
  priority?: { rank: 'P1' | 'P2' | 'P3' }
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
      callTool?: (name: string, args: Record<string, unknown>) => Promise<{
        structuredContent?: { saved?: boolean }
        result?: { structuredContent?: { saved?: boolean } }
      }>
    }
  }
}

export {}
