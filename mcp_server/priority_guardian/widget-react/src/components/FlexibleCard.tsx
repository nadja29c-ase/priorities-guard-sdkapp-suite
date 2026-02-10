import { useState } from 'react'
import { Button } from '@openai/apps-sdk-ui/components/Button'
import type { Priority } from '../types'
import { daysUntil, formatDate } from '../utils'
import { DeliverableItem } from './DeliverableItem'
import { AddDeliverableInput } from './AddDeliverableInput'
import { DeleteConfirmation } from './DeleteConfirmation'
import { BADGE_COLORS } from '../constants'

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

  const checkpointDays = priority.checkpointDate ? daysUntil(priority.checkpointDate) : null
  const badgeColorClass = BADGE_COLORS[priority.calendarKeyword] ?? BADGE_COLORS.P1

  // Get tomorrow's date for min date constraint
  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  const minDate = tomorrow.toISOString().split('T')[0]

  const handleSave = async () => {
    if (isSaving) return
    setError(null)

    const updates: {
      name?: string
      weekly_hour_target?: number
      checkpoint_date?: string
      desired_result?: string
    } = {}

    if (editName.trim() !== priority.name) {
      if (!editName.trim()) {
        setError('Name is required')
        return
      }
      updates.name = editName.trim()
    }

    const newHourTarget = editHourTarget ? parseFloat(editHourTarget) : null
    if (newHourTarget !== priority.weeklyHourTarget) {
      if (!editHourTarget || newHourTarget === null || newHourTarget <= 0) {
        setError('Weekly hour target must be greater than 0')
        return
      }
      updates.weekly_hour_target = newHourTarget
    }

    if (editCheckpointDate !== priority.checkpointDate) {
      if (!editCheckpointDate) {
        setError('Checkpoint date is required')
        return
      }
      updates.checkpoint_date = editCheckpointDate
    }

    if (editDesiredResult.trim() !== (priority.desiredResult || '')) {
      if (!editDesiredResult.trim()) {
        setError('Desired result is required')
        return
      }
      updates.desired_result = editDesiredResult.trim()
    }

    if (Object.keys(updates).length === 0) {
      onCancelEdit()
      return
    }

    setIsSaving(true)
    try {
      await onSave(priority.id, updates)
    } catch (e) {
      setError('Failed to save changes')
    } finally {
      setIsSaving(false)
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

  const handleCancelEdit = () => {
    setEditName(priority.name)
    setEditHourTarget(priority.weeklyHourTarget?.toString() || '')
    setEditCheckpointDate(priority.checkpointDate || '')
    setEditDesiredResult(priority.desiredResult || '')
    setError(null)
    onCancelEdit()
  }

  if (showDeleteConfirm) {
    return (
      <article className="bg-surface rounded-xl border border-default p-4">
        <DeleteConfirmation
          itemName={priority.name}
          itemType="priority"
          onConfirm={handleDelete}
          onCancel={() => setShowDeleteConfirm(false)}
          isDeleting={isDeleting}
        />
      </article>
    )
  }

  return (
    <article
      className="bg-surface rounded-xl border border-default p-4"
      aria-label={`Priority ${priority.calendarKeyword}: ${priority.name}`}
    >
      {/* Header: Badge + title + actions */}
      <div className="flex items-start gap-2 mb-2">
        <span className={`px-2 py-0.5 text-xs font-medium rounded flex-shrink-0 ${badgeColorClass}`}>
          {priority.calendarKeyword}
        </span>

        {isEditing ? (
          <input
            type="text"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            disabled={isSaving}
            maxLength={100}
            className="flex-1 text-base font-semibold text-default bg-surface border border-default rounded px-2 py-0.5 focus:outline-none focus:ring-1 focus:ring-info"
            aria-label="Priority name"
          />
        ) : (
          <h3 className="flex-1 text-base font-semibold text-default truncate">
            {priority.name}
          </h3>
        )}

        {/* Edit/Delete buttons */}
        {!isEditing && (
          <div className="flex gap-1 flex-shrink-0">
            <button
              type="button"
              onClick={onStartEdit}
              className="p-1.5 text-tertiary hover:text-default rounded"
              aria-label={`Edit priority: ${priority.name}`}
            >
              <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M11.5 2.5l2 2M2 14l.5-2 9-9 2 2-9 9-2.5.5z"/>
              </svg>
            </button>
            <button
              type="button"
              onClick={() => setShowDeleteConfirm(true)}
              className="p-1.5 text-tertiary hover:text-danger rounded"
              aria-label={`Delete priority: ${priority.name}`}
            >
              <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M3 4h10M6 4V3a1 1 0 011-1h2a1 1 0 011 1v1M13 4v9a1 1 0 01-1 1H4a1 1 0 01-1-1V4"/>
              </svg>
            </button>
          </div>
        )}
      </div>

      {/* Type badge and checkpoint */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xs text-secondary">{'\u21BB'} Flexible</span>
        {!isEditing && checkpointDays !== null && (
          <span className="text-xs text-secondary">
            {checkpointDays > 0 ? `${checkpointDays}d until check-in` : checkpointDays === 0 ? 'Check-in today' : 'Check-in overdue'}
          </span>
        )}
      </div>

      {/* Edit mode: All flexible fields */}
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
              disabled={isSaving}
              min="0.5"
              step="0.5"
              className="w-full text-sm text-default bg-surface border border-default rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-info"
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
              disabled={isSaving}
              min={minDate}
              className="w-full text-sm text-default bg-surface border border-default rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-info"
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
              disabled={isSaving}
              maxLength={200}
              rows={2}
              className="w-full text-sm text-default bg-surface border border-default rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-info resize-none"
            />
          </div>
        </div>
      ) : (
        <>
          {/* Weekly hours target - only show if weeklyHourTarget exists */}
          {priority.weeklyHourTarget != null && (
            <div className="mb-3">
              <div className="flex items-center gap-2">
                <span className="text-sm text-secondary">
                  {priority.weeklyHourTarget}h/week target
                </span>
                {/* Only show actual hours if value exists and is > 0 */}
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

      {/* Calendar keyword reminder */}
      <div className="mb-3 p-2 bg-surface-secondary rounded-lg">
        <p className="text-xs text-secondary">
          {'\uD83D\uDCC5'} Tag calendar events with <strong className="text-default">{priority.calendarKeyword}</strong> to track time
        </p>
      </div>

      {/* 1-Month Goal section (read-only display) */}
      {!isEditing && priority.desiredResult && (
        <div className="border-t border-subtle pt-3">
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

      {/* Deliverables */}
      {(priority.deliverables.length > 0 || !isEditing) && (
        <div className={`border-t border-subtle pt-3 ${!isEditing && priority.desiredResult ? 'mt-3' : ''}`}>
          <h4 className="text-xs font-medium text-tertiary uppercase tracking-wide mb-2">
            Deliverables
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
                  disabled={isEditing}
                />
              ))}
            </ul>
          ) : (
            <p className="text-xs text-tertiary mb-3">No deliverables yet</p>
          )}
          {!isEditing && (
            <AddDeliverableInput
              priorityId={priority.id}
              onAdd={onAddDeliverable}
            />
          )}
        </div>
      )}

      {/* Edit mode: error and actions */}
      {isEditing && (
        <div className="border-t border-subtle pt-3 mt-3">
          {error && (
            <p className="text-xs text-danger mb-2" role="alert">{error}</p>
          )}
          <div className="flex gap-2">
            <Button
              color="primary"
              variant="solid"
              size="sm"
              onClick={handleSave}
              disabled={isSaving}
            >
              {isSaving ? 'Saving...' : 'Save'}
            </Button>
            <Button
              color="secondary"
              variant="ghost"
              size="sm"
              onClick={handleCancelEdit}
              disabled={isSaving}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </article>
  )
}
