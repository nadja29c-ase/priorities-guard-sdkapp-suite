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
      // Theme and display
      theme?: 'light' | 'dark'
      locale?: string
      userAgent?: string
      displayMode?: 'inline' | 'pip' | 'fullscreen'
      maxHeight?: number
      safeArea?: { top: number; bottom: number; left: number; right: number }
      view?: 'default' | 'launcher'

      // Tool output data
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

      // Tool calling
      callTool?: <T = unknown>(name: string, args: Record<string, unknown>) => Promise<{
        structuredContent?: T
        result?: { structuredContent?: T }
      }>

      // Widget state persistence
      widgetState?: Record<string, unknown>
      setWidgetState?: (state: Record<string, unknown>) => void

      // Layout & height
      notifyIntrinsicHeight?: (height?: number) => void
      requestDisplayMode?: (options: { mode: 'inline' | 'pip' | 'fullscreen' }) => Promise<void>
      requestClose?: () => void
      requestModal?: (options: unknown) => Promise<unknown>

      // User actions
      sendFollowUpMessage?: (options: { prompt: string }) => Promise<void>
      uploadFile?: (file: File) => Promise<{ fileId: string }>
      getFileDownloadUrl?: (options: { fileId: string }) => Promise<{ downloadUrl: string }>
      openExternal?: (options: { href: string }) => void
    }
  }
}

export {}
