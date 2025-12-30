// Simplified data contract for Unpack

export interface QuestionCluster {
  id: string
  theme: string
  questions: string[]
  insight: string
}

export interface UnpackData {
  problem_statement: string
  clusters: QuestionCluster[]
  unclustered: string[]
  summary_markdown: string
}

// window.openai API types (simplified for Unpack)
declare global {
  interface Window {
    openai?: {
      theme?: 'light' | 'dark'
      toolOutput?: {
        structuredContent?: UnpackData
        result?: { structuredContent?: UnpackData }
      }
      notifyIntrinsicHeight?: () => void
      widgetState?: Record<string, unknown>
      setWidgetState?: (state: Record<string, unknown>) => void
    }
  }
}

export {}
