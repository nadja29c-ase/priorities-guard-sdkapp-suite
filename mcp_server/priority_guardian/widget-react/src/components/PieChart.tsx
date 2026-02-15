import type { PieSlice, CalendarKeyword } from '../types'
import { RING_STROKE_COLORS } from '../constants'

interface PieChartProps {
  slices: PieSlice[]
  totalHours: number
  weekStart: string
  weekEnd: string
}

// Priority colors from SDK tokens (same as HourRing)
// P1: info (blue), P2: discovery (purple), P3: caution (yellow)
const PRIORITY_COLORS: Record<CalendarKeyword, string> = {
  P1: RING_STROKE_COLORS.P1,
  P2: RING_STROKE_COLORS.P2,
  P3: RING_STROKE_COLORS.P3,
}

// Colorful semantic slice colors (non-priority categories)
// Distinct from P1 (blue), P2 (purple), P3 (yellow) - uses greens, teals, pinks, oranges
// SDK-compliant colors that work in both light and dark themes
const SEMANTIC_COLORS = [
  'var(--color-background-success-solid, #00a240)',  // green - SDK success
  'var(--color-background-danger-solid, #e02e2a)',   // red - SDK danger
  '#14b8a6',  // teal-500
  '#f97316',  // orange-500
  '#ec4899',  // pink-500
  '#06b6d4',  // cyan-500
  '#84cc16',  // lime-500
  '#a855f7',  // violet-500 (distinct from P2 purple)
]

// Muted grey for unmatched "other" - visible but subordinate (SDK semantic token)
const OTHER_GREY = 'var(--color-border-default)'

export function PieChart({ slices, totalHours, weekStart, weekEnd }: PieChartProps) {
  // Filter out zero-hour slices
  const validSlices = slices.filter(s => s.hours > 0)

  if (validSlices.length === 0) {
    return (
      <div className="p-6 text-center bg-surface rounded-xl border border-default">
        <p className="text-sm text-secondary">No time data to display</p>
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

  // Format week dates for display
  const formatWeekRange = () => {
    try {
      const start = new Date(weekStart)
      const end = new Date(weekEnd)
      const options: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' }
      return `${start.toLocaleDateString(undefined, options)} - ${end.toLocaleDateString(undefined, options)}`
    } catch {
      return `${weekStart} - ${weekEnd}`
    }
  }

  return (
    <div className="bg-surface rounded-xl border border-default p-6">
      {/* Header */}
      <div className="text-center mb-4">
        <h2 className="text-base font-semibold text-default">Time Allocation</h2>
        <p className="text-xs text-tertiary">{formatWeekRange()}</p>
      </div>

      {/* SVG Pie Chart */}
      <div className="flex justify-center mb-4">
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          aria-label={`Pie chart showing ${totalHours} total hours across ${validSlices.length} categories`}
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
              aria-label={`${seg.slice.label}: ${seg.slice.hours}h (${seg.percent.toFixed(0)}%)`}
            />
          ))}

          {/* Center text */}
          <text
            x={center}
            y={center - 8}
            textAnchor="middle"
            className="text-2xl font-bold"
            fill="var(--color-text-default)"
          >
            {totalHours.toFixed(1)}h
          </text>
          <text
            x={center}
            y={center + 12}
            textAnchor="middle"
            className="text-xs"
            fill="var(--color-text-tertiary)"
          >
            total
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
              <span className="text-default truncate">{seg.slice.label}</span>
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

      {/* CTA to categorize "Other" - only shown when uncategorized time exists */}
      {validSlices.some(s => ['other', 'uncategorized', 'misc'].includes(s.label.toLowerCase())) && (
        <p className="mt-4 text-xs text-center text-secondary">
          Ask ChatGPT to categorize 'Other' to uncover where your time is really going.
        </p>
      )}
    </div>
  )
}
