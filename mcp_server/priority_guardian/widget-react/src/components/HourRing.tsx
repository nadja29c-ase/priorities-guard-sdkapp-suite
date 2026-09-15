import type { CalendarKeyword } from '../types'
import { RING_STROKE_COLORS } from '../constants'
import { formatHours, formatHoursA11y } from '../utils'
import { t } from '../i18n'

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
 *
 * Size (inc_cardsize_fix_3.md, then unconditionally in inc_fullscreen_size_fix.md):
 * 56px (w-14), not the 44px (w-11) originally proposed — visually verified at
 * 44px/48px/56px against realistic (8h/10h) and long (12.5h/100h) values; the
 * center text overlay is HTML, not part of the scalable SVG viewBox, so it
 * doesn't shrink with the ring and visibly crowded the track at 44/48px even
 * in the realistic case. 56px was the first size where both cases stayed
 * clear. Originally inline-only (fullscreen kept 64px); re-checked directly
 * in fullscreen's actual rendered context (real component, long-value case)
 * before this increment made it unconditional — no disproportion found, no
 * new checkpoint was needed.
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

  // Build accessible aria-label (uses formatHoursA11y for localized unit)
  const ariaLabel = t('hourRingAria')
    .replace('{hours}', formatHoursA11y(actual))
    .replace('{target}', formatHoursA11y(target))

  return (
    <div className="relative flex-shrink-0 w-14 h-14">
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
      <div className="absolute inset-0 flex flex-col items-center justify-center" aria-hidden="true">
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
