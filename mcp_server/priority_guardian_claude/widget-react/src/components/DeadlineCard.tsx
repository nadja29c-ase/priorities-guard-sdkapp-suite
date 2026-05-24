import { useState, useRef, useEffect, useCallback } from 'react'
import type { Priority, CalendarKeyword } from '../types'
import { daysUntil } from '../utils'
import { DeliverableItem } from './DeliverableItem'
import { AddDeliverableInput } from './AddDeliverableInput'
import { DeleteConfirmation } from './DeleteConfirmation'
import { ChevronIcon } from './ChevronIcon'
import { KeywordPicker } from './KeywordPicker'
import { Button } from './Button'
import { BADGE_COLORS, BORDER_COLORS, ICON_STROKE_COLORS } from '../constants'
import { t, getRawLocale } from '../i18n'

interface DeadlineCardProps {
  priority: Priority
  priorities?: Priority[]  // All priorities for keyword picker (only needed in fullscreen)
  isInline?: boolean  // When true, display-only (no CRUD actions)
  isEditing?: boolean
  defaultDeliverablesExpanded?: boolean
  onStartEdit?: () => void
  onCancelEdit?: () => void
  onSave?: (priorityId: string, data: { name?: string; deadline?: string }) => Promise<void>
  onDelete?: (priorityId: string) => Promise<void>
  onKeywordChange?: (priorityId: string, keyword: CalendarKeyword) => Promise<void>
  onToggleDeliverable?: (deliverableId: string, done: boolean) => Promise<void>
  onRenameDeliverable?: (deliverableId: string, name: string) => Promise<void>
  onDeleteDeliverable?: (deliverableId: string) => Promise<void>
  onAddDeliverable?: (priorityId: string, name: string) => Promise<void>
}

