import { useState, useRef, useEffect, useCallback } from 'react'
import type { Priority } from '../types'
import { daysUntil } from '../utils'
import { DeleteConfirmation } from './DeleteConfirmation'
import { GoalSection } from './GoalSection'
import { Badge } from '@openai/apps-sdk-ui/components/Badge'
import { Button } from '@openai/apps-sdk-ui/components/Button'
import { BADGE_COLORS, BADGE_CIRCLE_CLASS, BORDER_COLORS } from '../constants'
import { HourRing } from './HourRing'

interface FlexibleCardProps {
  priority: Priority
  isEditing: boolean
  defaultGoalsExpanded?: boolean
  onStartEdit: () => void
  onCancelEdit: () => void
  onSave: (priorityId: string, data: {
    name?: string
    weekly_hour_target?: number
    checkpoint_date?: string
  }) => Promise<void>
  onDelete: (priorityId: string) => Promise<void>
  // Goal handlers (Inc D)
  onAddGoal: (text: string) => Promise<void>
  onToggleGoal: (goalId: string, achieved: boolean) => Promise<void>
  onRenameGoal: (goalId: string, text: string) => Promise<void>
  onDeleteGoal: (goalId: string) => Promise<void>
}

export function FlexibleCard({
  priority,
  isEditing,
  defaultGoalsExpanded = true,
  onStartEdit,
  onCancelEdit,
  onSave,
  onDelete,
  onAddGoal,
  onToggleGoal,
  onRenameGoal,
  onDeleteGoal,
}: FlexibleCardProps) {
  const [editName, setEditName] = useState(priority.name)
  const [editHourTarget, setEditHourTarget] = useState(priority.weeklyHourTarget?.toString() || '')
  const [editCheckpointDate, setEditCheckpointDate] = useState(priority.checkpointDate || '')
  const [isSaving, setIsSaving] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cardRef = useRef<HTMLElement>(null)

  const checkpointDays = priority.checkpointDate ? daysUntil(priority.checkpointDate) : null
  const badgeColorClass = BADGE_COLORS[priority.calendarKeyword] ?? BADGE_COLORS.P1
  const borderColorClass = BORDER_COLORS[priority.calendarKeyword] ?? BORDER_COLORS.P1

  // Get tomorrow's date for min date constraint
  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  const minDate = tomorrow.toISOString().split('T')[0]

  // Reset local state when priority changes from parent
  useEffect(() => {
    setEditName(priority.name)
    setEditHourTarget(priority.weeklyHourTarget?.toString() || '')
    setEditCheckpointDate(priority.checkpointDate || '')
  }, [priority.name, priority.weeklyHourTarget, priority.checkpointDate])

  // Clear timeout on unmount
  useEffect(() => {
    return () => {
      if (errorTimeoutRef.current) {
        clearTimeout(errorTimeoutRef.current)
      }
    }
  }, [])

  const autoSave = async (
    field: 'name' | 'weekly_hour_target' | 'checkpoint_date',
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

  const handleDelete = async () => {
    setIsDeleting(true)
    try {
      await onDelete(priority.id)
    } catch (e) {
      console.error('Delete error:', e)
      const errorMsg = e instanceof Error ? e.message : "Couldn't save. Try again."
      setError(errorMsg)
      setShowDeleteConfirm(false)
      // Clear error after 3s
      errorTimeoutRef.current = setTimeout(() => {
        setError(null)
      }, 3000)
    } finally {
      setIsDeleting(false)
    }
  }

  // Click outside to exit edit mode (reliable document-level listener)
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
      className={`bg-surface rounded-xl border border-default p-6 ${borderColorClass}`}
      aria-label={`Priority ${priority.calendarKeyword}: ${priority.name}`}
    >
      {/* Header: Title row + actions (2-column layout) */}
      <div className="flex items-start gap-3 mb-2">
        <div className="flex-1 min-w-0">
          {isEditing ? (
            <div className="flex items-center gap-2">
              <span className={`${BADGE_CIRCLE_CLASS} ${badgeColorClass}`}>
                {priority.calendarKeyword}
              </span>
              <input
                type="text"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                onBlur={handleNameBlur}
                disabled={isSaving}
                maxLength={100}
                autoFocus
                className="flex-1 text-base text-default bg-surface border border-default rounded-xl px-3 py-2 focus:outline-none focus:border-tertiary"
                aria-label="Priority name"
              />
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className={`${BADGE_CIRCLE_CLASS} ${badgeColorClass}`}>
                {priority.calendarKeyword}
              </span>
              <h3
                className="text-base font-semibold text-default truncate cursor-pointer hover:text-info"
                onClick={(e) => { e.stopPropagation(); onStartEdit(); }}
                title="Click to edit"
              >
                {priority.name}
              </h3>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onStartEdit(); }}
                className="p-1 text-tertiary hover:text-info rounded flex-shrink-0"
                aria-label={`Edit priority: ${priority.name}`}
              >
                <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M11.5 2.5l2 2M2 14l.5-2 9-9 2 2-9 9-2.5.5z"/>
                </svg>
              </button>
            </div>
          )}

          {/* Type tag, streak, and calendar info below name */}
          <div className="flex items-center gap-2 mt-1">
            <Badge color="secondary" variant="soft" size="sm">Flexible</Badge>
            {!isEditing && priority.streakCount != null && priority.streakCount > 0 && (
              <span
                className="text-xs text-warning flex items-center gap-0.5"
                title={`${priority.streakCount} consecutive week${priority.streakCount === 1 ? '' : 's'} investing time`}
              >
                🔥 {priority.streakCount}
              </span>
            )}
            {!isEditing && checkpointDays !== null && (
              <span className="text-xs text-secondary">
                {checkpointDays > 0 ? `${checkpointDays}d until check-in` : checkpointDays === 0 ? 'Check-in today' : 'Check-in overdue'}
              </span>
            )}
          </div>
          <div className="mt-2 p-2 bg-surface-secondary rounded-lg w-fit">
            <p className="text-xs text-secondary">
              📅 Use <strong className="text-default">{priority.calendarKeyword}</strong> in the calendar event title to track time
            </p>
          </div>

          {/* Aggregate stats - non-edit mode only */}
          {!isEditing && (
            <div className="mt-2 space-y-0.5">
              {/* Cumulative percentage or building average message */}
              {priority.weeklyHourTarget != null && priority.weeklyHourTarget > 0 && (
                priority.avgTargetAchievement != null ? (
                  <p className="text-xs text-secondary">
                    ~{Math.round(priority.avgTargetAchievement)}% of weekly target on avg
                  </p>
                ) : (
                  <p className="text-xs text-tertiary">Building your average…</p>
                )
              )}
              {/* Total hours invested */}
              {priority.totalHoursInvested != null && priority.totalHoursInvested > 0 && (
                <p className="text-xs text-secondary">
                  {priority.totalHoursInvested.toFixed(1)}h invested total
                </p>
              )}
            </div>
          )}
        </div>

        {/* Right column: HourRing (if target set and not editing) + delete button */}
        <div className="flex-shrink-0 flex flex-col items-center gap-2">
          {/* HourRing - only in non-edit mode when target is set */}
          {!isEditing && priority.weeklyHourTarget != null && (
            <div
              className="cursor-pointer"
              onClick={(e) => { e.stopPropagation(); onStartEdit(); }}
              title="Click to edit"
            >
              <HourRing
                actual={priority.weeklyHourActual ?? 0}
                target={priority.weeklyHourTarget}
                keyword={priority.calendarKeyword}
              />
            </div>
          )}
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setShowDeleteConfirm(true); }}
            className="p-1 text-tertiary hover:text-danger rounded"
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

      {/* Edit mode: Flexible priority fields with auto-save on blur */}
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
              className="w-full text-sm text-default bg-surface border border-default rounded-xl px-3 py-2 focus:outline-none focus:border-tertiary"
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
              className="w-full text-sm text-default bg-surface border border-default rounded-xl px-3 py-2 focus:outline-none focus:border-tertiary"
            />
          </div>
        </div>
      ) : null}

      {/* Goals section (Inc D) - always visible, not just in edit mode */}
      <GoalSection
        goals={priority.goals ?? []}
        checkpointDate={priority.checkpointDate}
        defaultExpanded={defaultGoalsExpanded || isEditing}
        onToggleGoal={onToggleGoal}
        onRenameGoal={onRenameGoal}
        onDeleteGoal={onDeleteGoal}
        onAddGoal={onAddGoal}
      />

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
    </article>
  )
}
