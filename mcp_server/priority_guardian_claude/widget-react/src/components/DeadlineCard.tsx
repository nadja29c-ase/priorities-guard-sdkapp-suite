import { useState } from 'react'
import type { Priority } from '../types'
import { daysUntil } from '../utils'
import { DeliverableItem } from './DeliverableItem'
import { ChevronIcon } from './ChevronIcon'
import { BADGE_COLORS, BORDER_COLORS, ICON_STROKE_COLORS } from '../constants'
import { t, getRawLocale } from '../i18n'

interface DeadlineCardProps {
  priority: Priority
  defaultDeliverablesExpanded?: boolean
  // All CRUD handlers removed for display-only mode
}

/**
 * DeadlineCard - Display only version for Claude widget.
 * No edit/delete handlers, no add deliverable input.
 */
export function DeadlineCard({
  priority,
  defaultDeliverablesExpanded = true,
}: DeadlineCardProps) {
  const [deliverablesExpanded, setDeliverablesExpanded] = useState(defaultDeliverablesExpanded)

  const days = priority.deadline ? daysUntil(priority.deadline) : null
  const doneCount = priority.deliverables.filter(d => d.done).length
  const totalCount = priority.deliverables.length

  const kw = priority.calendarKeyword
  const badgeColor = BADGE_COLORS[kw] ?? BADGE_COLORS.P1
  const borderColor = BORDER_COLORS[kw] ?? BORDER_COLORS.P1
  const iconStrokeColor = ICON_STROKE_COLORS[kw] ?? ICON_STROKE_COLORS.P1

  // Format deadline date for banner (e.g., "Mar 15, 2026")
  const locale = getRawLocale()
  const deadlineDate = priority.deadline
    ? new Date(priority.deadline + 'T00:00:00').toLocaleDateString(locale, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : ''

  return (
    <article
      style={{
        borderRadius: '12px',
        overflow: 'hidden',
        background: 'var(--color-background-primary, #fff)',
        border: '1px solid var(--color-border, #e5e5e5)',
        borderLeft: `3px solid ${borderColor}`,
      }}
      aria-label={priority.name}
    >
      {/* Deadline banner */}
      <div
        style={{
          padding: '10px 20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--color-background-secondary, #f9f9f9)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {/* Calendar icon */}
          <svg
            style={{ width: '14px', height: '14px', flexShrink: 0 }}
            viewBox="0 0 16 16"
            fill="none"
            stroke={iconStrokeColor}
            strokeWidth="1.5"
            aria-hidden="true"
          >
            <rect x="2" y="3" width="12" height="11" rx="1.5" />
            <path d="M5 1.5v3M11 1.5v3M2 7h12" />
          </svg>
          <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-text-secondary, #5c5c5c)' }}>
            {deadlineDate}
          </span>
        </div>
        <span style={{ fontSize: '12px', fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: 'var(--color-text-secondary, #5c5c5c)' }}>
          {days !== null && (
            days > 0
              ? t('dDaysLeft').replace('{n}', String(days))
              : days === 0
                ? t('dueToday')
                : t('dDaysOverdue').replace('{n}', String(Math.abs(days)))
          )}
        </span>
      </div>

      {/* Main content area */}
      <div style={{ padding: '20px' }}>
        {/* Header row: Badge + Name */}
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
        </div>

        {/* Lead measure - inline done/total + label */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
          <span style={{ fontSize: '24px', fontWeight: 700, fontVariantNumeric: 'tabular-nums', lineHeight: 1, color: 'var(--color-text-primary, #0d0d0d)' }}>
            {doneCount}
            <span style={{ fontSize: '18px', fontWeight: 400, color: 'var(--color-text-tertiary, #8c8c8c)' }}>
              /{totalCount}
            </span>
          </span>
          <span style={{ fontSize: '14px', color: 'var(--color-text-secondary, #5c5c5c)' }}>
            {t('deliverablesDone')}
          </span>
        </div>

        {/* E2E Deliverables - Collapsible */}
        <div style={{ paddingTop: '12px', borderTop: '1px solid var(--color-border-subtle, #f0f0f0)' }}>
          <button
            type="button"
            onClick={() => setDeliverablesExpanded(!deliverablesExpanded)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              width: '100%',
              marginBottom: '8px',
              background: 'none',
              border: 'none',
              padding: 0,
              cursor: 'pointer',
            }}
            aria-expanded={deliverablesExpanded}
          >
            <span style={{ fontSize: '12px', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-tertiary, #8c8c8c)' }}>
              {t('e2eDeliverables')}
            </span>
            <span style={{ fontSize: '12px', fontVariantNumeric: 'tabular-nums', color: 'var(--color-text-tertiary, #8c8c8c)' }}>
              ({doneCount}/{totalCount})
            </span>
            <span style={{ marginLeft: 'auto' }}>
              <ChevronIcon expanded={deliverablesExpanded} />
            </span>
          </button>

          {deliverablesExpanded && (
            <>
              {priority.deliverables.length > 0 ? (
                <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '6px' }} aria-label="Deliverables list">
                  {priority.deliverables.map((d) => (
                    <DeliverableItem key={d.id} deliverable={d} />
                  ))}
                </ul>
              ) : (
                <p style={{ fontSize: '12px', fontStyle: 'italic', color: 'var(--color-text-secondary, #5c5c5c)' }}>
                  {t('noDeliverablesHint')}
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </article>
  )
}
