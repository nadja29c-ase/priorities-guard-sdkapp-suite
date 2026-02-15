import type { TimeAllocation, CalendarKeyword } from '../types'
import { BAR_COLORS } from '../constants'
import { formatHours } from '../utils'

interface TimeAllocationBarProps {
  timeAllocation: TimeAllocation | undefined
  activeKeywords: CalendarKeyword[]  // Keywords that have active priorities
  onRefresh?: () => void
  isRefreshing?: boolean
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
 */
function formatDateRange(weekStart: string, weekEnd: string): string {
  const locale = window.openai?.locale ?? 'en-US'

  const start = parseDateParts(weekStart)
  const end = parseDateParts(weekEnd)

  // Subtract 1 day from end date (it's exclusive - Monday 00:00, we want Sunday)
  const startDate = new Date(start.year, start.month - 1, start.day)
  const endDate = new Date(end.year, end.month - 1, end.day - 1)

  const currentYear = new Date().getFullYear()

  const formatOptions: Intl.DateTimeFormatOptions = {
    month: 'short',
    day: 'numeric',
  }

  if (start.year !== currentYear) {
    formatOptions.year = 'numeric'
  }

  const startFormatted = startDate.toLocaleDateString(locale, formatOptions)

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

export function TimeAllocationBar({ timeAllocation, activeKeywords, onRefresh, isRefreshing }: TimeAllocationBarProps) {
  // Don't render if timeAllocation is absent
  if (!timeAllocation) {
    return null
  }

  const { weekStart, weekEnd, totalTrackedHours, barSegments, otherHours } = timeAllocation
  const dateRange = formatDateRange(weekStart, weekEnd)

  // Calculate segment widths as percentages
  const MIN_SEGMENT_PERCENT = 2

  const segments: { key: string; width: number; color: string }[] = []

  if (totalTrackedHours > 0) {
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

    if (otherHours > 0) {
      const percent = (otherHours / totalTrackedHours) * 100
      segments.push({
        key: 'other',
        width: Math.max(percent, MIN_SEGMENT_PERCENT),
        color: BAR_COLORS.other,
      })
    }

    // Normalize widths to sum to 100%
    const totalWidth = segments.reduce((sum, s) => sum + s.width, 0)
    if (totalWidth > 100) {
      const scale = 100 / totalWidth
      for (const s of segments) {
        s.width *= scale
      }
    }
  }

  // Build legend items
  const legendItems: { key: string; label: string; hours: number; isOther: boolean }[] = []

  for (const kw of activeKeywords) {
    legendItems.push({
      key: kw,
      label: kw,
      hours: timeAllocation.keywords[kw].hours,
      isOther: false,
    })
  }

  legendItems.push({
    key: 'other',
    label: 'other',
    hours: otherHours,
    isOther: true,
  })

  const ariaLabel = buildAriaLabel(timeAllocation, activeKeywords)

  return (
    <section className="mb-5" aria-labelledby="time-allocation-heading">
      {/* Header row - V7 style */}
      <div className="flex justify-between items-center mb-1.5">
        <span
          id="time-allocation-heading"
          className="text-xs font-medium uppercase tracking-wide"
          style={{ color: 'var(--gray-500, #5d5d5d)' }}
        >
          This week
        </span>
        <div className="flex items-center gap-2">
          <span
            className="text-sm font-semibold tabular-nums"
            style={{ color: 'var(--gray-900, #181818)' }}
          >
            {formatHours(totalTrackedHours)}
          </span>
          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={isRefreshing}
              className="p-1 rounded-full hover:bg-surface-secondary transition-colors"
              style={{ opacity: isRefreshing ? 0.4 : 1 }}
              title="Refresh calendar data"
              aria-label="Refresh calendar data"
            >
              <svg
                className="w-3 h-3"
                style={{ color: 'var(--gray-400, #8f8f8f)' }}
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
              >
                <path d="M2.5 8a5.5 5.5 0 019.3-3.9M13.5 8a5.5 5.5 0 01-9.3 3.9" />
                <path d="M12 1v3.5h-3.5M4 15v-3.5h3.5" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Date range */}
      <p className="text-xs mb-2.5" style={{ color: 'var(--gray-450, #767676)' }}>
        {dateRange}
      </p>

      {/* Stacked bar - V7: h-2, gap-px, rounded segments */}
      <div
        className="h-2 rounded-full overflow-hidden flex gap-px"
        style={{ background: 'var(--gray-100, #ededed)' }}
        role="img"
        aria-label={ariaLabel}
      >
        {totalTrackedHours === 0 ? (
          <div className="w-full h-full" />
        ) : (
          segments.map((segment, index) => (
            <div
              key={segment.key}
              className={`h-full ${segment.color} ${index === 0 ? 'rounded-l-full' : ''} ${index === segments.length - 1 ? 'rounded-r-full' : ''}`}
              style={{ width: `${segment.width}%` }}
            />
          ))
        )}
      </div>

      {/* Legend - V7: w-1.5 h-1.5 dots */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2.5">
        {legendItems.map((item) => (
          <div key={item.key} className="flex items-center gap-1.5">
            <span
              className={`w-1.5 h-1.5 rounded-full ${BAR_COLORS[item.key] ?? BAR_COLORS.other}`}
              aria-hidden="true"
            />
            <span
              className={`text-xs tabular-nums ${item.isOther ? 'italic' : ''}`}
              style={{ color: item.isOther ? 'var(--gray-400, #8f8f8f)' : 'var(--gray-500, #5d5d5d)' }}
            >
              {item.label} {formatHours(item.hours)}
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}
