import { useState, useRef, useEffect } from 'react'
import type { Deliverable } from '../types'
import { t } from '../i18n'

interface DeliverableItemProps {
  deliverable: Deliverable
  isInline?: boolean  // When true, display-only (no CRUD actions)
  isLast?: boolean    // When true, no bottom border (last item in list)
  onToggle?: (deliverableId: string, done: boolean) => Promise<void>
  onRename?: (deliverableId: string, name: string) => Promise<void>
  onDelete?: (deliverableId: string) => Promise<void>
  disabled?: boolean
}

// Touch device detection — icons always visible on mobile (no hover)
const isTouchDevice = typeof window !== 'undefined' && window.matchMedia('(hover: none)').matches

export function DeliverableItem({
  deliverable,
  isInline = false,
  isLast = false,
  onToggle,
  onRename,
  onDelete,
  disabled = false,
}: DeliverableItemProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [editName, setEditName] = useState(deliverable.name)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isHoveredEdit, setIsHoveredEdit] = useState(false)
  const [isHoveredDelete, setIsHoveredDelete] = useState(false)
  const [isHoveredNo, setIsHoveredNo] = useState(false)
  const [isGroupHovered, setIsGroupHovered] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Optimistic toggle state
  const [optimisticDone, setOptimisticDone] = useState<boolean | null>(null)
  const isPendingRef = useRef(false)

  // Displayed value: optimistic when set, otherwise prop
  const displayedDone = optimisticDone !== null ? optimisticDone : deliverable.done

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [isEditing])

  // Clear error timeout on unmount
  useEffect(() => {
    return () => {
      if (errorTimeoutRef.current) {
        clearTimeout(errorTimeoutRef.current)
      }
    }
  }, [])

  // Reset optimistic state when server prop changes
  useEffect(() => {
    setOptimisticDone(null)
  }, [deliverable.done])

  const showError = (message: string) => {
    if (errorTimeoutRef.current) clearTimeout(errorTimeoutRef.current)
    setError(message)
    errorTimeoutRef.current = setTimeout(() => setError(null), 3000)
  }

  const handleToggle = async () => {
    if (isPendingRef.current || disabled || isInline || !onToggle) return

    // Capture current displayed value and flip optimistically
    const currentValue = displayedDone
    const newValue = !currentValue
    setOptimisticDone(newValue)
    setError(null)

    isPendingRef.current = true
    try {
      await onToggle(deliverable.id, newValue)
      // Success: clear optimistic state (prop-sync useEffect is safety net)
      setOptimisticDone(null)
    } catch (e) {
      // Revert optimistic state to original value
      setOptimisticDone(currentValue)
      showError(e instanceof Error ? e.message : t('couldntSave'))
    } finally {
      isPendingRef.current = false
    }
  }

  const handleSaveEdit = async () => {
    if (isLoading || !onRename) return
    const trimmedName = editName.trim()

    // Empty text - revert to original
    if (!trimmedName) {
      setEditName(deliverable.name)
      setIsEditing(false)
      return
    }

    // No change - just close
    if (trimmedName === deliverable.name) {
      setIsEditing(false)
      return
    }
    setIsLoading(true)
    setError(null)
    try {
      await onRename(deliverable.id, trimmedName)
      setIsEditing(false)
    } catch (e) {
      showError(e instanceof Error ? e.message : t('couldntSave'))
      setEditName(deliverable.name) // Revert
    } finally {
      setIsLoading(false)
    }
  }

  const handleCancelEdit = () => {
    setEditName(deliverable.name)
    setIsEditing(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSaveEdit()
    } else if (e.key === 'Escape') {
      handleCancelEdit()
    }
  }

  const handleDelete = async () => {
    if (isLoading || !onDelete) return
    setIsLoading(true)
    setError(null)
    try {
      await onDelete(deliverable.id)
    } catch (e) {
      showError(e instanceof Error ? e.message : t('couldntSave'))
      setShowDeleteConfirm(false)
    } finally {
      setIsLoading(false)
    }
  }

  // Inline mode - display only (using inline styles for Claude widget)
  if (isInline) {
    return (
      <li style={{ paddingBottom: '8px', borderBottom: isLast ? 'none' : '1px solid var(--color-border-tertiary, rgba(31,30,29,0.15))' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {/* Checkbox (display only) — 16×16px visual element */}
          <span
            style={{
              width: '16px',
              height: '16px',
              borderRadius: '4px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              background: deliverable.done ? 'var(--color-text-tertiary, #73726C)' : 'transparent',
              border: deliverable.done ? 'none' : '1.5px solid var(--color-border-primary, rgba(31,30,29,0.4))',
            }}
            aria-hidden="true"
          >
            {deliverable.done && (
              <svg style={{ width: '10px', height: '10px', color: 'var(--color-background-primary, #fff)' }} viewBox="0 0 12 12" fill="none" aria-hidden="true">
                <path d="M2 6L5 9L10 3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            )}
          </span>

          {/* Name */}
          <span
            style={{
              flex: 1,
              fontSize: '12px',
              overflowWrap: 'break-word',
              color: deliverable.done ? 'var(--color-text-tertiary, #73726C)' : 'var(--color-text-primary, #141413)',
              textDecoration: deliverable.done ? 'line-through' : 'none',
            }}
          >
            {deliverable.name}
          </span>
        </div>
      </li>
    )
  }

  // Fullscreen mode - show delete confirmation
  if (showDeleteConfirm) {
    return (
      <li
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '8px',
          background: 'var(--color-background-secondary, #F5F4ED)',
          borderRadius: '6px',
        }}
      >
        <span style={{ fontSize: '12px', color: 'var(--color-text-primary, #141413)', flex: 1 }}>
          {t('removeItem', { name: deliverable.name })}
        </span>
        <button
          type="button"
          onClick={handleDelete}
          disabled={isLoading}
          style={{
            fontSize: '12px',
            color: 'var(--color-text-danger, #7F2C28)',
            fontWeight: 500,
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: '0 8px',
            minHeight: '44px',
            minWidth: '44px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            touchAction: 'manipulation',
            WebkitTapHighlightColor: 'transparent',
          }}
          aria-label={t('confirmRemove')}
        >
          {isLoading ? '...' : t('yes')}
        </button>
        <button
          type="button"
          onClick={() => setShowDeleteConfirm(false)}
          onMouseEnter={() => setIsHoveredNo(true)}
          onMouseLeave={() => setIsHoveredNo(false)}
          disabled={isLoading}
          style={{
            fontSize: '12px',
            color: isHoveredNo ? 'var(--color-text-primary, #141413)' : 'var(--color-text-secondary, #73726C)',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: '0 8px',
            minHeight: '44px',
            minWidth: '44px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            touchAction: 'manipulation',
            WebkitTapHighlightColor: 'transparent',
          }}
          aria-label={t('cancelRemove')}
        >
          {t('no')}
        </button>
      </li>
    )
  }

  // Fullscreen mode - interactive with CRUD
  return (
    <li style={{ paddingBottom: '8px', borderBottom: isLast ? 'none' : '1px solid var(--color-border-tertiary, rgba(31,30,29,0.15))' }}>
      {error && (
        <p style={{ fontSize: '12px', color: 'var(--color-text-danger, #7F2C28)', marginBottom: '4px' }} role="alert">
          {error}
        </p>
      )}
      <div
        style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: '8px' }}
        onMouseEnter={() => setIsGroupHovered(true)}
        onMouseLeave={() => setIsGroupHovered(false)}
      >
        {/* Checkbox — 44pt tap target via absolute positioning (no height inflation) */}
        <div style={{ position: 'relative', width: '16px', height: '16px', flexShrink: 0, alignSelf: 'center' }}>
          {/* Invisible tap target extender */}
          <span
            onClick={handleToggle}
            style={{
              position: 'absolute',
              top: '-14px',
              left: '-14px',
              right: '-14px',
              bottom: '-14px',
              cursor: disabled ? 'not-allowed' : 'pointer',
              touchAction: 'manipulation',
              WebkitTapHighlightColor: 'transparent',
            }}
            aria-hidden="true"
          />
          {/* Visual checkbox button — 16×16px, no height inflation */}
          <button
            type="button"
            onClick={handleToggle}
            disabled={disabled || !onToggle}
            style={{
              width: '16px',
              height: '16px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: displayedDone ? 'var(--color-text-tertiary, #73726C)' : 'transparent',
              border: displayedDone ? 'none' : '1.5px solid var(--color-border-primary, rgba(31,30,29,0.4))',
              borderRadius: '4px',
              padding: 0,
              cursor: disabled ? 'not-allowed' : 'pointer',
              touchAction: 'manipulation',
              WebkitTapHighlightColor: 'transparent',
            }}
            role="checkbox"
            aria-checked={displayedDone}
            aria-disabled={disabled}
            aria-label={t(displayedDone ? 'markAsNotDone' : 'markAsDone', { name: deliverable.name })}
          >
            {displayedDone && (
              <svg style={{ width: '10px', height: '10px', color: 'var(--color-background-primary, #fff)' }} viewBox="0 0 12 12" fill="none" aria-hidden="true">
                <path d="M2 6L5 9L10 3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            )}
          </button>
        </div>

        {/* Name (editable) */}
        {isEditing ? (
          <input
            ref={inputRef}
            type="text"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            onBlur={handleSaveEdit}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            style={{
              flex: 1,
              fontSize: '14px',
              color: 'var(--color-text-primary, #141413)',
              background: 'var(--color-background-primary, #fff)',
              border: '1px solid var(--color-border-primary, rgba(31,30,29,0.4))',
              borderRadius: '8px',
              padding: '8px 12px',
              outline: 'none',
            }}
            aria-label="Edit deliverable name"
          />
        ) : (
          <span
            style={{
              flex: 1,
              fontSize: '14px',
              cursor: 'pointer',
              overflowWrap: 'break-word',
              color: displayedDone ? 'var(--color-text-tertiary, #73726C)' : 'var(--color-text-primary, #141413)',
              textDecoration: displayedDone ? 'line-through' : 'none',
            }}
            onDoubleClick={() => !disabled && onRename && setIsEditing(true)}
            title={onRename ? t('doubleClickToEdit') : undefined}
          >
            {deliverable.name}
          </span>
        )}

        {/* Actions (visible on hover) — absolute to avoid inflating row height */}
        {!isEditing && !disabled && (onRename || onDelete) && (
          <div
            style={{
              position: 'absolute',
              right: 0,
              top: '50%',
              transform: 'translateY(-50%)',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              opacity: isGroupHovered ? 1 : (isTouchDevice ? 0.4 : 0),
              transition: 'opacity 0.15s',
            }}
          >
            {onRename && (
              <button
                type="button"
                onClick={() => setIsEditing(true)}
                onMouseEnter={() => setIsHoveredEdit(true)}
                onMouseLeave={() => setIsHoveredEdit(false)}
                style={{
                  padding: 0,
                  width: '44px',
                  height: '44px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: isHoveredEdit ? 'var(--color-text-primary, #141413)' : 'var(--color-text-tertiary, #73726C)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  touchAction: 'manipulation',
                  WebkitTapHighlightColor: 'transparent',
                }}
                aria-label={t('editItem', { name: deliverable.name })}
              >
                <svg style={{ width: '14px', height: '14px' }} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                  <path d="M11.5 2.5l2 2M2 14l.5-2 9-9 2 2-9 9-2.5.5z"/>
                </svg>
              </button>
            )}
            {onDelete && (
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(true)}
                onMouseEnter={() => setIsHoveredDelete(true)}
                onMouseLeave={() => setIsHoveredDelete(false)}
                style={{
                  padding: 0,
                  width: '44px',
                  height: '44px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: isHoveredDelete ? 'var(--color-text-danger, #7F2C28)' : 'var(--color-text-tertiary, #73726C)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  touchAction: 'manipulation',
                  WebkitTapHighlightColor: 'transparent',
                }}
                aria-label={t('deleteItemAction', { name: deliverable.name })}
              >
                <svg style={{ width: '14px', height: '14px' }} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                  <path d="M2 4h12M5.5 4V2.5a1 1 0 011-1h3a1 1 0 011 1V4"/>
                  <path d="M12.5 4v9a1.5 1.5 0 01-1.5 1.5H5a1.5 1.5 0 01-1.5-1.5V4"/>
                  <path d="M6.5 7v5M8 7v5M9.5 7v5"/>
                </svg>
              </button>
            )}
          </div>
        )}
      </div>
    </li>
  )
}
