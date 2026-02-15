import type { CalendarKeyword } from '../types'
import { RING_STROKE_COLORS } from '../constants'

interface DeliverableRingProps {
  done: number
  total: number
  keyword: CalendarKeyword
}

// Ring geometry constants (same as HourRing)
const VIEWBOX_SIZE = 64
const CENTER = VIEWBOX_SIZE / 2
const RADIUS = 26
const STROKE_WIDTH = 5
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

/**
 * Compact SVG circular progress ring showing deliverables done vs total.
 * Used in DeadlineCard to visualize deliverable completion progress.
 */
export function DeliverableRing({ done, total, keyword }: DeliverableRingProps) {
  // Calculate progress percentage (capped at 100%)
  const percentage = total > 0 ? Math.min((done / total) * 100, 100) : 0

  // SVG stroke-dashoffset for progress arc
  const dashoffset = CIRCUMFERENCE - (CIRCUMFERENCE * percentage / 100)

  // Get stroke color for the keyword
  const strokeColor = RING_STROKE_COLORS[keyword] ?? RING_STROKE_COLORS.P1

  // Build accessible aria-label
  const ariaLabel = `${done} of ${total} deliverables done`

  return (
    <div className="relative w-16 h-16 flex-shrink-0">
      {/* SVG Ring */}
      <svg
        viewBox={`0 0 ${VIEWBOX_SIZE} ${VIEWBOX_SIZE}`}
        className="w-full h-full"
        role="img"
        aria-label={ariaLabel}
      >
        {/* Track (background circle) */}
        <circle
          cx={CENTER}
          cy={CENTER}
          r={RADIUS}
          fill="none"
          stroke="var(--color-border-subtle)"
          strokeWidth={STROKE_WIDTH}
        />

        {/* Progress arc (foreground) */}
        {percentage > 0 && (
          <circle
            cx={CENTER}
            cy={CENTER}
            r={RADIUS}
            fill="none"
            stroke={strokeColor}
            strokeWidth={STROKE_WIDTH}
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={dashoffset}
            style={{
              transform: 'rotate(-90deg)',
              transformOrigin: 'center',
            }}
          />
        )}
      </svg>

      {/* Center text (HTML overlay for font inheritance) */}
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-semibold text-sm text-default leading-tight">
          {done}
        </span>
        <span className="text-2xs text-tertiary leading-tight">
          / {total}
        </span>
      </div>
    </div>
  )
}
