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
  weeklyHourActual?: number // For flexible type (current week hours)
  checkpointDate?: string // ISO date for flexible type
  desiredResult?: string // For flexible type
  streakCount?: number // For flexible type: consecutive weeks meeting target
  deliverables: Deliverable[]
  createdAt: string
  updatedAt?: string
  // Aggregate fields from snapshot pipeline (Inc 08)
  avgHoursWeek?: number | null // Average hours per week across completed weeks
  totalHoursInvested?: number // Cumulative hours invested across all time
  avgTargetAchievement?: number | null // Cumulative % of weekly target. NULL when < 2 snapshotted weeks.
}

export interface GoogleConnection {
  connected: boolean
  connectedAt?: string
  scopes?: string[]
}

// Time allocation from calendar (Increment 05 / Widget C)
export interface TimeAllocationKeyword {
  hours: number
  eventCount: number
}

export interface TimeAllocation {
  weekStart: string    // ISO datetime
  weekEnd: string      // ISO datetime (exclusive — next Monday 00:00)
  totalTrackedHours: number
  keywords: {
    P1: TimeAllocationKeyword
    P2: TimeAllocationKeyword
    P3: TimeAllocationKeyword
  }
  otherHours: number
  barSegments: {
    P1: number
    P2: number
    P3: number
    other: number
  }
}

// Dashboard view data (from get_priorities)
export interface DashboardData {
  google_connected: boolean
  google_connected_at?: string
  priorities: Priority[]
  available_keywords?: string[]
  timeAllocation?: TimeAllocation
}

// Pie chart slice (from get_weekly_report)
export interface PieSlice {
  label: string
  hours: number
  type: 'priority' | 'semantic'
  keyword?: CalendarKeyword  // For priority slices
  eventCount?: number        // For semantic slices
}

// Pie chart view data (from get_weekly_report)
// Widget uses: slices, totalHours, weekStart, weekEnd
// LLM uses: priorities, allEvents, isCurrentWeek (via assistant_guidance)
export interface PieChartData {
  weekStart: string
  weekEnd: string
  slices: PieSlice[]
  totalHours: number
  // Extra fields from get_weekly_report (widget ignores, LLM uses)
  priorities?: unknown[]
  allEvents?: unknown[]
  isCurrentWeek?: boolean
  timeAllocation?: unknown
  [key: string]: unknown  // Forward-compatible with future fields
}

// Union type for all tool output data
export type ToolOutputData = DashboardData | PieChartData

// Type guards
export function isPieChartData(data: ToolOutputData | null | undefined): data is PieChartData {
  return data !== null && data !== undefined && 'slices' in data
}

export function isDashboardData(data: ToolOutputData | null | undefined): data is DashboardData {
  return data !== null && data !== undefined && 'priorities' in data
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
