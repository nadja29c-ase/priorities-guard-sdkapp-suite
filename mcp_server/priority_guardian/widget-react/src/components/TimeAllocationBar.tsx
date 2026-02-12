import type { TimeAllocation, CalendarKeyword } from '../types'
import { BAR_COLORS } from '../constants'

interface TimeAllocationBarProps {
  timeAllocation: TimeAllocation | undefined
  activeKeywords: CalendarKeyword[]  // Keywords that have active priorities
}

/**
 * Format date range for display.
 * Shows "Feb 9 – Feb 15" (month abbreviated, no year if same year as now).
 * weekEnd is exclusive (next Monday 00:00), so we subtract 1 day for display.
 */
function formatDateRange(weekStart: string, weekEnd: string): string {
  const locale = window.openai?.locale ?? 'en-US'

  const startDate = new Date(weekStart)
  const endDate = new Date(weekEnd)
  // Subtract 1 day from end (it's exclusive - Monday 00:00, we want Sunday)
  endDate.setDate(endDate.getDate() - 1)

  const currentYear = new Date().getFullYear()
  const startYear = startDate.getFullYear()
  const endYear = endDate.getFullYear()

  const formatOptions: Intl.DateTimeFormatOptions = {
    month: 'short',
    day: 'numeric',
  }

  // Add year if different from current year
  if (startYear !== currentYear) {
    formatOptions.year = 'numeric'
  }

  const startFormatted = startDate.toLocaleDateString(locale, formatOptions)

  // For end date, only add year if different from current year
  const endFormatOptions: Intl.DateTimeFormatOptions = {
    month: 'short',
    day: 'numeric',
  }
  if (endYear !== currentYear) {
    endFormatOptions.year = 'numeric'
  }
  const endFormatted = endDate.toLocaleDateString(locale, endFormatOptions)

  return `${startFormatted} – ${endFormatted}`
}

/**
 * Format hours for display (e.g., "10.5h", "0h").
 * Removes unnecessary decimal places.
 */
function formatHours(hours: number): string {
  if (hours === 0) return '0h'
  // Round to 1 decimal place, remove trailing .0
  const rounded = Math.round(hours * 10) / 10
  const formatted = rounded % 1 === 0 ? rounded.toFixed(0) : rounded.toFixed(1)
  return `${formatted}h`
}

/**
 * Build aria-label for accessibility.
 * Uses keywords[].hours (true time toward each priority) not barSegments (exclusive bar allocation).
 */
function buildAriaLabel(
  timeAllocation: TimeAllocation,
  activeKeywords: CalendarKeyword[]
): string {
  const parts: string[] = []

  for (const kw of activeKeywords) {
    const hours = timeAllocation.keywords[kw].hours
    if (hours > 0) {
      parts.push(`${kw} ${formatHours(hours)}`)
    }
  }

  if (timeAllocation.otherHours > 0) {
    parts.push(`other ${formatHours(timeAllocation.otherHours)}`)
  }

  if (parts.length === 0) {
    return 'Time allocation: no tracked hours this week'
  }

  return `Time allocation: ${parts.join(', ')}`
}

export function TimeAllocationBar({ timeAllocation, activeKeywords }: TimeAllocationBarProps) {
  // Don't render if timeAllocation is absent
  if (!timeAllocation) {
    return null
  }

  const { weekStart, weekEnd, totalTrackedHours, barSegments, otherHours } = timeAllocation
  const dateRange = formatDateRange(weekStart, weekEnd)

  // Calculate segment widths as percentages
  // Use minimum width of 2% for very small segments to keep them visible
  const MIN_SEGMENT_PERCENT = 2

  const segments: { key: string; width: number; color: string }[] = []

  if (totalTrackedHours > 0) {
    // Add keyword segments for active priorities only
    for (const kw of activeKeywords) {
      const hours = barSegments[kw]
      if (hours > 0) {
        const percent = (hours / totalTrackedHours) * 100
        segments.push({
          key: kw,
          width: Math.max(percent, MIN_SEGMENT_PERCENT),
          color: BAR_COLORS[kw] ?? BAR_COLORS.other,
        })
      }
    }

    // Add "other" segment
    if (otherHours > 0) {
      const percent = (otherHours / totalTrackedHours) * 100
      segments.push({
        key: 'other',
        width: Math.max(percent, MIN_SEGMENT_PERCENT),
        color: BAR_COLORS.other,
      })
    }

    // Normalize widths to sum to 100% if we had to apply minimums
    const totalWidth = segments.reduce((sum, s) => sum + s.width, 0)
    if (totalWidth > 100) {
      const scale = 100 / totalWidth
      for (const s of segments) {
        s.width *= scale
      }
    }
  }

  // Build legend items: active keywords + "other" (always shown)
  // Legend uses keywords[].hours (true time toward each priority), not barSegments (exclusive bar allocation)
  const legendItems: { key: string; label: string; hours: number; isOther: boolean }[] = []

  for (const kw of activeKeywords) {
    legendItems.push({
      key: kw,
      label: kw,
      hours: timeAllocation.keywords[kw].hours,
      isOther: false,
    })
  }

  // "Other" always shown
  legendItems.push({
    key: 'other',
    label: 'other',
    hours: otherHours,
    isOther: true,
  })

  const ariaLabel = buildAriaLabel(timeAllocation, activeKeywords)

  return (
    <section
      className="bg-surface rounded-xl border border-default p-4 mb-5"
      aria-labelledby="time-allocation-heading"
    >
      {/* Header */}
      <div className="flex justify-between items-baseline mb-1">
        <h2 id="time-allocation-heading" className="text-sm font-medium text-default">
          Your time this week
        </h2>
        <span className="text-sm font-semibold text-default">
          {formatHours(totalTrackedHours)}
        </span>
      </div>

      {/* Date range */}
      <p className="text-xs text-secondary mb-3">
        {dateRange}
      </p>

      {/* Stacked bar */}
      <div
        className="h-3 rounded-full overflow-hidden flex bg-surface-tertiary"
        role="img"
        aria-label={ariaLabel}
      >
        {totalTrackedHours === 0 ? (
          // Empty state: full gray bar
          <div className="w-full h-full bg-surface-tertiary" />
        ) : (
          // Render segments
          segments.map((segment) => (
            <div
              key={segment.key}
              className={`h-full ${segment.color}`}
              style={{ width: `${segment.width}%` }}
            />
          ))
        )}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3">
        {legendItems.map((item) => (
          <div key={item.key} className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${BAR_COLORS[item.key] ?? BAR_COLORS.other}`}
              aria-hidden="true"
            />
            <span className={`text-xs ${item.isOther ? 'text-secondary italic' : 'text-secondary'}`}>
              {item.label} {formatHours(item.hours)}
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}
