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

// Type guards
export function isDashboardData(data: unknown): data is DashboardData {
  return data !== null && data !== undefined && typeof data === 'object' && 'priorities' in data
}
