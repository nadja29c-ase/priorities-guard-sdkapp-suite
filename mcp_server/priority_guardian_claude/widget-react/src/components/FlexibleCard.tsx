import { useState, useRef, useEffect, useCallback } from 'react'
import type { Priority, CalendarKeyword } from '../types'
import { DeleteConfirmation } from './DeleteConfirmation'
import { GoalSection } from './GoalSection'
import { KeywordPicker } from './KeywordPicker'
import { Button } from './Button'
import { BADGE_COLORS, BORDER_COLORS } from '../constants'
import { HourRing } from './HourRing'
import { t } from '../i18n'

interface FlexibleCardProps {
  priority: Priority
  priorities?: Priority[]  // All priorities for keyword picker (only needed in fullscreen)
  isInline?: boolean  // When true, display-only (no CRUD actions)
  isEditing?: boolean
  defaultGoalsExpanded?: boolean
  onStartEdit?: () => void
  onCancelEdit?: () => void
  onSave?: (priorityId: string, data: {
    name?: string
    weekly_hour_target?: number
    checkpoint_date?: string
  }) => Promise<void>
  onDelete?: (priorityId: string) => Promise<void>
  onKeywordChange?: (priorityId: string, keyword: CalendarKeyword) => Promise<void>
  // Goal handlers
  onAddGoal?: (text: string) => Promise<void>
  onToggleGoal?: (goalId: string, achieved: boolean) => Promise<void>
  onRenameGoal?: (goalId: string, text: string) => Promise<void>
  onDeleteGoal?: (goalId: string) => Promise<void>
}

