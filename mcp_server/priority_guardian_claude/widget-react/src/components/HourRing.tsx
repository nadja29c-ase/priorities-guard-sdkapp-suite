import type { CalendarKeyword } from '../types'
import { RING_STROKE_COLORS } from '../constants'
import { formatHours, formatHoursA11y } from '../utils'
import { t } from '../i18n'

interface HourRingProps {
  actual: number        // weeklyHourActual (0 if null/undefined)
  target: number        // weeklyHourTarget
  keyword: CalendarKeyword  // P1, P2, P3 - determines ring color
}

// Ring geometry constants - copied exactly from ChatGPT widget
const VIEWBOX_SIZE = 64
const CENTER = VIEWBOX_SIZE / 2  // 32
const RADIUS = 26
const STROKE_WIDTH = 5
const CIRCUMFERENCE = 2 * Math.PI * RADIUS  // ~163.36

/**
 * Compact SVG circular progress ring showing actual vs target hours.
 * Used in FlexibleCard to visualize weekly hour progress.
 *
 * Copied from ChatGPT widget - uses inline styles instead of Tailwind.
 */
export function HourRing({ actual, target, keyword }: HourRingProps) {
  // Calculate progress percentage (capped at 100%)
  const percentage = Math.min((actual / target) * 100, 100)

  // SVG stroke-dashoffset for progress arc
  const dashoffset = CIRCUMFERENCE - (CIRCUMFERENCE * percentage / 100)

  // Get stroke color for the keyword
  const strokeColor = RING_STROKE_COLORS[keyword] ?? RING_STROKE_COLORS.P1

  // Build accessible aria-label
  const ariaLabel = t('hourRingAria')
    .replace('{hours}', formatHoursA11y(actual))
    .replace('{target}', formatHoursA11y(target))

  return (
    <div style={{ position: 'relative', width: '64px', height: '64px', flexShrink: 0 }}>
      {/* SVG Ring */}
      <svg
        viewBox={`0 0 ${VIEWBOX_SIZE} ${VIEWBOX_SIZE}`}
        style={{ width: '100%', height: '100%' }}
        role="img"
        aria-label={ariaLabel}
      >
        {/* Track (background circle) */}
        <circle
          cx={CENTER}
          cy={CENTER}
          r={RADIUS}
          fill="none"
          stroke="var(--color-border-subtle, #e5e5e5)"
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
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}
        aria-hidden="true"
      >
        <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--color-text-primary, #0d0d0d)', lineHeight: 1.2 }}>
          {formatHours(actual)}
        </span>
        <span style={{ fontSize: '10px', color: 'var(--color-text-tertiary, #8c8c8c)', lineHeight: 1.2 }}>
          / {formatHours(target)}
        </span>
      </div>
    </div>
  )
}
