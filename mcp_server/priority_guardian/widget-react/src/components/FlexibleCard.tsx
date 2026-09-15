import { useState, useRef, useEffect, useCallback } from 'react'
import type { Priority, CalendarKeyword } from '../types'
import { DeleteConfirmation } from './DeleteConfirmation'
import { GoalSection } from './GoalSection'
import { KeywordPicker } from './KeywordPicker'
import { Button } from '@openai/apps-sdk-ui/components/Button'
import { BADGE_COLORS, BADGE_CIRCLE_CLASS, BORDER_COLORS } from '../constants'
import { HourRing } from './HourRing'
import { t } from '../i18n'

interface FlexibleCardProps {
  priority: Priority
  priorities: Priority[]  // All priorities for keyword picker
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
  onKeywordChange: (priorityId: string, keyword: CalendarKeyword) => Promise<void>
  // Goal handlers (Inc D)
  onAddGoal: (text: string) => Promise<void>
  onToggleGoal: (goalId: string, achieved: boolean) => Promise<void>
  onRenameGoal: (goalId: string, text: string) => Promise<void>
  onDeleteGoal: (goalId: string) => Promise<void>
}

export function FlexibleCard({
  priority,
  priorities,
  isEditing,
  defaultGoalsExpanded = true,
  onStartEdit,
  onCancelEdit,
  onSave,
  onDelete,
  onKeywordChange,
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
  const borderColorClass = BORDER_COLORS[kw] ?? BORDER_COLORS.P1

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
      setError(t('nameRequired'))
      setEditName(priority.name)
      return
    }
    if (field === 'weekly_hour_target') {
      const numVal = parseFloat(value)
      if (!value || isNaN(numVal) || numVal <= 0) {
        setError(t('weeklyHoursPositive'))
        setEditHourTarget(priority.weeklyHourTarget?.toString() || '')
        return
      }
    }

    // Check if value actually changed
    // Use numeric comparison for weekly_hour_target to handle "7.50" vs "7.5"
    if (field === 'name' && value === priority.name) {
      return
    } else if (field === 'weekly_hour_target') {
      const newNum = parseFloat(value)
      const oldNum = priority.weeklyHourTarget ?? 0
      if (newNum === oldNum) {
        return
      }
    } else if (field === 'checkpoint_date' && value === (priority.checkpointDate || '')) {
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

      if (errorTimeoutRef.current) clearTimeout(errorTimeoutRef.current)
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
    // Use numeric comparison to handle "7.50" vs "7.5"
    const newNum = parseFloat(editHourTarget)
    const oldNum = priority.weeklyHourTarget ?? 0
    if (!isNaN(newNum) && newNum !== oldNum) {
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
      const errorMsg = e instanceof Error ? e.message : t('couldntSave')
      setError(errorMsg)
      setShowDeleteConfirm(false)
      if (errorTimeoutRef.current) clearTimeout(errorTimeoutRef.current)
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
      className={`rounded-xl p-4 bg-surface border border-default ${borderColorClass}`}
      aria-label={priority.name}
    >
      {/* V7 Header: Badge + Name + Streak pill (read mode) or Badge + Edit/Trash (edit mode) */}
      <div className="flex items-center gap-2 mb-2">
        <span className={`${BADGE_CIRCLE_CLASS} ${badgeColorClass} text-2xs`}>
          {kw}
        </span>
        {!isEditing && (
          <h3
            className="text-sm font-semibold flex-1 truncate cursor-pointer hover:opacity-80 text-default focus:outline-none focus-visible:ring-1 focus-visible:ring-[var(--color-border-focus,currentColor)] rounded"
            onClick={(e) => { e.stopPropagation(); onStartEdit(); }}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); onStartEdit(); } }}
            tabIndex={0}
            role="button"
            aria-label={`${priority.name} — ${t('clickToEdit')}`}
            title={t('clickToEdit')}
          >
            {priority.name}
          </h3>
        )}
        {/* V7: Streak as pill (not emoji) */}
        {!isEditing && priority.streakCount != null && priority.streakCount > 0 && (
          <span className="text-xs tabular-nums px-1.5 py-0.5 rounded-full font-medium text-default bg-surface-tertiary">
            {t('weekStreak').replace('{n}', String(priority.streakCount))}
          </span>
        )}
        {isEditing && <div className="flex-1" />}
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onStartEdit(); }}
          className="p-1 rounded hover:bg-surface-secondary transition-colors"
          title={t('edit')}
          aria-label={t('editPriority').replace('{name}', priority.name)}
        >
          <svg className="w-3.5 h-3.5 text-tertiary" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="M11.5 2.5l2 2M2 14l.5-2 9-9 2 2-9 9-2.5.5z" />
          </svg>
        </button>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); setShowDeleteConfirm(true); }}
          className="p-1 rounded hover:bg-danger-soft-alpha transition-colors"
          title={t('delete')}
          aria-label={t('deleteItem').replace('{name}', priority.name)}
        >
          <svg className="w-3.5 h-3.5 text-tertiary" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="M2 4h12M5.5 4V2.5a1 1 0 011-1h3a1 1 0 011 1V4" />
            <path d="M12.5 4v9a1.5 1.5 0 01-1.5 1.5H5a1.5 1.5 0 01-1.5-1.5V4" />
            <path d="M6.5 7v5M9.5 7v5" />
          </svg>
        </button>
      </div>

      {/* Edit mode: Full-width name input (separate row to avoid mobile squeeze) */}
      {isEditing && (
        <input
          type="text"
          value={editName}
          onChange={(e) => setEditName(e.target.value)}
          onBlur={handleNameBlur}
          disabled={isSaving}
          maxLength={100}
          autoFocus
          className="w-full text-sm font-semibold text-default bg-surface border border-default rounded-lg px-2 py-1 mb-3 focus:outline-none focus:border-tertiary"
          aria-label="Priority name"
        />
      )}

      {/* Error message */}
      {error && (
        <p className="text-xs text-danger mb-2" role="alert">{error}</p>
      )}

      {/* V7: HourRing on left + Avg stats on right (not in edit mode) */}
      {!isEditing && priority.weeklyHourTarget != null && (
        <div className="flex items-center gap-4 mb-3">
          <HourRing
            actual={priority.weeklyHourActual ?? 0}
            target={priority.weeklyHourTarget}
            keyword={kw}
          />
          <div className="flex-1">
            {hasAvg ? (
              <>
                <span className="text-2xl font-bold tabular-nums leading-none text-default">
                  ~{Math.round(priority.avgTargetAchievement!)}%
                </span>
                <p className="text-xs mt-0.5 text-secondary">
                  {t('ofWeeklyTargetOnAvg')}
                </p>
              </>
            ) : (
              <div className="flex items-center gap-1.5">
                <svg
                  className="w-3.5 h-3.5 flex-shrink-0 text-tertiary"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M4 2h8M4 14h8M5 2v2c0 1.5 1 3 3 4-2 1-3 2.5-3 4v2M11 2v2c0 1.5-1 3-3 4 2 1 3 2.5 3 4v2" />
                </svg>
                <span className="text-sm italic text-tertiary">
                  {t('trackingInProgress')}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Edit mode: Keyword picker + Flexible priority fields with auto-save on blur */}
      {isEditing && (
        <div className="space-y-3 mb-3">
          {/* Keyword reassignment */}
          <KeywordPicker
            currentKeyword={kw as CalendarKeyword}
            priorities={priorities}
            onKeywordChange={(newKw) => onKeywordChange(priority.id, newKw)}
            disabled={isSaving}
          />

          <div>
            <label htmlFor={`hours-${priority.id}`} className="block text-xs font-medium text-secondary mb-1">
              {t('weeklyHourTarget')}
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
              {t('checkpointDate')}
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
            {t('changesAutoSave')}
          </p>
          <Button
            color="secondary"
            variant="outline"
            size="sm"
            onClick={onCancelEdit}
            disabled={isSaving}
          >
            {t('done')}
          </Button>
        </div>
      )}
    </article>
  )
}
