import { useState, useRef, useEffect } from 'react'
import type { Priority } from '../types'
import { daysUntil, formatDate } from '../utils'
import { DeliverableItem } from './DeliverableItem'
import { AddDeliverableInput } from './AddDeliverableInput'
import { DeleteConfirmation } from './DeleteConfirmation'
import { Badge } from '@openai/apps-sdk-ui/components/Badge'
import { BADGE_COLORS, BADGE_CIRCLE_CLASS } from '../constants'

interface DeadlineCardProps {
  priority: Priority
  isEditing: boolean
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
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const days = priority.deadline ? daysUntil(priority.deadline) : null
  const doneCount = priority.deliverables.filter(d => d.done).length
  const totalCount = priority.deliverables.length

  const badgeColorClass = BADGE_COLORS[priority.calendarKeyword] ?? BADGE_COLORS.P1

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
    // Validate
    if (field === 'name' && !value.trim()) {
      setError('Name is required')
      setEditName(priority.name) // Revert
      return
    }
    if (field === 'deadline' && !value) {
      setError('Deadline is required')
      setEditDeadline(priority.deadline || '') // Revert
      return
    }

    // Check if value actually changed
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
      // Silence means success - no indicator needed
    } catch (e) {
      console.error('callTool error:', e)
      // Show error message from tool if available, otherwise generic
      const errorMsg = e instanceof Error ? e.message : 'Failed to save'
      setError(errorMsg)
      // Revert to original value
      if (field === 'name') {
        setEditName(priority.name)
      } else {
        setEditDeadline(priority.deadline || '')
      }
      // Clear error after 3s
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
    } finally {
      setIsDeleting(false)
    }
  }

  // Click outside to exit edit mode
  const handleCardClick = (e: React.MouseEvent) => {
    // Only exit if clicking the card background, not inputs/buttons
    if (e.target === e.currentTarget && isEditing && !isSaving) {
      onCancelEdit()
    }
  }

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
      className="bg-surface rounded-xl border border-default p-4"
      aria-label={`Priority ${priority.calendarKeyword}: ${priority.name}`}
      onClick={handleCardClick}
    >
      {/* Header: Badge + title + actions */}
      <div className="flex items-start gap-3 mb-2">
        <span className={`${BADGE_CIRCLE_CLASS} ${badgeColorClass}`}>
          {priority.calendarKeyword}
        </span>

        <div className="flex-1 min-w-0">
          {isEditing ? (
            <input
              type="text"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              onBlur={handleNameBlur}
              disabled={isSaving}
              maxLength={100}
              autoFocus
              className="w-full text-base font-semibold text-default bg-surface border border-default rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-info"
              aria-label="Priority name"
            />
          ) : (
            <h3
              className="text-base font-semibold text-default truncate cursor-pointer hover:text-info"
              onClick={(e) => { e.stopPropagation(); onStartEdit(); }}
              title="Click to edit"
            >
              {priority.name}
            </h3>
          )}

          {/* Type tag and calendar info below name */}
          <div className="flex items-center gap-2 mt-1">
            <Badge color="secondary" variant="soft" size="sm">Deadline-driven</Badge>
          </div>
          <div className="mt-2 p-2 bg-surface-secondary rounded-lg">
            <p className="text-xs text-secondary">
              📅 Use <strong className="text-default">{priority.calendarKeyword}</strong> in the calendar event title to track time
            </p>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1 flex-shrink-0">
          {/* Edit button (hidden when editing) */}
          {!isEditing && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onStartEdit(); }}
              className="p-1.5 text-tertiary hover:text-info rounded"
              aria-label={`Edit priority: ${priority.name}`}
            >
              <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M11.5 2.5l2 2M2 14l.5-2 9-9 2 2-9 9-2.5.5z"/>
              </svg>
            </button>
          )}

          {/* Delete button */}
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setShowDeleteConfirm(true); }}
            className="p-1.5 text-tertiary hover:text-danger rounded"
            aria-label={`Delete priority: ${priority.name}`}
          >
            <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M2 4h12M5.5 4V2.5a1 1 0 011-1h3a1 1 0 011 1V4"/>
              <path d="M12.5 4v9a1.5 1.5 0 01-1.5 1.5H5a1.5 1.5 0 01-1.5-1.5V4"/>
              <path d="M6.5 7v5M8 7v5M9.5 7v5"/>
            </svg>
          </button>
        </div>
      </div>

      {/* Error message */}
      {error && (
        <p className="text-xs text-danger mb-2" role="alert">{error}</p>
      )}

      {/* Progress info */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        {totalCount > 0 && (
          <span className="text-xs text-secondary">
            {doneCount} of {totalCount} done
            {days !== null && ` · ${days > 0 ? `${days}d left` : days === 0 ? 'Due today' : `${Math.abs(days)}d overdue`}`}
          </span>
        )}
        {totalCount === 0 && days !== null && (
          <span className="text-xs text-secondary">
            {days > 0 ? `${days}d left` : days === 0 ? 'Due today' : `${Math.abs(days)}d overdue`}
          </span>
        )}
      </div>

      {/* Deadline field - inline editable */}
      {isEditing ? (
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
            className="w-full text-sm text-default bg-surface border border-default rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-info"
          />
        </div>
      ) : (
        priority.deadline && (
          <div
            className="mb-3 text-xs text-tertiary cursor-pointer hover:text-info"
            onClick={(e) => { e.stopPropagation(); onStartEdit(); }}
            title="Click to edit"
          >
            Due: {formatDate(priority.deadline)}
          </div>
        )
      )}

      {/* E2E Deliverables */}
      <div className="border-t border-subtle pt-3">
        <h4 className="text-sm font-semibold text-default mb-2">
          E2E Deliverables
        </h4>
        {priority.deliverables.length > 0 ? (
          <ul className="space-y-1.5 mb-3" aria-label="Deliverables list">
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
          <p className="text-xs text-tertiary mb-3">No deliverables yet</p>
        )}
        <AddDeliverableInput
          priorityId={priority.id}
          onAdd={onAddDeliverable}
        />
      </div>

      {/* Edit mode hint */}
      {isEditing && (
        <p className="text-xs text-tertiary mt-3 text-center">
          Changes save automatically. Click outside to close.
        </p>
      )}
    </article>
  )
}
