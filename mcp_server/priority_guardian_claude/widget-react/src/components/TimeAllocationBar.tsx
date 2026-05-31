import type { TimeAllocation, CalendarKeyword } from '../types'
import { BAR_COLORS } from '../constants'
import { formatHours, formatHoursA11y } from '../utils'
import { t, getRawLocale } from '../i18n'

interface TimeAllocationBarProps {
  timeAllocation: TimeAllocation | undefined
  activeKeywords: CalendarKeyword[]  // Keywords that have active priorities
  onRefresh?: () => void
  isRefreshing?: boolean
}

/**
 * Parse date components from ISO string directly (timezone-safe).
 */
function parseDateParts(isoString: string): { year: number; month: number; day: number } {
  const [datePart] = isoString.split('T')
  const [year, month, day] = datePart.split('-').map(Number)
  return { year, month, day }
}

/**
 * Format date range for display.
 * weekEnd is exclusive (next Monday 00:00), so we subtract 1 day for display.
 */
function formatDateRange(weekStart: string, weekEnd: string): string {
  const locale = getRawLocale()

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

  return `${startFormatted} - ${endFormatted}`
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
      parts.push(`${kw} ${formatHoursA11y(hours)}`)
    }
  }

  if (timeAllocation.otherHours > 0) {
    parts.push(`${t('otherLabel')} ${formatHoursA11y(timeAllocation.otherHours)}`)
  }

  if (parts.length === 0) {
    return t('noTrackedHours')
  }

  return t('timeAllocationPrefix') + parts.join(', ')
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
    label: t('otherLabel'),
    hours: otherHours,
    isOther: true,
  })

  const ariaLabel = buildAriaLabel(timeAllocation, activeKeywords)

  return (
    <section style={{ marginBottom: '20px' }} aria-labelledby="time-allocation-heading">
      {/* Header row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
        <span
          id="time-allocation-heading"
          style={{
            fontSize: '12px',
            fontWeight: 500,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            color: 'var(--color-text-secondary, #3D3D3A)',
          }}
        >
          {t('timeAllocationHeading')}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '14px', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: 'var(--color-text-primary, #0d0d0d)' }}>
            {formatHours(totalTrackedHours)}
          </span>
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={isRefreshing}
              style={{
                padding: '4px',
                minWidth: '44px',
                minHeight: '44px',
                borderRadius: '9999px',
                background: 'none',
                border: 'none',
                cursor: isRefreshing ? 'not-allowed' : 'pointer',
                opacity: isRefreshing ? 0.4 : 1,
                color: 'var(--color-text-tertiary, #73726C)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
              title={t('refreshCalendar')}
              aria-label={t('refreshCalendar')}
            >
              <svg
                style={{
                  width: '12px',
                  height: '12px',
                  animation: isRefreshing ? 'spin 1s linear infinite' : 'none',
                }}
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                aria-hidden="true"
              >
                <path d="M2.5 8a5.5 5.5 0 019.3-3.9M13.5 8a5.5 5.5 0 01-9.3 3.9" />
                <path d="M12 1v3.5h-3.5M4 15v-3.5h3.5" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Date range */}
      <p style={{ fontSize: '12px', marginBottom: '10px', color: 'var(--color-text-secondary, #3D3D3A)' }}>
        {dateRange}
      </p>

      {/* Stacked bar */}
      <div
        style={{
          height: '8px',
          borderRadius: '9999px',
          overflow: 'hidden',
          display: 'flex',
          gap: '1px',
          background: 'var(--color-background-tertiary, #ebebeb)',
        }}
        role="img"
        aria-label={ariaLabel}
      >
        {totalTrackedHours === 0 ? (
          <div style={{ width: '100%', height: '100%' }} />
        ) : (
          segments.map((segment, index) => (
            <div
              key={segment.key}
              style={{
                height: '100%',
                width: `${segment.width}%`,
                background: segment.color,
                borderRadius: index === 0 ? '9999px 0 0 9999px' : index === segments.length - 1 ? '0 9999px 9999px 0' : '0',
              }}
            />
          ))
        )}
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', marginTop: '10px' }}>
        {legendItems.map((item) => (
          <div key={item.key} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                background: item.isOther ? BAR_COLORS.other : (BAR_COLORS[item.key] ?? BAR_COLORS.other),
              }}
              aria-hidden="true"
            />
            <span
              style={{
                fontSize: '12px',
                fontVariantNumeric: 'tabular-nums',
                color: 'var(--color-text-secondary, #3D3D3A)',
                fontStyle: item.isOther ? 'italic' : 'normal',
              }}
            >
              {item.label} {formatHours(item.hours)}
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}