export function FlexibleCard({
  priority,
  priorities = [],
  isInline = false,
  isEditing = false,
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
  const [isHoveredEdit, setIsHoveredEdit] = useState(false)
  const [isHoveredDelete, setIsHoveredDelete] = useState(false)
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cardRef = useRef<HTMLElement>(null)

  const kw = priority.calendarKeyword
  const badgeColor = BADGE_COLORS[kw] ?? BADGE_COLORS.P1
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
    if (!onSave) return

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
      const errorMsg = e instanceof Error ? e.message : t('couldntSave')
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
    if (!onDelete) return
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
    if (isEditing && !isSaving && onCancelEdit && cardRef.current && !cardRef.current.contains(e.target as Node)) {
      onCancelEdit()
    }
  }, [isEditing, isSaving, onCancelEdit])

  useEffect(() => {
    if (isEditing) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isEditing, handleClickOutside])

  // Inline mode - display only (using inline styles for Claude widget)
  if (isInline) {
    return (
      <article
        style={{
          borderRadius: '12px',
          padding: '8px',
          background: 'var(--color-background-primary, #fff)',
          border: '1px solid var(--color-border, #e5e5e5)',
          borderLeft: `3px solid ${borderColor}`,
        }}
        aria-label={priority.name}
      >
        {/* Header: Badge + Name + Streak pill */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '24px',
              height: '24px',
              borderRadius: '50%',
              fontSize: '10px',
              fontWeight: 700,
              background: badgeColor.bg,
              color: badgeColor.text,
            }}
          >
            {kw}
          </span>
          <h3
            style={{
              flex: 1,
              fontSize: '14px',
              fontWeight: 600,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              color: 'var(--color-text-primary, #0d0d0d)',
              margin: 0,
            }}
          >
            {priority.name}
          </h3>
          {/* Streak as pill */}
          {priority.streakCount != null && priority.streakCount > 0 && (
            <span
              style={{
                fontSize: '12px',
                fontVariantNumeric: 'tabular-nums',
                padding: '2px 6px',
                borderRadius: '9999px',
                fontWeight: 500,
                color: 'var(--color-text-primary, #0d0d0d)',
                background: 'var(--color-background-tertiary, #ebebeb)',
              }}
            >
              {t('weekStreak').replace('{n}', String(priority.streakCount))}
            </span>
          )}
        </div>

        {/* HourRing on left + Avg stats on right */}
        {priority.weeklyHourTarget != null && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '6px' }}>
            <HourRing
              actual={priority.weeklyHourActual ?? 0}
              target={priority.weeklyHourTarget}
              keyword={kw}
            />
            <div style={{ flex: 1 }}>
              {hasAvg ? (
                <>
                  <span style={{ fontSize: '24px', fontWeight: 700, fontVariantNumeric: 'tabular-nums', lineHeight: 1, color: 'var(--color-text-primary, #0d0d0d)' }}>
                    ~{Math.round(priority.avgTargetAchievement!)}%
                  </span>
                  <p style={{ fontSize: '12px', marginTop: '2px', color: 'var(--color-text-secondary, #3D3D3A)' }}>
                    {t('ofWeeklyTargetOnAvg')}
                  </p>
                </>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <svg
                    style={{ width: '14px', height: '14px', flexShrink: 0, color: 'var(--color-text-tertiary, #73726C)' }}
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
                  <span style={{ fontSize: '14px', fontStyle: 'italic', color: 'var(--color-text-tertiary, #73726C)' }}>
                    {t('trackingInProgress')}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Goals section */}
        <GoalSection
          goals={priority.goals ?? []}
          checkpointDate={priority.checkpointDate}
          defaultExpanded={defaultGoalsExpanded}
          isInline
        />
      </article>
    )
  }

  // Fullscreen mode - delete confirmation
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

  // Fullscreen mode - interactive with CRUD
  return (
    <article
      ref={cardRef}
      style={{
        borderRadius: '12px',
        padding: '12px',
        background: 'var(--color-background-primary, #fff)',
        border: '1px solid var(--color-border, #e5e5e5)',
        borderLeft: `3px solid ${borderColor}`,
      }}
      aria-label={priority.name}
    >
      {/* Header: Badge + Name + Streak pill (read mode) or Badge + Edit/Trash (edit mode) */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '24px',
            height: '24px',
            borderRadius: '50%',
            fontSize: '10px',
            fontWeight: 700,
            flexShrink: 0,
            background: badgeColor.bg,
            color: badgeColor.text,
          }}
        >
          {kw}
        </span>
        {!isEditing && (
          <h3
            style={{
              flex: 1,
              fontSize: '14px',
              fontWeight: 600,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              cursor: 'pointer',
              color: 'var(--color-text-primary, #0d0d0d)',
              margin: 0,
            }}
            onClick={(e) => { e.stopPropagation(); onStartEdit?.(); }}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); onStartEdit?.(); } }}
            tabIndex={0}
            role="button"
            aria-label={`${priority.name} — ${t('clickToEdit')}`}
            title={t('clickToEdit')}
          >
            {priority.name}
          </h3>
        )}
        {/* Streak as pill */}
        {!isEditing && priority.streakCount != null && priority.streakCount > 0 && (
          <span
            style={{
              fontSize: '12px',
              fontVariantNumeric: 'tabular-nums',
              padding: '2px 6px',
              borderRadius: '9999px',
              fontWeight: 500,
              color: 'var(--color-text-primary, #0d0d0d)',
              background: 'var(--color-background-tertiary, #ebebeb)',
            }}
          >
            {t('weekStreak').replace('{n}', String(priority.streakCount))}
          </span>
        )}
        {isEditing && <div style={{ flex: 1 }} />}
        {onStartEdit && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onStartEdit(); }}
            onMouseEnter={() => setIsHoveredEdit(true)}
            onMouseLeave={() => setIsHoveredEdit(false)}
            style={{
              padding: '4px',
              borderRadius: '4px',
              transition: 'background 0.15s',
              background: isHoveredEdit ? 'var(--color-background-secondary, #F5F4ED)' : 'transparent',
              border: 'none',
              cursor: 'pointer',
            }}
            title={t('edit')}
            aria-label={t('editPriority').replace('{name}', priority.name)}
          >
            <svg style={{ width: '14px', height: '14px', color: 'var(--color-text-tertiary, #73726C)' }} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <path d="M11.5 2.5l2 2M2 14l.5-2 9-9 2 2-9 9-2.5.5z" />
            </svg>
          </button>
        )}
        {onDelete && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setShowDeleteConfirm(true); }}
            onMouseEnter={() => setIsHoveredDelete(true)}
            onMouseLeave={() => setIsHoveredDelete(false)}
            style={{
              padding: '4px',
              borderRadius: '4px',
              transition: 'background 0.15s',
              background: isHoveredDelete ? 'rgba(220, 38, 38, 0.1)' : 'transparent',
              border: 'none',
              cursor: 'pointer',
            }}
            title={t('delete')}
            aria-label={t('deleteItem').replace('{name}', priority.name)}
          >
            <svg style={{ width: '14px', height: '14px', color: 'var(--color-text-tertiary, #73726C)' }} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <path d="M2 4h12M5.5 4V2.5a1 1 0 011-1h3a1 1 0 011 1V4" />
              <path d="M12.5 4v9a1.5 1.5 0 01-1.5 1.5H5a1.5 1.5 0 01-1.5-1.5V4" />
              <path d="M6.5 7v5M9.5 7v5" />
            </svg>
          </button>
        )}
      </div>

      {/* Edit mode: Full-width name input */}
      {isEditing && (
        <input
          type="text"
          value={editName}
          onChange={(e) => setEditName(e.target.value)}
          onBlur={handleNameBlur}
          disabled={isSaving}
          maxLength={100}
          autoFocus
          style={{
            width: '100%',
            fontSize: '14px',
            fontWeight: 600,
            color: 'var(--color-text-primary, #0d0d0d)',
            background: 'var(--color-background-primary, #fff)',
            border: '1px solid var(--color-border, #e5e5e5)',
            borderRadius: '8px',
            padding: '8px 12px',
            marginBottom: '12px',
            outline: 'none',
          }}
          aria-label={t('priorityNameLabel')}
        />
      )}

      {/* Error message */}
      {error && (
        <p style={{ fontSize: '12px', color: 'var(--color-text-danger, #dc2626)', marginBottom: '8px' }} role="alert">{error}</p>
      )}

      {/* HourRing on left + Avg stats on right (not in edit mode) */}
      {!isEditing && priority.weeklyHourTarget != null && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '16px' }}>
          <HourRing
            actual={priority.weeklyHourActual ?? 0}
            target={priority.weeklyHourTarget}
            keyword={kw}
          />
          <div style={{ flex: 1 }}>
            {hasAvg ? (
              <>
                <span style={{ fontSize: '24px', fontWeight: 700, fontVariantNumeric: 'tabular-nums', lineHeight: 1, color: 'var(--color-text-primary, #0d0d0d)' }}>
                  ~{Math.round(priority.avgTargetAchievement!)}%
                </span>
                <p style={{ fontSize: '12px', marginTop: '2px', color: 'var(--color-text-secondary, #3D3D3A)' }}>
                  {t('ofWeeklyTargetOnAvg')}
                </p>
              </>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <svg
                  style={{ width: '14px', height: '14px', flexShrink: 0, color: 'var(--color-text-tertiary, #73726C)' }}
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
                <span style={{ fontSize: '14px', fontStyle: 'italic', color: 'var(--color-text-tertiary, #73726C)' }}>
                  {t('trackingInProgress')}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Edit mode: Keyword picker + Flexible priority fields */}
      {isEditing && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '12px' }}>
          {onKeywordChange && (
            <KeywordPicker
              currentKeyword={kw as CalendarKeyword}
              priorities={priorities}
              onKeywordChange={(newKw) => onKeywordChange(priority.id, newKw)}
              disabled={isSaving}
            />
          )}

          <div>
            <label htmlFor={`hours-${priority.id}`} style={{ display: 'block', fontSize: '12px', fontWeight: 500, color: 'var(--color-text-secondary, #737373)', marginBottom: '4px' }}>
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
              style={{
                width: '100%',
                fontSize: '14px',
                color: 'var(--color-text-primary, #0d0d0d)',
                background: 'var(--color-background-primary, #fff)',
                border: '1px solid var(--color-border, #e5e5e5)',
                borderRadius: '12px',
                padding: '8px 12px',
                outline: 'none',
              }}
            />
          </div>

          <div>
            <label htmlFor={`checkpoint-${priority.id}`} style={{ display: 'block', fontSize: '12px', fontWeight: 500, color: 'var(--color-text-secondary, #737373)', marginBottom: '4px' }}>
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
              style={{
                width: '100%',
                fontSize: '14px',
                color: 'var(--color-text-primary, #0d0d0d)',
                background: 'var(--color-background-primary, #fff)',
                border: '1px solid var(--color-border, #e5e5e5)',
                borderRadius: '12px',
                padding: '8px 12px',
                outline: 'none',
                boxSizing: 'border-box',
                WebkitAppearance: 'none',
              }}
            />
          </div>
        </div>
      )}

      {/* Goals section */}
      <GoalSection
        goals={priority.goals ?? []}
        checkpointDate={priority.checkpointDate}
        defaultExpanded={defaultGoalsExpanded || isEditing}
        onToggleGoal={onToggleGoal}
        onRenameGoal={onRenameGoal}
        onDeleteGoal={onDeleteGoal}
        onAddGoal={onAddGoal}
        disabled={isSaving}
      />

      {/* Edit mode actions */}
      {isEditing && onCancelEdit && (
        <div style={{ marginTop: '8px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <p style={{ fontSize: '12px', color: 'var(--color-text-tertiary, #73726C)' }}>
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
