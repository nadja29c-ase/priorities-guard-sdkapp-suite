import type { Priority } from '../types'
import { daysUntil, formatDate } from '../utils'
import { Badge } from '@openai/apps-sdk-ui/components/Badge'

interface FlexibleCardProps {
  priority: Priority
}

export function FlexibleCard({ priority }: FlexibleCardProps) {
  const checkpointDays = priority.checkpointDate ? daysUntil(priority.checkpointDate) : null

  // Badge color based on keyword
  const badgeColor = priority.calendarKeyword === 'P1' ? 'success'
    : priority.calendarKeyword === 'P2' ? 'warning'
    : 'danger'

  return (
    <article
      className="bg-surface rounded-xl border border-default p-4"
      aria-label={`Priority ${priority.calendarKeyword}: ${priority.name}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-default truncate">
            {priority.name}
          </h3>
        </div>
        <Badge color={badgeColor} variant="solid" size="sm">
          {priority.calendarKeyword}
        </Badge>
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

      {/* Weekly hours target */}
      {priority.weeklyHourTarget && (
        <div className="mb-3">
          <div className="flex items-center gap-2">
            <span className="text-sm text-secondary">
              {priority.weeklyHourTarget}h/week target
            </span>
            {priority.weeklyHourActual !== undefined && (
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
