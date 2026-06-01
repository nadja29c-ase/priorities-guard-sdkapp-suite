import { useState, useRef, useEffect } from 'react'
import type { Goal } from '../types'
import { t } from '../i18n'

interface GoalItemProps {
  goal: Goal
  isInline?: boolean  // When true, display-only (no CRUD actions)
  isLast?: boolean    // When true, no bottom border (last item in list)
  onToggle?: (goalId: string, achieved: boolean) => Promise<void>
  onRename?: (goalId: string, text: string) => Promise<void>
  onDelete?: (goalId: string) => Promise<void>
  disabled?: boolean
}

// Touch device detection — icons always visible on mobile (no hover)
const isTouchDevice = typeof window !== 'undefined' && window.matchMedia('(hover: none)').matches

/**
 * GoalItem - V7 style with edit/delete parity to DeliverableItem
 * - 18px circular checkbox (green bg-success-solid when achieved)
 * - Text with strikethrough when achieved
 * - Double-click to edit, hover edit/delete actions
 * - Inline delete confirmation
 */
export function GoalItem({
  goal,
  isInline = false,
  isLast = false,
  onToggle,
  onRename,
  onDelete,
  disabled = false,
}: GoalItemProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [editText, setEditText] = useState(goal.text)
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
  const [optimisticAchieved, setOptimisticAchieved] = useState<boolean | null>(null)
  const isPendingRef = useRef(false)

  // Displayed value: optimistic when set, otherwise prop
  const displayedAchieved = optimisticAchieved !== null ? optimisticAchieved : goal.achieved

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
    setOptimisticAchieved(null)
  }, [goal.achieved])

  const showErrorMessage = (message: string) => {
    if (errorTimeoutRef.current) clearTimeout(errorTimeoutRef.current)
    setError(message)
    errorTimeoutRef.current = setTimeout(() => setError(null), 3000)
  }

  const handleToggle = async () => {
    if (isPendingRef.current || disabled || isInline || !onToggle) return

    // Capture current displayed value and flip optimistically
    const currentValue = displayedAchieved
    const newValue = !currentValue
    setOptimisticAchieved(newValue)
    setError(null)

    isPendingRef.current = true
    try {
      await onToggle(goal.id, newValue)
      // Success: clear optimistic state (prop-sync useEffect is safety net)
      setOptimisticAchieved(null)
    } catch (e) {
      // Revert optimistic state to original value
      setOptimisticAchieved(currentValue)
      showErrorMessage(e instanceof Error ? e.message : t('couldntSave'))
    } finally {
      isPendingRef.current = false
    }
  }

  const handleSaveEdit = async () => {
    if (isLoading || !onRename) return
    const trimmedText = editText.trim()

    // Empty text - revert to original
    if (!trimmedText) {
      setEditText(goal.text)
      setIsEditing(false)
      return
    }

    // No change - just close
    if (trimmedText === goal.text) {
      setIsEditing(false)
      return
    }

    setIsLoading(true)
    setError(null)
    try {
      await onRename(goal.id, trimmedText)
      setIsEditing(false)
    } catch (e) {
      showErrorMessage(e instanceof Error ? e.message : t('couldntSave'))
      setEditText(goal.text) // Revert
    } finally {
      setIsLoading(false)
    }
  }

  const handleCancelEdit = () => {
    setEditText(goal.text)
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
      await onDelete(goal.id)
    } catch (e) {
      showErrorMessage(e instanceof Error ? e.message : t('couldntSave'))
      setShowDeleteConfirm(false)
    } finally {
      setIsLoading(false)
    }
  }

  // Inline mode - display only (using inline styles for Claude widget)
  if (isInline) {
    return (
      <li style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
        {/* Circular checkbox (display only) - 18px diameter */}
        <span
          style={{
            marginTop: '2px',
            width: '18px',
            height: '18px',
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            background: goal.achieved ? 'var(--color-background-success-solid, #10b981)' : 'transparent',
            border: goal.achieved ? 'none' : '1.5px solid var(--color-border-primary, rgba(31,30,29,0.4))',
          }}
          aria-hidden="true"
        >
          {goal.achieved && (
            <svg style={{ width: '10px', height: '10px', color: 'var(--color-background-primary, #fff)' }} viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M2 6l3 3 5-5" />
            </svg>
          )}
        </span>

        {/* Goal text */}
        <p
          style={{
            flex: 1,
            minWidth: 0,
            fontSize: '11px',
            overflowWrap: 'break-word',
            color: goal.achieved ? 'var(--color-text-tertiary, #73726C)' : 'var(--color-text-primary, #141413)',
            textDecoration: goal.achieved ? 'line-through' : 'none',
          }}
        >
          {goal.text}
        </p>
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
          {t('removeItem', { name: goal.text })}
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
        style={{ position: 'relative', display: 'flex', alignItems: 'flex-start', gap: '10px' }}
        onMouseEnter={() => setIsGroupHovered(true)}
        onMouseLeave={() => setIsGroupHovered(false)}
      >
        {/* Circular checkbox — 44pt tap target via absolute positioning (no height inflation) */}
        <div style={{ position: 'relative', width: '18px', height: '18px', flexShrink: 0, alignSelf: 'center' }}>
          {/* Invisible tap target extender */}
          <span
            onClick={handleToggle}
            style={{
              position: 'absolute',
              top: '-13px',
              left: '-13px',
              right: '-13px',
              bottom: '-13px',
              cursor: disabled ? 'not-allowed' : 'pointer',
              touchAction: 'manipulation',
              WebkitTapHighlightColor: 'transparent',
            }}
            aria-hidden="true"
          />
          {/* Visual checkbox button — 18×18px, no height inflation */}
          <button
            type="button"
            onClick={handleToggle}
            disabled={disabled || !onToggle}
            style={{
              width: '18px',
              height: '18px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: displayedAchieved ? 'var(--color-background-success-solid, #10b981)' : 'transparent',
              border: displayedAchieved ? 'none' : '1.5px solid var(--color-border-primary, rgba(31,30,29,0.4))',
              borderRadius: '50%',
              padding: 0,
              cursor: disabled ? 'not-allowed' : 'pointer',
              touchAction: 'manipulation',
              WebkitTapHighlightColor: 'transparent',
              opacity: disabled ? 0.5 : 1,
              transition: 'all 0.15s ease-out',
            }}
            role="checkbox"
            aria-checked={displayedAchieved}
            aria-disabled={disabled}
            aria-label={t(displayedAchieved ? 'markAsNotAchieved' : 'markAsAchieved', { name: goal.text })}
          >
            {displayedAchieved && (
              <svg style={{ width: '10px', height: '10px', color: '#fff' }} viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M2 6l3 3 5-5" />
              </svg>
            )}
          </button>
        </div>

        {/* Goal text (editable) */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {isEditing ? (
            <input
              ref={inputRef}
              type="text"
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              onBlur={handleSaveEdit}
              onKeyDown={handleKeyDown}
              disabled={isLoading}
              style={{
                width: '100%',
                fontSize: '14px',
                color: 'var(--color-text-primary, #141413)',
                background: 'var(--color-background-primary, #fff)',
                border: '1px solid var(--color-border-primary, rgba(31,30,29,0.4))',
                borderRadius: '8px',
                padding: '8px 12px',
                outline: 'none',
              }}
              aria-label={t('editGoalText')}
            />
          ) : (
            <p
              style={{
                margin: 0,
                fontSize: '14px',
                cursor: 'pointer',
                overflowWrap: 'break-word',
                color: displayedAchieved ? 'var(--color-text-tertiary, #73726C)' : 'var(--color-text-primary, #141413)',
                textDecoration: displayedAchieved ? 'line-through' : 'none',
              }}
              onDoubleClick={() => !disabled && onRename && setIsEditing(true)}
              title={onRename ? t('doubleClickToEdit') : undefined}
            >
              {goal.text}
            </p>
          )}
        </div>

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
                aria-label={t('editItem', { name: goal.text })}
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
                aria-label={t('deleteItemAction', { name: goal.text })}
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
