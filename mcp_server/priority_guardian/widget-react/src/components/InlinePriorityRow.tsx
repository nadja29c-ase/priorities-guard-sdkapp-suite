import type { Priority } from '../types'
import { daysUntil, formatDate } from '../utils'
import { BADGE_COLORS, BADGE_CIRCLE_CLASS, BORDER_COLORS } from '../constants'
import { t } from '../i18n'

interface InlinePriorityRowProps {
  priority: Priority
}

/**
 * Compact, static (non-interactive) row for inline mode — inc_card_size_fix2.md.
 * Deliberately does not render DeadlineCard/FlexibleCard's rich chrome (edit,
 * delete, deliverables/goals lists) — inline's only path to those is the
 * existing "Open full dashboard" CTA. Reuses the same data/formatting the
 * fullscreen cards already use (daysUntil, checkpointDate, avgTargetAchievement,
 * doneCount/totalCount, badge/border color tokens) rather than any new logic.
 */
export function InlinePriorityRow({ priority }: InlinePriorityRowProps) {
  const kw = priority.calendarKeyword
  const badgeColorClass = BADGE_COLORS[kw] ?? BADGE_COLORS.P1
  const borderColorClass = BORDER_COLORS[kw] ?? BORDER_COLORS.P1
  const isDeadline = priority.type === 'deadline'

  const days = isDeadline && priority.deadline ? daysUntil(priority.deadline) : null
  const statusLine = isDeadline
    ? days !== null
      ? days > 0
        ? t('dDaysLeft', { n: days })
        : days === 0
          ? t('dueToday')
          : t('dDaysOverdue', { n: Math.abs(days) })
      : null
    : priority.checkpointDate
      ? `${t('by')} ${formatDate(priority.checkpointDate)}`
      : null

  const doneCount = priority.deliverables.filter(d => d.done).length
  const totalCount = priority.deliverables.length
  const hasAvg = priority.avgTargetAchievement != null

  return (
    <div
      className={`rounded-xl px-3 py-2.5 bg-surface border border-default ${borderColorClass}`}
    >
      <div className="flex items-center gap-2">
        <span className={`${BADGE_CIRCLE_CLASS} ${badgeColorClass} text-2xs`}>
          {kw}
        </span>
        {/* truncate is visual-only (overflow/ellipsis) — the full name stays
            in the text node, so it stays in the accessibility tree even when
            clipped. title is supplemental (desktop hover), never load-bearing. */}
        <span
          className="text-sm font-semibold truncate flex-1 text-default"
          title={priority.name}
        >
          {priority.name}
        </span>
        {isDeadline ? (
          <span className="text-sm font-semibold tabular-nums text-default flex-shrink-0">
            {doneCount}/{totalCount}
          </span>
        ) : hasAvg ? (
          <span className="text-sm font-semibold tabular-nums text-default flex-shrink-0">
            ~{Math.round(priority.avgTargetAchievement!)}%
          </span>
        ) : (
          <span className="text-xs text-tertiary flex-shrink-0">
            {t('notEnoughDataYet')}
          </span>
        )}
      </div>
      {statusLine && (
        <p className="text-xs text-secondary mt-1 pl-8">
          {statusLine}
        </p>
      )}
    </div>
  )
}
