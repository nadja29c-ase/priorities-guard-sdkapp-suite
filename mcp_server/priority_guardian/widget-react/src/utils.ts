import type { Priority, ToolOutputData, CalendarKeyword } from './types'

/**
 * Extract structuredContent from callTool result (tries multiple paths)
 */
export function extractStructuredContent<T>(result: unknown): T | undefined {
  if (!result || typeof result !== 'object') return undefined
  const r = result as Record<string, unknown>

  // Try: result.structuredContent
  if (r.structuredContent !== undefined) {
    return r.structuredContent as T
  }
  // Try: result.result.structuredContent
  if (r.result && typeof r.result === 'object') {
    const inner = r.result as Record<string, unknown>
    if (inner.structuredContent !== undefined) {
      return inner.structuredContent as T
    }
  }
  return undefined
}

/**
 * Result type for getToolOutput with error information
 */
export interface ToolOutputResult {
  data: ToolOutputData | null
  error: string | null
}

/**
 * Get PG data from window.openai.toolOutput (tries multiple paths)
 * Returns both data and any error that occurred during parsing
 *
 * Note: The MCP tool handler normalizes data to camelCase before returning,
 * so no conversion is needed here.
 */
export function getToolOutput(): ToolOutputResult {
  try {
    const t = window.openai?.toolOutput
    if (!t) return { data: null, error: null }

    // Try all known paths for data
    let data: ToolOutputData | undefined

    if (t.result?.structuredContent?.data) {
      data = t.result.structuredContent.data
    } else if (t.structuredContent?.data) {
      data = t.structuredContent.data
    } else if (t.data) {
      data = t.data
    }

    if (!data) {
      return { data: null, error: null }
    }

    // Data is already normalized to camelCase by the MCP tool handler
    return { data, error: null }
  } catch (err) {
    console.error('Failed to parse tool output:', err)
    return {
      data: null,
      error: 'Failed to load dashboard data. The data may be corrupted.',
    }
  }
}

/**
 * Priority ranking: P1 < P2 < P3 (lower = higher priority)
 */
export function keywordToNumber(keyword: CalendarKeyword): number {
  if (keyword === 'P1') return 1
  if (keyword === 'P2') return 2
  if (keyword === 'P3') return 3
  return 999
}

/**
 * Sort priorities by calendarKeyword (P1 first, then P2, P3)
 */
export function sortPrioritiesByKeyword(priorities: Priority[]): Priority[] {
  return [...priorities].sort((a, b) => {
    return keywordToNumber(a.calendarKeyword) - keywordToNumber(b.calendarKeyword)
  })
}

/**
 * Calculate days until a date
 */
export function daysUntil(dateStr: string): number {
  const target = new Date(dateStr)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  target.setHours(0, 0, 0, 0)
  const diffMs = target.getTime() - today.getTime()
  return Math.ceil(diffMs / (1000 * 60 * 60 * 24))
}

/**
 * Format a date string for display
 */
export function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}
