import { useState, useRef, useEffect } from 'react'
import type { Goal } from '../types'
import { t } from '../i18n'

interface GoalItemProps {
  goal: Goal
  onToggle: (goalId: string, achieved: boolean) => Promise<void>
  onRename?: (goalId: string, text: string) => Promise<void>
  onDelete?: (goalId: string) => Promise<void>
  disabled?: boolean
}

/**
 * GoalItem - V7 style with edit/delete parity to DeliverableItem
 * - 18px circular checkbox (green bg-success-solid when achieved)
 * - Text with strikethrough when achieved
 * - Double-click to edit, hover edit/delete actions
 * - Inline delete confirmation
 */
export function GoalItem({
  goal,
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
    if (isPendingRef.current || disabled) return

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

  // Delete confirmation view
  if (showDeleteConfirm) {
    return (
      <li className="flex items-center gap-2 p-2 bg-surface-secondary rounded">
        <span className="text-xs text-default flex-1">{t('removeItem').replace('{name}', goal.text)}</span>
        <button
          type="button"
          onClick={handleDelete}
          disabled={isLoading}
          className="text-xs text-danger hover:text-danger font-medium"
          aria-label={t('confirmRemove')}
        >
          {isLoading ? '...' : t('yes')}
        </button>
        <button
          type="button"
          onClick={() => setShowDeleteConfirm(false)}
          disabled={isLoading}
          className="text-xs text-secondary hover:text-default"
          aria-label={t('cancelRemove')}
        >
          {t('no')}
        </button>
      </li>
    )
  }

  return (
    <li>
      {error && (
        <p className="text-xs text-danger mb-1" role="alert">{error}</p>
      )}
      <div className="flex items-start gap-2.5 group">
        {/* Circular checkbox - 18px diameter, green when achieved */}
        <button
          type="button"
          onClick={handleToggle}
          disabled={disabled}
          className="mt-0.5 flex-shrink-0 transition-all"
          role="checkbox"
          aria-checked={displayedAchieved}
          aria-disabled={disabled}
          aria-label={`Mark "${goal.text}" as ${displayedAchieved ? 'not achieved' : 'achieved'}`}
        >
          <span
            className={`w-[18px] h-[18px] rounded-full flex items-center justify-center transition-all duration-150 ease-out ${
              displayedAchieved ? 'bg-success-solid border-0' : 'border-[1.5px] border-strong'
            } ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
          >
            {displayedAchieved && (
              <svg className="w-2.5 h-2.5 text-white" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M2 6l3 3 5-5" />
              </svg>
            )}
          </span>
        </button>

      {/* Goal text (editable) */}
      <div className="flex-1 min-w-0">
        {isEditing ? (
          <input
            ref={inputRef}
            type="text"
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            onBlur={handleSaveEdit}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            className="w-full text-sm text-default bg-surface border border-default rounded-lg px-3 py-2 focus:outline-none focus:border-tertiary"
            aria-label="Edit goal text"
          />
        ) : (
          <p
            className={`text-sm transition-colors cursor-pointer [overflow-wrap:break-word] ${displayedAchieved ? 'line-through text-tertiary' : 'text-default'}`}
            onDoubleClick={() => !disabled && onRename && setIsEditing(true)}
            title={onRename ? "Double-click to edit" : undefined}
          >
            {goal.text}
          </p>
        )}
      </div>

      {/* Actions (visible on hover) */}
      {!isEditing && !disabled && (onRename || onDelete) && (
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity mt-0.5">
          {onRename && (
            <button
              type="button"
              onClick={() => setIsEditing(true)}
              className="p-1 text-tertiary hover:text-default"
              aria-label={`Edit "${goal.text}"`}
            >
              <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                <path d="M11.5 2.5l2 2M2 14l.5-2 9-9 2 2-9 9-2.5.5z"/>
              </svg>
            </button>
          )}
          {onDelete && (
            <button
              type="button"
              onClick={() => setShowDeleteConfirm(true)}
              className="p-1 text-tertiary hover:text-danger"
              aria-label={`Delete "${goal.text}"`}
            >
              <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
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