export function DeadlineCard({
  priority,
  priorities = [],
  isInline = false,
  isEditing = false,
  defaultDeliverablesExpanded = true,
  onStartEdit,
  onCancelEdit,
  onSave,
  onDelete,
  onKeywordChange,
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
  const [isHoveredEdit, setIsHoveredEdit] = useState(false)
  const [isHoveredDelete, setIsHoveredDelete] = useState(false)
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cardRef = useRef<HTMLElement>(null)

  const days = priority.deadline ? daysUntil(priority.deadline) : null
  const doneCount = priority.deliverables.filter(d => d.done).length
  const totalCount = priority.deliverables.length

  const kw = priority.calendarKeyword
  const badgeColor = BADGE_COLORS[kw] ?? BADGE_COLORS.P1
  const borderColor = BORDER_COLORS[kw] ?? BORDER_COLORS.P1
  const iconStrokeColor = ICON_STROKE_COLORS[kw] ?? ICON_STROKE_COLORS.P1

  // Format deadline date for banner
  const locale = getRawLocale()
  const deadlineDate = priority.deadline
    ? new Date(priority.deadline + 'T00:00:00').toLocaleDateString(locale, {
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
    if (!onSave) return

    if (field === 'name' && !value.trim()) {
      setError(t('nameRequired'))
      setEditName(priority.name)
      return
    }
    if (field === 'deadline' && !value) {
      setError(t('deadlineRequired'))
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

  const handleDeadlineBlur = () => {
    if (editDeadline !== priority.deadline) {
      autoSave('deadline', editDeadline)
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
          overflow: 'hidden',
          background: 'var(--color-background-primary, #fff)',
          border: '1px solid var(--color-border, #e5e5e5)',
          borderLeft: `3px solid ${borderColor}`,
        }}
        aria-label={priority.name}
      >
        {/* Deadline banner */}
        <div
          style={{
            padding: '10px 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'var(--color-background-secondary, #f9f9f9)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <svg
              style={{ width: '14px', height: '14px', flexShrink: 0 }}
              viewBox="0 0 16 16"
              fill="none"
              stroke={iconStrokeColor}
              strokeWidth="1.5"
              aria-hidden="true"
            >
              <rect x="2" y="3" width="12" height="11" rx="1.5" />
              <path d="M5 1.5v3M11 1.5v3M2 7h12" />
            </svg>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-text-secondary, #5c5c5c)' }}>
              {deadlineDate}
            </span>
          </div>
          <span style={{ fontSize: '12px', fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: 'var(--color-text-secondary, #5c5c5c)' }}>
            {days !== null && (
              days > 0
                ? t('dDaysLeft').replace('{n}', String(days))
                : days === 0
                  ? t('dueToday')
                  : t('dDaysOverdue').replace('{n}', String(Math.abs(days)))
            )}
          </span>
        </div>

        {/* Main content area */}
        <div style={{ padding: '20px' }}>
          {/* Header row: Badge + Name */}
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
          </div>

          {/* Lead measure */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <span style={{ fontSize: '24px', fontWeight: 700, fontVariantNumeric: 'tabular-nums', lineHeight: 1, color: 'var(--color-text-primary, #0d0d0d)' }}>
              {doneCount}
              <span style={{ fontSize: '18px', fontWeight: 400, color: 'var(--color-text-tertiary, #8c8c8c)' }}>
                /{totalCount}
              </span>
            </span>
            <span style={{ fontSize: '14px', color: 'var(--color-text-secondary, #5c5c5c)' }}>
              {t('deliverablesDone')}
            </span>
          </div>

          {/* E2E Deliverables - Collapsible */}
          <div style={{ paddingTop: '12px', borderTop: '1px solid var(--color-border-subtle, #f0f0f0)' }}>
            <button
              type="button"
              onClick={() => setDeliverablesExpanded(!deliverablesExpanded)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                width: '100%',
                marginBottom: '8px',
                background: 'none',
                border: 'none',
                padding: 0,
                cursor: 'pointer',
              }}
              aria-expanded={deliverablesExpanded}
            >
              <span style={{ fontSize: '12px', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-tertiary, #8c8c8c)' }}>
                {t('e2eDeliverables')}
              </span>
              <span style={{ fontSize: '12px', fontVariantNumeric: 'tabular-nums', color: 'var(--color-text-tertiary, #8c8c8c)' }}>
                ({doneCount}/{totalCount})
              </span>
              <span style={{ marginLeft: 'auto' }}>
                <ChevronIcon expanded={deliverablesExpanded} />
              </span>
            </button>

            {deliverablesExpanded && (
              <>
                {priority.deliverables.length > 0 ? (
                  <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '6px' }} aria-label="Deliverables list">
                    {priority.deliverables.map((d) => (
                      <DeliverableItem key={d.id} deliverable={d} isInline />
                    ))}
                  </ul>
                ) : (
                  <p style={{ fontSize: '12px', fontStyle: 'italic', color: 'var(--color-text-secondary, #5c5c5c)' }}>
                    {t('noDeliverablesHint')}
                  </p>
                )}
              </>
            )}
          </div>
        </div>
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
        overflow: 'hidden',
        background: 'var(--color-background-primary, #fff)',
        border: '1px solid var(--color-border, #e5e5e5)',
        borderLeft: `3px solid ${borderColor}`,
      }}
      aria-label={priority.name}
    >
      {/* Deadline banner */}
      <div
        data-testid="deadline-banner"
        style={{
          padding: '10px 20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--color-background-secondary, #f9f9f9)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <svg
            style={{ width: '14px', height: '14px', flexShrink: 0 }}
            viewBox="0 0 16 16"
            fill="none"
            stroke={iconStrokeColor}
            strokeWidth="1.5"
            aria-hidden="true"
          >
            <rect x="2" y="3" width="12" height="11" rx="1.5" />
            <path d="M5 1.5v3M11 1.5v3M2 7h12" />
          </svg>
          <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-text-secondary, #5c5c5c)' }}>
            {deadlineDate}
          </span>
        </div>
        <span style={{ fontSize: '12px', fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: 'var(--color-text-secondary, #5c5c5c)' }}>
          {days !== null && (
            days > 0
              ? t('dDaysLeft').replace('{n}', String(days))
              : days === 0
                ? t('dueToday')
                : t('dDaysOverdue').replace('{n}', String(Math.abs(days)))
          )}
        </span>
      </div>

      {/* Main content area */}
      <div style={{ padding: '20px' }}>
        {/* Header row: Badge + Name (read mode) or Badge + Edit/Trash (edit mode) */}
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
                background: isHoveredEdit ? 'var(--color-background-secondary, #f9f9f9)' : 'transparent',
                border: 'none',
                cursor: 'pointer',
              }}
              title={t('edit')}
              aria-label={t('editPriority').replace('{name}', priority.name)}
            >
              <svg style={{ width: '14px', height: '14px', color: 'var(--color-text-tertiary, #8c8c8c)' }} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
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
                background: isHoveredDelete ? 'rgba(220, 38, 38, 0.1)' : 'transparent',
                border: 'none',
                cursor: 'pointer',
              }}
              title={t('delete')}
              aria-label={t('deleteItem').replace('{name}', priority.name)}
            >
              <svg style={{ width: '14px', height: '14px', color: 'var(--color-text-tertiary, #8c8c8c)' }} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
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
            aria-label="Priority name"
          />
        )}

        {/* Error message */}
        {error && (
          <p style={{ fontSize: '12px', color: 'var(--color-text-danger, #dc2626)', marginBottom: '8px' }} role="alert">{error}</p>
        )}

        {/* Lead measure */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
          <span style={{ fontSize: '24px', fontWeight: 700, fontVariantNumeric: 'tabular-nums', lineHeight: 1, color: 'var(--color-text-primary, #0d0d0d)' }}>
            {doneCount}
            <span style={{ fontSize: '18px', fontWeight: 400, color: 'var(--color-text-tertiary, #8c8c8c)' }}>
              /{totalCount}
            </span>
          </span>
          <span style={{ fontSize: '14px', color: 'var(--color-text-secondary, #5c5c5c)' }}>
            {t('deliverablesDone')}
          </span>
        </div>

        {/* Edit mode: Keyword picker + Deadline field */}
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
              <label htmlFor={`deadline-${priority.id}`} style={{ display: 'block', fontSize: '12px', fontWeight: 500, color: 'var(--color-text-secondary, #737373)', marginBottom: '4px' }}>
                {t('deadlineLabel')}
              </label>
              <input
                id={`deadline-${priority.id}`}
                type="date"
                value={editDeadline}
                onChange={(e) => setEditDeadline(e.target.value)}
                onBlur={handleDeadlineBlur}
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
                }}
              />
            </div>
          </div>
        )}

        {/* E2E Deliverables - Collapsible */}
        <div style={{ paddingTop: '12px', borderTop: '1px solid var(--color-border-subtle, #f0f0f0)' }}>
          <button
            type="button"
            onClick={() => setDeliverablesExpanded(!deliverablesExpanded)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              width: '100%',
              marginBottom: '8px',
              background: 'none',
              border: 'none',
              padding: 0,
              cursor: 'pointer',
            }}
            aria-expanded={deliverablesExpanded}
          >
            <span style={{ fontSize: '12px', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-tertiary, #8c8c8c)' }}>
              {t('e2eDeliverables')}
            </span>
            <span style={{ fontSize: '12px', fontVariantNumeric: 'tabular-nums', color: 'var(--color-text-tertiary, #8c8c8c)' }}>
              ({doneCount}/{totalCount})
            </span>
            <span style={{ marginLeft: 'auto' }}>
              <ChevronIcon expanded={deliverablesExpanded} />
            </span>
          </button>

          {deliverablesExpanded && (
            <>
              {priority.deliverables.length > 0 ? (
                <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '8px' }} aria-label="Deliverables list">
                  {priority.deliverables.map((d) => (
                    <DeliverableItem
                      key={d.id}
                      deliverable={d}
                      onToggle={onToggleDeliverable}
                      onRename={onRenameDeliverable}
                      onDelete={onDeleteDeliverable}
                      disabled={isSaving}
                    />
                  ))}
                </ul>
              ) : (
                <p style={{ fontSize: '12px', fontStyle: 'italic', color: 'var(--color-text-secondary, #5c5c5c)', marginBottom: '8px' }}>
                  {t('noDeliverablesHint')}
                </p>
              )}
              {onAddDeliverable && (
                <AddDeliverableInput
                  priorityId={priority.id}
                  onAdd={onAddDeliverable}
                />
              )}
            </>
          )}
        </div>

        {/* Edit mode actions */}
        {isEditing && onCancelEdit && (
          <div style={{ marginTop: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <p style={{ fontSize: '12px', color: 'var(--color-text-tertiary, #8c8c8c)' }}>
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
      </div>
    </article>
  )
}
