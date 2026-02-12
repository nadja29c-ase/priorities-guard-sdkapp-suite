import type { CalendarKeyword } from '../types'
import { RING_STROKE_COLORS } from '../constants'
import { formatHours } from '../utils'

interface HourRingProps {
  actual: number        // weeklyHourActual (0 if null/undefined)
  target: number        // weeklyHourTarget
  keyword: CalendarKeyword  // P1, P2, P3 — determines ring color
}

// Ring geometry constants
const VIEWBOX_SIZE = 64
const CENTER = VIEWBOX_SIZE / 2  // 32
const RADIUS = 26
const STROKE_WIDTH = 5
const CIRCUMFERENCE = 2 * Math.PI * RADIUS  // ~163.36

/**
 * Compact SVG circular progress ring showing actual vs target hours.
 * Used in FlexibleCard to visualize weekly hour progress.
 */
export function HourRing({ actual, target, keyword }: HourRingProps) {
  // Calculate progress percentage (capped at 100%)
  const percentage = Math.min((actual / target) * 100, 100)

  // SVG stroke-dashoffset for progress arc
  // dashoffset = circumference means 0% visible
  // dashoffset = 0 means 100% visible
  const dashoffset = CIRCUMFERENCE - (CIRCUMFERENCE * percentage / 100)

  // Get stroke color for the keyword
  const strokeColor = RING_STROKE_COLORS[keyword] ?? RING_STROKE_COLORS.P1

  // Build accessible aria-label
  const ariaLabel = `${formatHours(actual)} of ${formatHours(target)} this week`

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
          {formatHours(actual)}
        </span>
        <span className="text-2xs text-tertiary leading-tight">
          / {formatHours(target)}
        </span>
      </div>
    </div>
  )
}
