// Priority Guardian data contract

export type CalendarKeyword = 'P1' | 'P2' | 'P3'
export type PriorityType = 'deadline' | 'flexible'
export type PriorityStatus = 'active' | 'retired'

export interface Deliverable {
  id: string
  name: string
  done: boolean
}

export interface Priority {
  id: string
  name: string
  type: PriorityType
  calendarKeyword: CalendarKeyword
  status: PriorityStatus
  deadline?: string // ISO date for deadline type
  weeklyHourTarget?: number // For flexible type
  weeklyHourActual?: number // For flexible type (future)
  checkpointDate?: string // ISO date for flexible type
  desiredResult?: string // For flexible type
  deliverables: Deliverable[]
  createdAt: string
  updatedAt?: string
}

export interface GoogleConnection {
  connected: boolean
  connectedAt?: string
  scopes?: string[]
}

export interface ToolOutputData {
  google_connected: boolean
  google_connected_at?: string
  priorities: Priority[]
  available_keywords?: string[]
}

// Widget state for edit mode persistence
export interface WidgetState {
  editingPriorityId?: string
  addFormOpen?: boolean
  [key: string]: unknown  // Allow any additional keys for Record<string, unknown> compatibility
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
            data?: ToolOutputData
          }
        }
        structuredContent?: {
          data?: ToolOutputData
        }
        data?: ToolOutputData
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
