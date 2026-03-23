import { useState } from 'react'
import type { Goal } from '../types'
import { GoalItem } from './GoalItem'
import { ChevronIcon } from './ChevronIcon'
import { getRawLocale } from '../i18n'
import { t } from '../i18n'

interface GoalSectionProps {
  goals: Goal[]
  checkpointDate?: string
  defaultExpanded?: boolean
  // All CRUD handlers removed for display-only mode
}

/**
 * GoalSection - Display only version for Claude widget.
 * No add/edit/delete handlers.
 */
export function GoalSection({
  goals,
  checkpointDate,
  defaultExpanded = false,
}: GoalSectionProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  // Collapsible if multiple goals OR currently collapsed (allows re-expand)
  const isCollapsible = goals.length > 1 || !expanded

  // Format checkpoint date
  const formatDate = (dateStr: string) => {
    const locale = getRawLocale()
    const date = new Date(dateStr + 'T00:00:00')
    return date.toLocaleDateString(locale, { month: 'short', day: 'numeric' })
  }

  const achievedCount = goals.filter(g => g.achieved).length

  return (
    <div style={{ borderTop: '1px solid var(--color-border-subtle, #f0f0f0)', paddingTop: '12px' }}>
      {/* Header */}
      <button
        type="button"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          marginBottom: '8px',
          width: '100%',
          textAlign: 'left',
          background: 'none',
          border: 'none',
          padding: 0,
          cursor: isCollapsible ? 'pointer' : 'default',
        }}
        onClick={() => isCollapsible && setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-label={goals.length === 1 ? t('oneMonthGoal') : t('oneMonthGoals')}
      >
        {isCollapsible && (
          <ChevronIcon expanded={expanded} />
        )}
        <span
          style={{
            fontSize: '12px',
            fontWeight: 500,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            color: 'var(--color-text-tertiary, #8c8c8c)',
          }}
        >
          {goals.length === 1 ? t('oneMonthGoal') : t('oneMonthGoals')}
        </span>
        {checkpointDate && (
          <span style={{ fontSize: '12px', color: 'var(--color-text-tertiary, #8c8c8c)' }}>
            {t('by')} {formatDate(checkpointDate)}
          </span>
        )}
        {goals.length > 0 && (
          <span style={{ fontSize: '12px', color: 'var(--color-text-secondary, #5c5c5c)', marginLeft: 'auto' }}>
            {achievedCount}/{goals.length}
          </span>
        )}
      </button>

      {/* Goals list */}
      {(expanded || !isCollapsible) && (
        <>
          {goals.length > 0 ? (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '8px' }} aria-label="Goals list">
              {goals.map((goal) => (
                <GoalItem key={goal.id} goal={goal} />
              ))}
            </ul>
          ) : (
            <p style={{ fontSize: '12px', color: 'var(--color-text-tertiary, #8c8c8c)', marginBottom: '8px' }}>{t('noGoalsYet')}</p>
          )}
        </>
      )}
    </div>
  )
}
