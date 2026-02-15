import { useState, useRef, useEffect, useCallback } from 'react'
import type { Priority } from '../types'
import { daysUntil } from '../utils'
import { DeliverableItem } from './DeliverableItem'
import { AddDeliverableInput } from './AddDeliverableInput'
import { DeleteConfirmation } from './DeleteConfirmation'
import { ChevronIcon } from './ChevronIcon'
import { Button } from '@openai/apps-sdk-ui/components/Button'
import { BADGE_COLORS, BADGE_CIRCLE_CLASS } from '../constants'

// V7 accent colors for deadline banner
const ACCENT_COLORS: Record<string, { soft: string; accent: string; border: string }> = {
  P1: {
    soft: 'var(--color-background-info-soft-alpha, #eff6ff)',
    accent: 'var(--color-text-info, #0285ff)',
    border: '#0285ff',
  },
  P2: {
    soft: 'var(--color-background-discovery-soft-alpha, #faf5ff)',
    accent: 'var(--color-text-discovery, #924ff7)',
    border: '#924ff7',
  },
  P3: {
    soft: 'var(--color-background-caution-soft-alpha, #fefce8)',
    accent: 'var(--color-text-caution, #e0ac00)',
    border: '#ffc300',
  },
}

interface DeadlineCardProps {
  priority: Priority
  isEditing: boolean
  defaultDeliverablesExpanded?: boolean
  onStartEdit: () => void
  onCancelEdit: () => void
  onSave: (priorityId: string, data: { name?: string; deadline?: string }) => Promise<void>
  onDelete: (priorityId: string) => Promise<void>
  onToggleDeliverable: (deliverableId: string, done: boolean) => Promise<void>
  onRenameDeliverable: (deliverableId: string, name: string) => Promise<void>
  onDeleteDeliverable: (deliverableId: string) => Promise<void>
  onAddDeliverable: (priorityId: string, name: string) => Promise<void>
}

