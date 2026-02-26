import { useState, useRef, useEffect } from 'react'
import type { Goal } from '../types'

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

  const showErrorMessage = (message: string) => {
    setError(message)
    errorTimeoutRef.current = setTimeout(() => setError(null), 3000)
  }

  const handleToggle = async () => {
    if (isLoading || disabled) return
    setIsLoading(true)
    setError(null)
    try {
      await onToggle(goal.id, !goal.achieved)
    } catch (e) {
      showErrorMessage(e instanceof Error ? e.message : "Couldn't save. Try again.")
    } finally {
      setIsLoading(false)
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
      showErrorMessage(e instanceof Error ? e.message : "Couldn't save. Try again.")
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
      showErrorMessage(e instanceof Error ? e.message : "Couldn't save. Try again.")
      setShowDeleteConfirm(false)
    } finally {
      setIsLoading(false)
    }
  }

  // Delete confirmation view
  if (showDeleteConfirm) {
    return (
      <li className="flex items-center gap-2 p-2 bg-surface-secondary rounded">
        <span className="text-xs text-default flex-1">Remove "{goal.text}"?</span>
        <button
          type="button"
          onClick={handleDelete}
          disabled={isLoading}
          className="text-xs text-danger hover:text-danger font-medium"
          aria-label="Confirm remove"
        >
          {isLoading ? '...' : 'Yes'}
        </button>
        <button
          type="button"
          onClick={() => setShowDeleteConfirm(false)}
          disabled={isLoading}
          className="text-xs text-secondary hover:text-default"
          aria-label="Cancel remove"
        >
          No
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
        disabled={disabled || isLoading}
        className="mt-0.5 flex-shrink-0 transition-all"
        role="checkbox"
        aria-checked={goal.achieved}
        aria-label={`Mark "${goal.text}" as ${goal.achieved ? 'not achieved' : 'achieved'}`}
      >
        <span
          className={`rounded-full flex items-center justify-center ${goal.achieved ? 'bg-success-solid' : ''}`}
          style={{
            width: '18px',
            height: '18px',
            border: goal.achieved ? 'none' : '1.5px solid var(--color-border-strong)',
            transition: 'all 150ms ease-out',
            opacity: (disabled || isLoading) ? 0.5 : 1,
            cursor: (disabled || isLoading) ? 'not-allowed' : 'pointer',
          }}
        >
          {goal.achieved && (
            <svg className="w-2.5 h-2.5" viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth="2">
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
            className={`text-sm transition-colors cursor-pointer ${goal.achieved ? 'line-through text-tertiary' : 'text-default'}`}
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
              <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
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
              <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
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
