import type { Priority } from '../types'
import { daysUntil, formatDate } from '../utils'

interface FlexibleCardProps {
  priority: Priority
}

// Neutral badge colors per spec (no success/danger/warning connotation)
const BADGE_COLORS: Record<string, string> = {
  P1: 'bg-[#5B8DEF] text-white',  // muted blue
  P2: 'bg-[#9B7FD4] text-white',  // muted purple
  P3: 'bg-[#4DB6AC] text-white',  // muted teal
}

export function FlexibleCard({ priority }: FlexibleCardProps) {
  const checkpointDays = priority.checkpointDate ? daysUntil(priority.checkpointDate) : null

  const badgeColorClass = BADGE_COLORS[priority.calendarKeyword] ?? BADGE_COLORS.P1

  return (
    <article
      className="bg-surface rounded-xl border border-default p-4"
      aria-label={`Priority ${priority.calendarKeyword}: ${priority.name}`}
    >
      {/* Header: Badge BEFORE title */}
      <div className="flex items-center gap-2 mb-2">
        <span className={`px-2 py-0.5 text-xs font-medium rounded ${badgeColorClass}`}>
          {priority.calendarKeyword}
        </span>
        <h3 className="text-base font-semibold text-default truncate">
          {priority.name}
        </h3>
      </div>

      {/* Type badge and checkpoint */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xs text-secondary">{'\u21BB'} Flexible</span>
        {checkpointDays !== null && (
          <span className="text-xs text-secondary">
            {checkpointDays > 0 ? `${checkpointDays}d until check-in` : checkpointDays === 0 ? 'Check-in today' : 'Check-in overdue'}
          </span>
        )}
      </div>

      {/* Weekly hours target - only show if weeklyHourTarget exists */}
      {priority.weeklyHourTarget != null && (
        <div className="mb-3">
          <div className="flex items-center gap-2">
            <span className="text-sm text-secondary">
              {priority.weeklyHourTarget}h/week target
            </span>
            {/* Only show actual hours if value exists and is > 0 */}
            {priority.weeklyHourActual != null && priority.weeklyHourActual > 0 && (
              <span className="text-sm text-tertiary">
                ({priority.weeklyHourActual}h actual)
              </span>
            )}
          </div>
        </div>
      )}

      {/* Calendar keyword reminder */}
      <div className="mb-3 p-2 bg-surface-secondary rounded-lg">
        <p className="text-xs text-secondary">
          {'\uD83D\uDCC5'} Tag calendar events with <strong className="text-default">{priority.calendarKeyword}</strong> to track time
        </p>
      </div>

      {/* 1-Month Goal section */}
      {priority.desiredResult && (
        <div className="border-t border-subtle pt-3">
          <h4 className="text-xs font-medium text-tertiary uppercase tracking-wide mb-1">
            1-Month Goal
          </h4>
          {priority.checkpointDate && (
            <p className="text-xs text-tertiary mb-1">
              by {formatDate(priority.checkpointDate)}
            </p>
          )}
          <p className="text-sm text-default">
            {priority.desiredResult}
          </p>
        </div>
      )}
    </article>
  )
}
