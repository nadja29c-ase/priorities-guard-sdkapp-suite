import type { PieSlice, CalendarKeyword } from '../types'
import { RING_STROKE_COLORS } from '../constants'
import { t } from '../i18n'

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

// Colorful semantic slice colors (non-priority categories)
// Distinct from P1 (blue), P2 (purple), P3 (yellow) - uses SDK primitives only
// All values are CSS variables from variables-primitive.css or variables-semantic.css
const SEMANTIC_COLORS = [
  'var(--color-background-success-solid)',  // green
  'var(--color-background-danger-solid)',   // red
  'var(--color-background-warning-solid)',  // orange
  'var(--green-300)',                       // light green - SDK primitive
  'var(--pink-400)',                        // pink - SDK primitive
  'var(--blue-300)',                        // light blue - SDK primitive
  'var(--orange-300)',                      // light orange - SDK primitive
  'var(--red-300)',                         // light red - SDK primitive
]

// Muted grey for unmatched "other" - visible but subordinate
// gray-500 (#5d5d5d) is identical in both light/dark modes, provides consistent contrast
const OTHER_GREY = 'var(--gray-500)'

export function PieChart({ slices, totalHours, weekStart, weekEnd, semanticTargetLabel }: PieChartProps) {
  // Filter out zero-hour slices
  const validSlices = slices.filter(s => s.hours > 0)

  if (validSlices.length === 0) {
    return (
      <div className="p-6 text-center bg-surface rounded-xl border border-default">
        <p className="text-sm text-secondary">{t('noTimeData')}</p>
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
      const locale = window.openai?.locale ?? 'en-US'
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
    <div className="bg-surface rounded-xl border border-default p-6">
      {/* Header */}
      <div className="text-center mb-4">
        <h2 className="text-base font-semibold text-default">
          {semanticTargetLabel ? t('breakdown') + translateSliceLabel(semanticTargetLabel) : t('timeAllocationTitle')}
        </h2>
        <p className="text-xs text-tertiary">{formatWeekRange()}</p>
      </div>

      {/* SVG Pie Chart */}
      <div className="flex justify-center mb-4">
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          aria-label={t('pieChartAria').replace('{hours}', totalHours.toFixed(1)).replace('{n}', String(validSlices.length))}
          role="img"
        >
          {/* Background circle */}
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke="var(--color-border-subtle)"
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
              aria-label={`${translateSliceLabel(seg.slice.label)}: ${seg.slice.hours}h (${seg.percent.toFixed(0)}%)`}
            />
          ))}

          {/* Center text */}
          <text
            x={center}
            y={center - 8}
            textAnchor="middle"
            style={{ fill: 'var(--color-text)', fontSize: '1.25rem', fontWeight: 700 }}
          >
            {totalHours.toFixed(1)}h
          </text>
          <text
            x={center}
            y={center + 12}
            textAnchor="middle"
            style={{ fill: 'var(--color-text-tertiary)', fontSize: '0.75rem' }}
          >
            {t('totalHours')}
          </text>
        </svg>
      </div>

      {/* Legend */}
      <div className="space-y-2">
        {segments.map((seg, index) => (
          <div key={index} className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2 min-w-0">
              <span
                className="w-3 h-3 rounded-full flex-shrink-0"
                style={{ backgroundColor: seg.color }}
                aria-hidden="true"
              />
              <span className="text-default truncate">{translateSliceLabel(seg.slice.label)}</span>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0 ml-2">
              <span className="text-secondary">{seg.slice.hours.toFixed(1)}h</span>
              <span className="text-tertiary text-xs w-10 text-right">
                {seg.percent.toFixed(0)}%
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* CTA to break down categories - shown when not already zoomed in */}
      {!semanticTargetLabel && (
        <p className="mt-4 text-xs text-center text-secondary">
          {t('breakdownCta')}
        </p>
      )}
    </div>
  )
}
