import type { Goal } from '../types'

interface GoalItemProps {
  goal: Goal
}

/**
 * GoalItem - Display only version for Claude widget.
 * All edit/delete/toggle handlers removed.
 */
export function GoalItem({ goal }: GoalItemProps) {
  return (
    <li style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
      {/* Circular checkbox (display only) - 18px diameter */}
      <div
        style={{
          marginTop: '2px',
          width: '18px',
          height: '18px',
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          background: goal.achieved ? '#10b981' : 'transparent',
          border: goal.achieved ? 'none' : '1.5px solid var(--color-border, #e5e5e5)',
        }}
        role="checkbox"
        aria-checked={goal.achieved}
      >
        {goal.achieved && (
          <svg style={{ width: '10px', height: '10px', color: '#fff' }} viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M2 6l3 3 5-5" />
          </svg>
        )}
      </div>

      {/* Goal text */}
      <p
        style={{
          flex: 1,
          minWidth: 0,
          fontSize: '14px',
          overflowWrap: 'break-word',
          color: goal.achieved ? 'var(--color-text-tertiary, #8c8c8c)' : 'var(--color-text-primary, #0d0d0d)',
          textDecoration: goal.achieved ? 'line-through' : 'none',
        }}
      >
        {goal.text}
      </p>
    </li>
  )
}