export function DeadlineCard({
  priority,
  isEditing,
  defaultDeliverablesExpanded = true,
  onStartEdit,
  onCancelEdit,
  onSave,
  onDelete,
  onToggleDeliverable,
  onRenameDeliverable,
  onDeleteDeliverable,
  onAddDeliverable,
}: DeadlineCardProps) {
  const [editName, setEditName] = useState(priority.name)
  const [editDeadline, setEditDeadline] = useState(priority.deadline || '')
  const [isSaving, setIsSaving] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deliverablesExpanded, setDeliverablesExpanded] = useState(defaultDeliverablesExpanded)
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cardRef = useRef<HTMLElement>(null)

  const days = priority.deadline ? daysUntil(priority.deadline) : null
  const doneCount = priority.deliverables.filter(d => d.done).length
  const totalCount = priority.deliverables.length

  const kw = priority.calendarKeyword
  const badgeColorClass = BADGE_COLORS[kw] ?? BADGE_COLORS.P1
  const colors = ACCENT_COLORS[kw] ?? ACCENT_COLORS.P1

  // Format deadline date for banner (e.g., "Mar 15, 2026")
  const deadlineDate = priority.deadline
    ? new Date(priority.deadline + 'T00:00:00').toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : ''

  // Get tomorrow's date for min date constraint
  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  const minDate = tomorrow.toISOString().split('T')[0]

  // Reset local state when priority changes from parent
  useEffect(() => {
    setEditName(priority.name)
    setEditDeadline(priority.deadline || '')
  }, [priority.name, priority.deadline])

  // Clear timeout on unmount
  useEffect(() => {
    return () => {
      if (errorTimeoutRef.current) {
        clearTimeout(errorTimeoutRef.current)
      }
    }
  }, [])

  const autoSave = async (field: 'name' | 'deadline', value: string) => {
    if (field === 'name' && !value.trim()) {
      setError('Name is required')
      setEditName(priority.name)
      return
    }
    if (field === 'deadline' && !value) {
      setError('Deadline is required')
      setEditDeadline(priority.deadline || '')
      return
    }

    const originalValue = field === 'name' ? priority.name : priority.deadline
    if (value === originalValue) {
      return
    }

    setError(null)
    setIsSaving(true)

    try {
      const updates = field === 'name'
        ? { name: value.trim() }
        : { deadline: value }
      await onSave(priority.id, updates)
    } catch (e) {
      console.error('callTool error:', e)
      const errorMsg = e instanceof Error ? e.message : 'Failed to save'
      setError(errorMsg)
      if (field === 'name') {
        setEditName(priority.name)
      } else {
        setEditDeadline(priority.deadline || '')
      }
      errorTimeoutRef.current = setTimeout(() => {
        setError(null)
      }, 3000)
    } finally {
      setIsSaving(false)
    }
  }

  const handleNameBlur = () => {
    if (editName.trim() !== priority.name) {
      autoSave('name', editName)
    }
  }

  const handleDeadlineBlur = () => {
    if (editDeadline !== priority.deadline) {
      autoSave('deadline', editDeadline)
    }
  }

  const handleDelete = async () => {
    setIsDeleting(true)
    try {
      await onDelete(priority.id)
    } catch (e) {
      console.error('Delete error:', e)
      const errorMsg = e instanceof Error ? e.message : "Couldn't save. Try again."
      setError(errorMsg)
      setShowDeleteConfirm(false)
      errorTimeoutRef.current = setTimeout(() => {
        setError(null)
      }, 3000)
    } finally {
      setIsDeleting(false)
    }
  }

  const handleClickOutside = useCallback((e: MouseEvent) => {
    if (isEditing && !isSaving && cardRef.current && !cardRef.current.contains(e.target as Node)) {
      onCancelEdit()
    }
  }, [isEditing, isSaving, onCancelEdit])

  useEffect(() => {
    if (isEditing) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isEditing, handleClickOutside])

  if (showDeleteConfirm) {
    return (
      <DeleteConfirmation
        itemName={priority.name}
        itemType="priority"
        calendarKeyword={priority.calendarKeyword}
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteConfirm(false)}
        isDeleting={isDeleting}
      />
    )
  }

  return (
    <article
      ref={cardRef}
      className="rounded-xl overflow-hidden"
      style={{
        background: 'var(--gray-0, #ffffff)',
        border: '1px solid var(--gray-100, #ededed)',
        borderLeft: `4px solid ${colors.border}`,
      }}
      aria-label={`Priority ${kw}: ${priority.name}`}
    >
      {/* V7: Colored deadline banner at top */}
      <div
        className="px-5 py-2.5 flex items-center justify-between"
        style={{ background: colors.soft }}
      >
        <div className="flex items-center gap-2">
          {/* Calendar icon */}
          <svg
            className="w-3.5 h-3.5 flex-shrink-0"
            viewBox="0 0 16 16"
            fill="none"
            stroke={colors.accent}
            strokeWidth="1.5"
          >
            <rect x="2" y="3" width="12" height="11" rx="1.5" />
            <path d="M5 1.5v3M11 1.5v3M2 7h12" />
          </svg>
          <span
            className="text-xs font-semibold"
            style={{ color: colors.accent }}
          >
            {deadlineDate}
          </span>
        </div>
        <span
          className="text-xs font-bold tabular-nums"
          style={{ color: colors.accent }}
        >
          {days !== null && (
            days > 0 ? `${days}d left` : days === 0 ? 'Due today' : `${Math.abs(days)}d overdue`
          )}
        </span>
      </div>

      {/* Main content area */}
      <div className="p-5">
        {/* Header row: Badge + Name + Edit/Trash */}
        <div className="flex items-center gap-2 mb-3">
          <span
            className={`${BADGE_CIRCLE_CLASS} ${badgeColorClass}`}
            style={{ fontSize: '0.65rem' }}
          >
            {kw}
          </span>
          {isEditing ? (
            <input
              type="text"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              onBlur={handleNameBlur}
              disabled={isSaving}
              maxLength={100}
              autoFocus
              className="flex-1 text-sm font-semibold text-default bg-surface border border-default rounded-lg px-2 py-1 focus:outline-none focus:border-tertiary"
              style={{ color: 'var(--gray-900, #181818)' }}
              aria-label="Priority name"
            />
          ) : (
            <h3
              className="text-sm font-semibold flex-1 truncate cursor-pointer hover:opacity-80"
              style={{ color: 'var(--gray-900, #181818)' }}
              onClick={(e) => { e.stopPropagation(); onStartEdit(); }}
              title="Click to edit"
            >
              {priority.name}
            </h3>
          )}
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onStartEdit(); }}
            className="p-1 rounded hover:bg-surface-secondary transition-colors"
            title="Edit"
            aria-label={`Edit priority: ${priority.name}`}
          >
            <svg className="w-3.5 h-3.5" style={{ color: 'var(--gray-350, #9f9f9f)' }} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M11.5 2.5l2 2M2 14l.5-2 9-9 2 2-9 9-2.5.5z" />
            </svg>
          </button>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setShowDeleteConfirm(true); }}
            className="p-1 rounded hover:bg-danger-soft-alpha transition-colors"
            title="Delete priority"
            aria-label={`Delete priority: ${priority.name}`}
          >
            <svg className="w-3.5 h-3.5" style={{ color: 'var(--gray-350, #9f9f9f)' }} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M2 4h12M5.5 4V2.5a1 1 0 011-1h3a1 1 0 011 1V4" />
              <path d="M12.5 4v9a1.5 1.5 0 01-1.5 1.5H5a1.5 1.5 0 01-1.5-1.5V4" />
              <path d="M6.5 7v5M9.5 7v5" />
            </svg>
          </button>
        </div>

        {/* Error message */}
        {error && (
          <p className="text-xs text-danger mb-2" role="alert">{error}</p>
        )}

        {/* V7: Lead measure - inline done/total + label */}
        <div className="flex items-center gap-2 mb-4">
          <span
            className="text-2xl font-bold tabular-nums leading-none"
            style={{ color: 'var(--gray-900, #181818)' }}
          >
            {doneCount}
            <span
              className="text-lg font-normal"
              style={{ color: 'var(--gray-350, #9f9f9f)' }}
            >
              /{totalCount}
            </span>
          </span>
          <span
            className="text-sm"
            style={{ color: 'var(--gray-450, #767676)' }}
          >
            Deliverables done
          </span>
        </div>

        {/* Deadline field - editable in edit mode */}
        {isEditing && (
          <div className="mb-3">
            <label htmlFor={`deadline-${priority.id}`} className="block text-xs font-medium text-secondary mb-1">
              Deadline
            </label>
            <input
              id={`deadline-${priority.id}`}
              type="date"
              value={editDeadline}
              onChange={(e) => setEditDeadline(e.target.value)}
              onBlur={handleDeadlineBlur}
              disabled={isSaving}
              min={minDate}
              className="w-full text-sm text-default bg-surface border border-default rounded-xl px-3 py-2 focus:outline-none focus:border-tertiary"
            />
          </div>
        )}

        {/* E2E Deliverables - Collapsible */}
        <div className="pt-3" style={{ borderTop: '1px solid var(--gray-75, #f3f3f3)' }}>
          <button
            onClick={() => setDeliverablesExpanded(!deliverablesExpanded)}
            className="flex items-center gap-1.5 w-full mb-2 hover:opacity-80 transition-opacity"
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
          >
            <h4
              className="text-xs font-medium uppercase tracking-wide"
              style={{ color: 'var(--gray-400, #8f8f8f)' }}
            >
              E2E Deliverables
            </h4>
            <span
              className="text-xs tabular-nums"
              style={{ color: 'var(--gray-350, #9f9f9f)' }}
            >
              ({doneCount}/{totalCount})
            </span>
            <span className="ml-auto">
              <ChevronIcon expanded={deliverablesExpanded} />
            </span>
          </button>

          {deliverablesExpanded && (
            <>
              {priority.deliverables.length > 0 ? (
                <ul className="space-y-1.5 mb-2" aria-label="Deliverables list">
                  {priority.deliverables.map((d) => (
                    <DeliverableItem
                      key={d.id}
                      deliverable={d}
                      onToggle={onToggleDeliverable}
                      onRename={onRenameDeliverable}
                      onDelete={onDeleteDeliverable}
                      disabled={false}
                    />
                  ))}
                </ul>
              ) : (
                <p className="text-xs mb-2" style={{ color: 'var(--gray-450, #767676)' }}>
                  Without E2E deliverables, you only see hours spent — add them to track real progress.
                </p>
              )}
              <AddDeliverableInput
                priorityId={priority.id}
                onAdd={onAddDeliverable}
              />
            </>
          )}
        </div>

        {/* Edit mode actions */}
        {isEditing && (
          <div className="mt-4 flex items-center justify-between">
            <p className="text-xs text-tertiary">
              Changes save automatically
            </p>
            <Button
              color="secondary"
              variant="ghost"
              size="sm"
              onClick={onCancelEdit}
              disabled={isSaving}
            >
              Done
            </Button>
          </div>
        )}
      </div>
    </article>
  )
}
