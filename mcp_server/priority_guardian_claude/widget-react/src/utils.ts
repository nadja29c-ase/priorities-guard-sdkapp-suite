import type { Priority, CalendarKeyword } from './types'
import { t, getRawLocale } from './i18n'

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
 * Format a date string for display (locale-aware)
 */
export function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  const locale = getRawLocale()
  return date.toLocaleDateString(locale, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

/**
 * Format hours for display (e.g., "10.5h", "0h").
 * Removes unnecessary decimal places.
 */
export function formatHours(hours: number): string {
  if (hours === 0) return '0h'
  // Round to 1 decimal place, remove trailing .0
  const rounded = Math.round(hours * 10) / 10
  const formatted = rounded % 1 === 0 ? rounded.toFixed(0) : rounded.toFixed(1)
  return `${formatted}h`
}

/**
 * Format hours for accessibility (aria-labels only).
 * Uses full localized unit word ("hours" / "Stunden") instead of "h" abbreviation.
 */
export function formatHoursA11y(hours: number): string {
  const rounded = Math.round(hours * 10) / 10
  const formatted = rounded % 1 === 0 ? rounded.toFixed(0) : rounded.toFixed(1)
  return `${formatted} ${t('hoursUnit')}`
}

/**
 * Detect mobile device from userAgent string.
 * Claude's hostContext.userAgent is a plain string, not an object.
 */
export function isMobileDevice(userAgent: string | undefined): boolean {
  return /iPhone|iPad|iPod|Android/i.test(userAgent ?? '')
}

/**
 * Extract structuredContent from Claude callServerTool result.
 * Returns typed data or undefined if extraction fails.
 */
export function extractClaudeStructuredContent<T>(result: unknown): T | undefined {
  if (!result || typeof result !== 'object') return undefined
  const r = result as Record<string, unknown>
  if (r.structuredContent !== undefined) {
    return r.structuredContent as T
  }
  return undefined
}
