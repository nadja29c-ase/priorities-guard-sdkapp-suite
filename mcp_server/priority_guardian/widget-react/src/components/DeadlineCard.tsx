import type { Priority } from '../types'
import { daysUntil, formatDate } from '../utils'
import { Badge } from '@openai/apps-sdk-ui/components/Badge'

interface DeadlineCardProps {
  priority: Priority
}

export function DeadlineCard({ priority }: DeadlineCardProps) {
  const days = priority.deadline ? daysUntil(priority.deadline) : null
  const doneCount = priority.deliverables.filter(d => d.done).length
  const totalCount = priority.deliverables.length

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

      {/* Type badge and progress */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <span className="text-xs text-secondary">{'\u23F1'} Deadline</span>
        {totalCount > 0 && (
          <span className="text-xs text-secondary">
            {doneCount} of {totalCount} done
            {days !== null && ` \u00B7 ${days > 0 ? `${days}d left` : days === 0 ? 'Due today' : `${Math.abs(days)}d overdue`}`}
          </span>
        )}
        {totalCount === 0 && days !== null && (
          <span className="text-xs text-secondary">
            {days > 0 ? `${days}d left` : days === 0 ? 'Due today' : `${Math.abs(days)}d overdue`}
          </span>
        )}
      </div>

      {/* Calendar keyword reminder */}
      <div className="mb-3 p-2 bg-surface-secondary rounded-lg">
        <p className="text-xs text-secondary">
          {'\uD83D\uDCC5'} Tag calendar events with <strong className="text-default">{priority.calendarKeyword}</strong> to track time
        </p>
      </div>

      {/* Deliverables (read-only) */}
      {priority.deliverables.length > 0 && (
        <div className="border-t border-subtle pt-3">
          <h4 className="text-xs font-medium text-tertiary uppercase tracking-wide mb-2">
            Deliverables
          </h4>
          <ul className="space-y-1.5" aria-label="Deliverables list">
            {priority.deliverables.map((d) => (
              <li key={d.id} className="flex items-center gap-2">
                <div
                  className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 ${
                    d.done
                      ? 'bg-success border-success'
                      : 'border-default'
                  }`}
                  aria-hidden="true"
                >
                  {d.done && (
                    <svg className="w-2.5 h-2.5 text-white" viewBox="0 0 12 12" fill="none">
                      <path d="M2 6L5 9L10 3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  )}
                </div>
                <span className={`text-sm ${d.done ? 'text-tertiary line-through' : 'text-default'}`}>
                  {d.name}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Deadline date */}
      {priority.deadline && (
        <div className="mt-3 text-xs text-tertiary">
          Due: {formatDate(priority.deadline)}
        </div>
      )}
    </article>
  )
}
