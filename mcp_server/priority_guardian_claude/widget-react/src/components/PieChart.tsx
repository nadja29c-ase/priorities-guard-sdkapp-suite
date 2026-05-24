import type { PieSlice, CalendarKeyword } from '../types'
import { RING_STROKE_COLORS } from '../constants'
import { formatHoursA11y } from '../utils'
import { t, getRawLocale } from '../i18n'

/**
 * Translate known sentinel labels from backend data.
 * These are system-generated labels, not user content.
 */
function translateSliceLabel(label: string): string {
  const lower = label.toLowerCase()
  if (lower === 'other') return t('otherLabel')
  if (lower === 'uncategorized') return t('uncategorized')
  if (lower === 'unnamed') return t('unnamed')
  return label
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

interface PieChartProps {
  slices: PieSlice[]
  totalHours: number
  weekStart: string
  weekEnd: string
  semanticTargetLabel?: string | null  // "P1: Ship v1.0" or "Other" when zoomed
}

// Priority colors from SDK tokens (same as HourRing)
// P1: info (blue), P2: discovery (purple), P3: caution (yellow)
const PRIORITY_COLORS: Record<CalendarKeyword, string> = {
  P1: RING_STROKE_COLORS.P1,
  P2: RING_STROKE_COLORS.P2,
  P3: RING_STROKE_COLORS.P3,
}

// Semantic slice colors for non-priority categories.
// All theme-adaptive SDK tokens. Distinct from P1 (blue), P2 (purple), P3 (yellow).
// 5 colors covers typical breakdown slices; cycles if more needed.
const SEMANTIC_COLORS = [
  'var(--color-background-success-solid, #10b981)',    // green
  'var(--color-background-danger-solid, #dc2626)',     // red
  'var(--color-background-warning-solid, #f59e0b)',    // orange/amber
  'var(--color-background-primary-solid, #0285ff)',    // brand accent
  'var(--color-background-secondary-solid, #737373)',  // neutral dark
]

// Muted neutral for "Other"/"Uncategorized" — subordinate to named categories
const OTHER_GREY = 'var(--color-background-secondary-solid, #737373)'

export function PieChart({ slices, totalHours, weekStart, weekEnd, semanticTargetLabel }: PieChartProps) {
  // Filter out zero-hour slices
  const validSlices = slices.filter(s => s.hours > 0)

  if (validSlices.length === 0) {
    return (
      <div
        style={{
          padding: '24px',
          textAlign: 'center',
          background: 'var(--color-background-primary, #fff)',
          borderRadius: '12px',
          border: '1px solid var(--color-border, #e5e5e5)',
        }}
      >
        <p style={{ fontSize: '14px', color: 'var(--color-text-secondary, #737373)' }}>
          {t('noTimeData')}
        </p>
      </div>
    )
  }

  // SVG dimensions
  const size = 200
  const center = size / 2
  const radius = 80
  const strokeWidth = 40

  // Calculate circumference
  const circumference = 2 * Math.PI * radius

  // Build segments with cumulative offsets
  let cumulativePercent = 0
  const segments = validSlices.map((slice, index) => {
    const percent = (slice.hours / totalHours) * 100
    const strokeDasharray = `${(percent / 100) * circumference} ${circumference}`
    const rotation = (cumulativePercent / 100) * 360 - 90 // Start from top

    // Get color based on slice type
    let color: string
    if (slice.type === 'priority' && slice.keyword) {
      color = PRIORITY_COLORS[slice.keyword as CalendarKeyword] || SEMANTIC_COLORS[0]
    } else {
      // Check if this is a generic "other" slice (uncategorized)
      const labelLower = slice.label.toLowerCase()
      if (labelLower === 'other' || labelLower === 'uncategorized' || labelLower === 'misc') {
        color = OTHER_GREY
      } else {
        // Semantic slices get colorful colors (cycle through)
        const semanticIndex = validSlices.filter((s, i) => i < index && s.type === 'semantic' &&
          !['other', 'uncategorized', 'misc'].includes(s.label.toLowerCase())).length
        color = SEMANTIC_COLORS[semanticIndex % SEMANTIC_COLORS.length]
      }
    }

    cumulativePercent += percent

    return {
      slice,
      percent,
      strokeDasharray,
      rotation,
      color,
    }
  })

  // Format week dates for display (timezone-safe)
  const formatWeekRange = () => {
    try {
      const locale = getRawLocale()
      const start = parseDateParts(weekStart)
      const end = parseDateParts(weekEnd)

      // weekEnd is exclusive (Monday 00:00), so subtract 1 day for display
      const startDate = new Date(start.year, start.month - 1, start.day)
      const endDate = new Date(end.year, end.month - 1, end.day - 1)

      const options: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' }
      return `${startDate.toLocaleDateString(locale, options)} – ${endDate.toLocaleDateString(locale, options)}`
    } catch {
      return `${weekStart} – ${weekEnd}`
    }
  }

  return (
    <div
      style={{
        background: 'var(--color-background-primary, #fff)',
        borderRadius: '12px',
        border: '1px solid var(--color-border, #e5e5e5)',
        padding: '24px',
      }}
    >
      {/* Header */}
      <div style={{ textAlign: 'center', marginBottom: '16px' }}>
        <h2
          style={{
            fontSize: '16px',
            fontWeight: 600,
            color: 'var(--color-text-primary, #0d0d0d)',
          }}
        >
          {semanticTargetLabel ? t('breakdown') + translateSliceLabel(semanticTargetLabel) : t('timeAllocationTitle')}
        </h2>
        <p style={{ fontSize: '12px', color: 'var(--color-text-tertiary, #8c8c8c)' }}>
          {formatWeekRange()}
        </p>
      </div>

      {/* SVG Pie Chart */}
      <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '16px' }}>
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          aria-label={t('pieChartAria', { hours: totalHours.toFixed(1), n: validSlices.length })}
          role="img"
        >
          {/* Background circle */}
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke="var(--color-border-subtle, #e5e5e5)"
            strokeWidth={strokeWidth}
          />

          {/* Segments */}
          {segments.map((seg, index) => (
            <circle
              key={index}
              cx={center}
              cy={center}
              r={radius}
              fill="none"
              stroke={seg.color}
              strokeWidth={strokeWidth}
              strokeDasharray={seg.strokeDasharray}
              strokeDashoffset={0}
              transform={`rotate(${seg.rotation} ${center} ${center})`}
              aria-label={`${translateSliceLabel(seg.slice.label)}: ${formatHoursA11y(seg.slice.hours)} (${seg.percent.toFixed(0)}%)`}
            />
          ))}

          {/* Center text */}
          <text
            x={center}
            y={center - 8}
            textAnchor="middle"
            style={{ fill: 'var(--color-text-primary, #0d0d0d)', fontSize: '1.25rem', fontWeight: 700 }}
          >
            {totalHours.toFixed(1)}h
          </text>
          <text
            x={center}
            y={center + 12}
            textAnchor="middle"
            style={{ fill: 'var(--color-text-tertiary, #8c8c8c)', fontSize: '0.75rem' }}
          >
            {t('totalHours')}
          </text>
        </svg>
        {/* Visually hidden total for screen readers (SVG text is inaccessible with role="img") */}
        <p
          style={{
            position: 'absolute',
            width: '1px',
            height: '1px',
            padding: 0,
            margin: '-1px',
            overflow: 'hidden',
            clip: 'rect(0, 0, 0, 0)',
            whiteSpace: 'nowrap',
            border: 0,
          }}
        >
          {formatHoursA11y(totalHours)} {t('totalHours')}
        </p>
      </div>

      {/* Legend - semantic list for screen readers */}
      <ul
        style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '8px' }}
        aria-label={t('timeAllocationTitle')}
      >
        {segments.map((seg, index) => (
          <li
            key={index}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: '14px',
            }}
            aria-label={`${translateSliceLabel(seg.slice.label)}: ${formatHoursA11y(seg.slice.hours)}, ${seg.percent.toFixed(0)}%`}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
              <span
                style={{
                  width: '12px',
                  height: '12px',
                  borderRadius: '9999px',
                  flexShrink: 0,
                  backgroundColor: seg.color,
                }}
                aria-hidden="true"
              />
              <span
                aria-hidden="true"
                style={{
                  color: 'var(--color-text-primary, #0d0d0d)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {translateSliceLabel(seg.slice.label)}
              </span>
            </div>
            <div
              style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0, marginLeft: '8px' }}
              aria-hidden="true"
            >
              <span style={{ color: 'var(--color-text-secondary, #737373)' }}>
                {seg.slice.hours.toFixed(1)}h
              </span>
              <span
                style={{
                  color: 'var(--color-text-tertiary, #8c8c8c)',
                  fontSize: '12px',
                  width: '40px',
                  textAlign: 'right',
                }}
              >
                {seg.percent.toFixed(0)}%
              </span>
            </div>
          </li>
        ))}
      </ul>

      {/* CTA to break down categories - shown when not already zoomed in */}
      {!semanticTargetLabel && (
        <p
          style={{
            marginTop: '16px',
            fontSize: '12px',
            textAlign: 'center',
            color: 'var(--color-text-secondary, #737373)',
          }}
        >
          {t('breakdownCta')}
        </p>
      )}
    </div>
  )
}
