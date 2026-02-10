import { useState } from 'react'
import { Button } from '@openai/apps-sdk-ui/components/Button'
import type { Priority } from '../types'
import { daysUntil, formatDate } from '../utils'
import { DeliverableItem } from './DeliverableItem'
import { AddDeliverableInput } from './AddDeliverableInput'
import { DeleteConfirmation } from './DeleteConfirmation'
import { BADGE_COLORS } from '../constants'

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

  const days = priority.deadline ? daysUntil(priority.deadline) : null
  const doneCount = priority.deliverables.filter(d => d.done).length
  const totalCount = priority.deliverables.length

  const badgeColorClass = BADGE_COLORS[priority.calendarKeyword] ?? BADGE_COLORS.P1

  // Get tomorrow's date for min date constraint
  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  const minDate = tomorrow.toISOString().split('T')[0]

  const handleSave = async () => {
    if (isSaving) return
    setError(null)

    const updates: { name?: string; deadline?: string } = {}
    if (editName.trim() !== priority.name) {
      if (!editName.trim()) {
        setError('Name is required')
        return
      }
      updates.name = editName.trim()
    }
    if (editDeadline !== priority.deadline) {
      if (!editDeadline) {
        setError('Deadline is required')
        return
      }
      updates.deadline = editDeadline
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
    setEditDeadline(priority.deadline || '')
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

      {/* Type badge and progress */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <span className="text-xs text-secondary">{'\u23F1'} Deadline</span>
        {totalCount > 0 && (
          <span className="text-xs text-secondary">
            {doneCount} of {totalCount} done
            {days !== null && ` \u00B7 ${days > 0 ? `${days}d left` : days === 0 ? 'Due today' : `${Math.abs(days)}d overdue`}`}
          </span>
        )}
        {totalCount === 0 && days !== null && (
          <span className="text-xs text-secondary">
            {days > 0 ? `${days}d left` : days === 0 ? 'Due today' : `${Math.abs(days)}d overdue`}
          </span>
        )}
      </div>

      {/* Edit mode: deadline field */}
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
            disabled={isSaving}
            min={minDate}
            className="w-full text-sm text-default bg-surface border border-default rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-info"
          />
        </div>
      )}

      {/* Calendar keyword reminder */}
      <div className="mb-3 p-2 bg-surface-secondary rounded-lg">
        <p className="text-xs text-secondary">
          {'\uD83D\uDCC5'} Tag calendar events with <strong className="text-default">{priority.calendarKeyword}</strong> to track time
        </p>
      </div>

      {/* Deliverables */}
      {(priority.deliverables.length > 0 || !isEditing) && (
        <div className="border-t border-subtle pt-3">
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

      {/* Deadline date (read-only display) */}
      {!isEditing && priority.deadline && (
        <div className="mt-3 text-xs text-tertiary">
          Due: {formatDate(priority.deadline)}
        </div>
      )}
    </article>
  )
}
