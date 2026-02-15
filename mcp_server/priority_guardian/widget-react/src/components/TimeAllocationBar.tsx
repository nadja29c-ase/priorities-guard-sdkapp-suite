import type { TimeAllocation, CalendarKeyword } from '../types'
import { BAR_COLORS } from '../constants'
import { formatHours } from '../utils'

interface TimeAllocationBarProps {
  timeAllocation: TimeAllocation | undefined
  activeKeywords: CalendarKeyword[]  // Keywords that have active priorities
}

/**
 * Parse date components from ISO string directly (timezone-safe).
 * Avoids Date object local-timezone conversion issues.
 */
function parseDateParts(isoString: string): { year: number; month: number; day: number } {
  const [datePart] = isoString.split('T')
  const [year, month, day] = datePart.split('-').map(Number)
  return { year, month, day }
}

/**
 * Format date range for display.
 * Shows "Feb 9 – Feb 15" (month abbreviated, no year if same year as now).
 * weekEnd is exclusive (next Monday 00:00), so we subtract 1 day for display.
 *
 * Uses string parsing instead of Date arithmetic to avoid timezone issues:
 * the backend sends dates in user's timezone, and we want to display those
 * dates regardless of the browser's current timezone.
 */
function formatDateRange(weekStart: string, weekEnd: string): string {
  const locale = window.openai?.locale ?? 'en-US'

  const start = parseDateParts(weekStart)
  const end = parseDateParts(weekEnd)

  // Subtract 1 day from end date (it's exclusive - Monday 00:00, we want Sunday)
  // Create Date with year, month-1, day-1 to get the previous day
  const startDate = new Date(start.year, start.month - 1, start.day)
  const endDate = new Date(end.year, end.month - 1, end.day - 1)

  const currentYear = new Date().getFullYear()

  const formatOptions: Intl.DateTimeFormatOptions = {
    month: 'short',
    day: 'numeric',
  }

  // Add year if different from current year
  if (start.year !== currentYear) {
    formatOptions.year = 'numeric'
  }

  const startFormatted = startDate.toLocaleDateString(locale, formatOptions)

  // For end date, only add year if different from current year
  const endFormatOptions: Intl.DateTimeFormatOptions = {
    month: 'short',
    day: 'numeric',
  }
  if (endDate.getFullYear() !== currentYear) {
    endFormatOptions.year = 'numeric'
  }
  const endFormatted = endDate.toLocaleDateString(locale, endFormatOptions)

  return `${startFormatted} – ${endFormatted}`
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
  // Show instructional state if timeAllocation is absent
  if (!timeAllocation) {
    return (
      <section
        className="bg-surface rounded-xl border border-default p-4 mb-5"
        aria-label="Time tracking instructions"
      >
        <div className="p-2 bg-surface-secondary rounded-lg">
          <p className="text-xs text-secondary">
            {'📅'} Use <strong className="text-default">P1</strong>, <strong className="text-default">P2</strong>, <strong className="text-default">P3</strong> in the calendar event title to track time
          </p>
        </div>
      </section>
    )
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
          Your time allocation this week
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
