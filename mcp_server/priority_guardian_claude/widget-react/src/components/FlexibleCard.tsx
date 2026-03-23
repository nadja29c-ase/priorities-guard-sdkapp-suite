import type { Priority } from '../types'
import { GoalSection } from './GoalSection'
import { HourRing } from './HourRing'
import { BADGE_COLORS, BORDER_COLORS } from '../constants'
import { t } from '../i18n'

interface FlexibleCardProps {
  priority: Priority
  defaultGoalsExpanded?: boolean
  // All CRUD handlers removed for display-only mode
}

/**
 * FlexibleCard - Display only version for Claude widget.
 * No edit/delete handlers, no add goal input.
 */
export function FlexibleCard({
  priority,
  defaultGoalsExpanded = true,
}: FlexibleCardProps) {
  const kw = priority.calendarKeyword
  const badgeColor = BADGE_COLORS[kw] ?? BADGE_COLORS.P1
  const borderColor = BORDER_COLORS[kw] ?? BORDER_COLORS.P1

  const hasAvg = priority.avgTargetAchievement != null

  return (
    <article
      style={{
        borderRadius: '12px',
        padding: '20px',
        background: 'var(--color-background-primary, #fff)',
        border: '1px solid var(--color-border, #e5e5e5)',
        borderLeft: `3px solid ${borderColor}`,
      }}
      aria-label={priority.name}
    >
      {/* Header: Badge + Name + Streak pill */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '24px',
            height: '24px',
            borderRadius: '50%',
            fontSize: '10px',
            fontWeight: 700,
            background: badgeColor.bg,
            color: badgeColor.text,
          }}
        >
          {kw}
        </span>
        <h3
          style={{
            flex: 1,
            fontSize: '14px',
            fontWeight: 600,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            color: 'var(--color-text-primary, #0d0d0d)',
            margin: 0,
          }}
        >
          {priority.name}
        </h3>
        {/* Streak as pill */}
        {priority.streakCount != null && priority.streakCount > 0 && (
          <span
            style={{
              fontSize: '12px',
              fontVariantNumeric: 'tabular-nums',
              padding: '2px 6px',
              borderRadius: '9999px',
              fontWeight: 500,
              color: 'var(--color-text-primary, #0d0d0d)',
              background: 'var(--color-background-tertiary, #ebebeb)',
            }}
          >
            {t('weekStreak').replace('{n}', String(priority.streakCount))}
          </span>
        )}
      </div>

      {/* HourRing on left + Avg stats on right */}
      {priority.weeklyHourTarget != null && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '16px' }}>
          <HourRing
            actual={priority.weeklyHourActual ?? 0}
            target={priority.weeklyHourTarget}
            keyword={kw}
          />
          <div style={{ flex: 1 }}>
            {hasAvg ? (
              <>
                <span style={{ fontSize: '24px', fontWeight: 700, fontVariantNumeric: 'tabular-nums', lineHeight: 1, color: 'var(--color-text-primary, #0d0d0d)' }}>
                  ~{Math.round(priority.avgTargetAchievement!)}%
                </span>
                <p style={{ fontSize: '12px', marginTop: '2px', color: 'var(--color-text-secondary, #5c5c5c)' }}>
                  {t('ofWeeklyTargetOnAvg')}
                </p>
              </>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <svg
                  style={{ width: '14px', height: '14px', flexShrink: 0, color: 'var(--color-text-tertiary, #8c8c8c)' }}
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M4 2h8M4 14h8M5 2v2c0 1.5 1 3 3 4-2 1-3 2.5-3 4v2M11 2v2c0 1.5-1 3-3 4 2 1 3 2.5 3 4v2" />
                </svg>
                <span style={{ fontSize: '14px', fontStyle: 'italic', color: 'var(--color-text-tertiary, #8c8c8c)' }}>
                  {t('trackingInProgress')}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Goals section */}
      <GoalSection
        goals={priority.goals ?? []}
        checkpointDate={priority.checkpointDate}
        defaultExpanded={defaultGoalsExpanded}
      />
    </article>
  )
}
