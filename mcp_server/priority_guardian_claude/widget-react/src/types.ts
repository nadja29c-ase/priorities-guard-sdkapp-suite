// Priority Guardian data contract
// Copied from ChatGPT widget - window.openai declarations removed (using MCP Apps bridge)

export type CalendarKeyword = 'P1' | 'P2' | 'P3'
export type PriorityType = 'deadline' | 'flexible'
export type PriorityStatus = 'active' | 'retired'

export interface Deliverable {
  id: string
  name: string
  done: boolean
}

export interface Goal {
  id: string
  text: string
  achieved: boolean
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
  streakCount?: number // For flexible type: consecutive weeks meeting target
  deliverables: Deliverable[]
  goals: Goal[] // For flexible type (Inc D)
  // Aggregate fields from snapshot pipeline (Inc 08)
  totalHoursInvested?: number // Cumulative hours invested across all time
  avgTargetAchievement?: number | null // Cumulative % of weekly target. NULL when < 2 snapshotted weeks.
}

export interface GoogleConnection {
  connected: boolean
  scopes?: string[]
}

// Time allocation from calendar (Increment 05 / Widget C)
export interface TimeAllocationKeyword {
  hours: number
  eventCount: number
}

export interface TimeAllocation {
  weekStart: string    // ISO datetime
  weekEnd: string      // ISO datetime (exclusive - next Monday 00:00)
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
  priorities: Priority[]
  available_keywords?: string[]
  timeAllocation?: TimeAllocation
  locale?: string  // User locale for i18n (e.g., 'en-US', 'de-DE')
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
export interface PieChartData {
  weekStart: string
  weekEnd: string
  slices: PieSlice[]
  totalHours: number
  semanticTarget?: 'P1' | 'P2' | 'P3' | 'other' | null
  semanticTargetLabel?: string | null
  priorities?: unknown[]
  allEvents?: unknown[]
  isCurrentWeek?: boolean
  timeAllocation?: unknown
  [key: string]: unknown
}

// Union type for all tool output data
export type ToolOutputData = DashboardData | PieChartData

// Widget state (React state only — no persistence in sandboxed iframe)
export interface WidgetState {
  editingPriorityId?: string | null
  addFormOpen?: boolean
  awaitingOAuth?: boolean
}

// Type guards
export function isPieChartData(data: ToolOutputData | null | undefined): data is PieChartData {
  return data !== null && data !== undefined && 'slices' in data
}

export function isDashboardData(data: ToolOutputData | null | undefined): data is DashboardData {
  return data !== null && data !== undefined && !isPieChartData(data) && Array.isArray((data as DashboardData).priorities)
}
