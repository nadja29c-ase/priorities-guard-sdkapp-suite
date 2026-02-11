import { useState, useRef, useEffect } from 'react'
import type { Priority } from '../types'
import { daysUntil, formatDate } from '../utils'
import { DeliverableItem } from './DeliverableItem'
import { AddDeliverableInput } from './AddDeliverableInput'
import { DeleteConfirmation } from './DeleteConfirmation'
import { Badge } from '@openai/apps-sdk-ui/components/Badge'
import { BADGE_COLORS, BADGE_CIRCLE_CLASS } from '../constants'

interface FlexibleCardProps {
  priority: Priority
  isEditing: boolean
  onStartEdit: () => void
  onCancelEdit: () => void
  onSave: (priorityId: string, data: {
    name?: string
    weekly_hour_target?: number
    checkpoint_date?: string
    desired_result?: string
  }) => Promise<void>
  onDelete: (priorityId: string) => Promise<void>
  onToggleDeliverable: (deliverableId: string, done: boolean) => Promise<void>
  onRenameDeliverable: (deliverableId: string, name: string) => Promise<void>
  onDeleteDeliverable: (deliverableId: string) => Promise<void>
  onAddDeliverable: (priorityId: string, name: string) => Promise<void>
}

export function FlexibleCard({
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
}: FlexibleCardProps) {
  const [editName, setEditName] = useState(priority.name)
  const [editHourTarget, setEditHourTarget] = useState(priority.weeklyHourTarget?.toString() || '')
  const [editCheckpointDate, setEditCheckpointDate] = useState(priority.checkpointDate || '')
  const [editDesiredResult, setEditDesiredResult] = useState(priority.desiredResult || '')
  const [isSaving, setIsSaving] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const checkpointDays = priority.checkpointDate ? daysUntil(priority.checkpointDate) : null
  const badgeColorClass = BADGE_COLORS[priority.calendarKeyword] ?? BADGE_COLORS.P1

  // Get tomorrow's date for min date constraint
  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  const minDate = tomorrow.toISOString().split('T')[0]

  // Reset local state when priority changes from parent
  useEffect(() => {
    setEditName(priority.name)
    setEditHourTarget(priority.weeklyHourTarget?.toString() || '')
    setEditCheckpointDate(priority.checkpointDate || '')
    setEditDesiredResult(priority.desiredResult || '')
  }, [priority.name, priority.weeklyHourTarget, priority.checkpointDate, priority.desiredResult])

  // Clear timeout on unmount
  useEffect(() => {
    return () => {
      if (errorTimeoutRef.current) {
        clearTimeout(errorTimeoutRef.current)
      }
    }
  }, [])

  const autoSave = async (
    field: 'name' | 'weekly_hour_target' | 'checkpoint_date' | 'desired_result',
    value: string
  ) => {
    // Validate based on field
    if (field === 'name' && !value.trim()) {
      setError('Name is required')
      setEditName(priority.name)
      return
    }
    if (field === 'weekly_hour_target') {
      const numVal = parseFloat(value)
      if (!value || isNaN(numVal) || numVal <= 0) {
        setError('Weekly hours must be > 0')
        setEditHourTarget(priority.weeklyHourTarget?.toString() || '')
        return
      }
    }

    // Check if value actually changed
    let originalValue: string | number | null = null
    if (field === 'name') originalValue = priority.name
    else if (field === 'weekly_hour_target') originalValue = priority.weeklyHourTarget?.toString() || ''
    else if (field === 'checkpoint_date') originalValue = priority.checkpointDate || ''
    else if (field === 'desired_result') originalValue = priority.desiredResult || ''

    if (value === originalValue) {
      return
    }

    setError(null)
    setIsSaving(true)

    try {
      const updates: Record<string, string | number> = {}
      if (field === 'name') {
        updates.name = value.trim()
      } else if (field === 'weekly_hour_target') {
        updates.weekly_hour_target = parseFloat(value)
      } else if (field === 'checkpoint_date') {
        updates.checkpoint_date = value
      } else if (field === 'desired_result') {
        updates.desired_result = value.trim()
      }

      await onSave(priority.id, updates)
      // Silence means success - no indicator needed
    } catch (e) {
      console.error('callTool error:', e)
      // Show error message from tool if available, otherwise generic
      const errorMsg = e instanceof Error ? e.message : 'Failed to save'
      setError(errorMsg)
      // Revert to original value
      if (field === 'name') setEditName(priority.name)
      else if (field === 'weekly_hour_target') setEditHourTarget(priority.weeklyHourTarget?.toString() || '')
      else if (field === 'checkpoint_date') setEditCheckpointDate(priority.checkpointDate || '')
      else if (field === 'desired_result') setEditDesiredResult(priority.desiredResult || '')

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

  const handleHourTargetBlur = () => {
    if (editHourTarget !== (priority.weeklyHourTarget?.toString() || '')) {
      autoSave('weekly_hour_target', editHourTarget)
    }
  }

  const handleCheckpointBlur = () => {
    if (editCheckpointDate !== (priority.checkpointDate || '')) {
      autoSave('checkpoint_date', editCheckpointDate)
    }
  }

  const handleDesiredResultBlur = () => {
    if (editDesiredResult.trim() !== (priority.desiredResult || '')) {
      autoSave('desired_result', editDesiredResult)
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
            <Badge color="secondary" variant="soft" size="sm">Flexible</Badge>
            {!isEditing && checkpointDays !== null && (
              <span className="text-xs text-secondary">
                {checkpointDays > 0 ? `${checkpointDays}d until check-in` : checkpointDays === 0 ? 'Check-in today' : 'Check-in overdue'}
              </span>
            )}
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

      {/* Edit mode: All flexible fields with auto-save on blur */}
      {isEditing ? (
        <div className="space-y-3 mb-3">
          <div>
            <label htmlFor={`hours-${priority.id}`} className="block text-xs font-medium text-secondary mb-1">
              Weekly Hour Target
            </label>
            <input
              id={`hours-${priority.id}`}
              type="number"
              value={editHourTarget}
              onChange={(e) => setEditHourTarget(e.target.value)}
              onBlur={handleHourTargetBlur}
              disabled={isSaving}
              min="0.5"
              step="0.5"
              className="w-full text-sm text-default bg-surface border border-default rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-info"
            />
          </div>

          <div>
            <label htmlFor={`checkpoint-${priority.id}`} className="block text-xs font-medium text-secondary mb-1">
              Checkpoint Date
            </label>
            <input
              id={`checkpoint-${priority.id}`}
              type="date"
              value={editCheckpointDate}
              onChange={(e) => setEditCheckpointDate(e.target.value)}
              onBlur={handleCheckpointBlur}
              disabled={isSaving}
              min={minDate}
              className="w-full text-sm text-default bg-surface border border-default rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-info"
            />
          </div>

          <div>
            <label htmlFor={`result-${priority.id}`} className="block text-xs font-medium text-secondary mb-1">
              Desired Result
            </label>
            <textarea
              id={`result-${priority.id}`}
              value={editDesiredResult}
              onChange={(e) => setEditDesiredResult(e.target.value)}
              onBlur={handleDesiredResultBlur}
              disabled={isSaving}
              maxLength={200}
              rows={2}
              className="w-full text-sm text-default bg-surface border border-default rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-info resize-none"
            />
          </div>
        </div>
      ) : (
        <>
          {/* Weekly hours target - clickable to edit */}
          {priority.weeklyHourTarget != null && (
            <div
              className="mb-3 cursor-pointer hover:text-info"
              onClick={(e) => { e.stopPropagation(); onStartEdit(); }}
              title="Click to edit"
            >
              <div className="flex items-center gap-2">
                <span className="text-sm text-secondary">
                  {priority.weeklyHourTarget}h/week target
                </span>
                {priority.weeklyHourActual != null && priority.weeklyHourActual > 0 && (
                  <span className="text-sm text-tertiary">
                    ({priority.weeklyHourActual}h actual)
                  </span>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {/* 1-Month Goal section - clickable to edit */}
      {!isEditing && priority.desiredResult && (
        <div
          className="border-t border-subtle pt-3 cursor-pointer hover:bg-surface-secondary rounded-lg -mx-2 px-2"
          onClick={(e) => { e.stopPropagation(); onStartEdit(); }}
          title="Click to edit"
        >
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

      {/* E2E Deliverables */}
      <div className={`border-t border-subtle pt-3 ${!isEditing && priority.desiredResult ? 'mt-3' : ''}`}>
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
