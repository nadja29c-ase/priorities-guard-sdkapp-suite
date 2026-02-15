import { useState, useRef, useEffect, useCallback } from 'react'
import type { Priority } from '../types'
import { daysUntil } from '../utils'
import { DeleteConfirmation } from './DeleteConfirmation'
import { GoalSection } from './GoalSection'
import { Button } from '@openai/apps-sdk-ui/components/Button'
import { BADGE_COLORS, BADGE_CIRCLE_CLASS } from '../constants'
import { HourRing } from './HourRing'

// V7 border colors for card left border
const BORDER_COLORS: Record<string, string> = {
  P1: '#0285ff',
  P2: '#924ff7',
  P3: '#ffc300',
}

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

  const kw = priority.calendarKeyword
  const badgeColorClass = BADGE_COLORS[kw] ?? BADGE_COLORS.P1
  const borderColor = BORDER_COLORS[kw] ?? BORDER_COLORS.P1

  const hasAvg = priority.avgTargetAchievement != null

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
    } catch (e) {
      console.error('callTool error:', e)
      const errorMsg = e instanceof Error ? e.message : 'Failed to save'
      setError(errorMsg)
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
      className="rounded-xl p-5"
      style={{
        background: 'var(--gray-0, #ffffff)',
        border: '1px solid var(--gray-100, #ededed)',
        borderLeft: `4px solid ${borderColor}`,
      }}
      aria-label={`Priority ${kw}: ${priority.name}`}
    >
      {/* V7 Header: Badge + Name + Streak pill + Edit/Trash */}
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
        {/* V7: Streak as pill (not emoji) */}
        {!isEditing && priority.streakCount != null && priority.streakCount > 0 && (
          <span
            className="text-xs tabular-nums px-1.5 py-0.5 rounded-full font-medium"
            style={{
              color: 'var(--gray-600, #414141)',
              background: 'var(--gray-75, #f3f3f3)',
              fontSize: '0.7rem',
            }}
          >
            {priority.streakCount}w streak
          </span>
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

      {/* V7: HourRing on left + Avg stats on right (not in edit mode) */}
      {!isEditing && priority.weeklyHourTarget != null && (
        <div className="flex items-start gap-4 mb-4">
          <HourRing
            actual={priority.weeklyHourActual ?? 0}
            target={priority.weeklyHourTarget}
            keyword={kw}
          />
          <div className="flex-1 pt-1">
            {hasAvg ? (
              <div className="mb-1.5">
                <span
                  className="text-2xl font-bold tabular-nums leading-none"
                  style={{ color: 'var(--gray-900, #181818)' }}
                >
                  ~{Math.round(priority.avgTargetAchievement!)}%
                </span>
                <p
                  className="text-xs mt-0.5"
                  style={{ color: 'var(--gray-450, #767676)' }}
                >
                  of weekly target on avg
                </p>
              </div>
            ) : (
              <div className="mb-1.5">
                <span
                  className="text-sm"
                  style={{ color: 'var(--gray-350, #9f9f9f)' }}
                >
                  Building your average…
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Edit mode: Flexible priority fields with auto-save on blur */}
      {isEditing && (
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
      )}

      {/* Goals section (Inc D) */}
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
