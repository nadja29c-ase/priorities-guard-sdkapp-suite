import type { Deliverable } from '../types'

interface DeliverableItemProps {
  deliverable: Deliverable
}

/**
 * DeliverableItem - Display only version for Claude widget.
 * All edit/delete handlers removed.
 */
export function DeliverableItem({ deliverable }: DeliverableItemProps) {
  return (
    <li style={{ paddingBottom: '8px', borderBottom: '1px solid var(--color-border-subtle, #f0f0f0)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {/* Checkbox (display only) */}
        <div
          style={{
            width: '16px',
            height: '16px',
            borderRadius: '4px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            background: deliverable.done ? 'var(--color-text-tertiary, #8c8c8c)' : 'transparent',
            border: deliverable.done ? 'none' : '1.5px solid var(--color-border, #e5e5e5)',
          }}
          role="checkbox"
          aria-checked={deliverable.done}
        >
          {deliverable.done && (
            <svg style={{ width: '10px', height: '10px', color: '#fff' }} viewBox="0 0 12 12" fill="none" aria-hidden="true">
              <path d="M2 6L5 9L10 3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          )}
        </div>

        {/* Name */}
        <span
          style={{
            flex: 1,
            fontSize: '14px',
            overflowWrap: 'break-word',
            color: deliverable.done ? 'var(--color-text-tertiary, #8c8c8c)' : 'var(--color-text-primary, #0d0d0d)',
            textDecoration: deliverable.done ? 'line-through' : 'none',
          }}
        >
          {deliverable.name}
        </span>
      </div>
    </li>
  )
}
