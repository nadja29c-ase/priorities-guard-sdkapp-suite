import { useState, useRef, useEffect, useCallback } from 'react'
import type { Goal } from '../types'

interface GoalItemProps {
  goal: Goal
  onToggle: (goalId: string, achieved: boolean) => Promise<void>
  onRename: (goalId: string, text: string) => Promise<void>
  onDelete: (goalId: string) => Promise<void>
  disabled?: boolean
}

export function GoalItem({
  goal,
  onToggle,
  onRename,
  onDelete,
  disabled = false,
}: GoalItemProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [editText, setEditText] = useState(goal.text)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Sync editText with goal.text when goal changes
  useEffect(() => {
    setEditText(goal.text)
  }, [goal.text])

  // Focus input when entering edit mode
  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [isEditing])

  // Clear timeout on unmount
  useEffect(() => {
    return () => {
      if (errorTimeoutRef.current) {
        clearTimeout(errorTimeoutRef.current)
      }
    }
  }, [])

  const handleToggle = useCallback(async () => {
    if (disabled || isLoading) return
    setIsLoading(true)
    setError(null)
    try {
      await onToggle(goal.id, !goal.achieved)
    } catch (e) {
      console.error('Toggle goal error:', e)
      setError(e instanceof Error ? e.message : 'Failed to update')
      errorTimeoutRef.current = setTimeout(() => setError(null), 3000)
    } finally {
      setIsLoading(false)
    }
  }, [disabled, isLoading, onToggle, goal.id, goal.achieved])

  const handleSave = useCallback(async () => {
    const trimmed = editText.trim()
    if (!trimmed) {
      setEditText(goal.text)
      setIsEditing(false)
      return
    }
    if (trimmed === goal.text) {
      setIsEditing(false)
      return
    }

    setIsLoading(true)
    setError(null)
    try {
      await onRename(goal.id, trimmed)
      setIsEditing(false)
    } catch (e) {
      console.error('Rename goal error:', e)
      setError(e instanceof Error ? e.message : 'Failed to save')
      errorTimeoutRef.current = setTimeout(() => setError(null), 3000)
      setEditText(goal.text) // Revert
    } finally {
      setIsLoading(false)
    }
  }, [editText, goal.text, goal.id, onRename])

  const handleDelete = useCallback(async () => {
    if (disabled || isLoading) return
    setIsLoading(true)
    setError(null)
    try {
      await onDelete(goal.id)
    } catch (e) {
      console.error('Delete goal error:', e)
      setError(e instanceof Error ? e.message : 'Failed to delete')
      errorTimeoutRef.current = setTimeout(() => setError(null), 3000)
    } finally {
      setIsLoading(false)
    }
  }, [disabled, isLoading, onDelete, goal.id])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSave()
    } else if (e.key === 'Escape') {
      setEditText(goal.text)
      setIsEditing(false)
    }
  }

  return (
    <li className="flex items-start gap-2 group">
      {/* Circular checkbox */}
      <button
        type="button"
        onClick={handleToggle}
        disabled={disabled || isLoading}
        className={`flex-shrink-0 w-4 h-4 mt-0.5 rounded-full border-2 transition-colors ${
          goal.achieved
            ? 'bg-success border-success'
            : 'border-outline-default hover:border-outline-strong'
        } ${(disabled || isLoading) ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
        aria-label={goal.achieved ? 'Mark as not achieved' : 'Mark as achieved'}
      >
        {goal.achieved && (
          <svg className="w-full h-full text-white p-0.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="3">
            <path d="M3 8l4 4 6-6" />
          </svg>
        )}
      </button>

      {/* Goal text or edit input */}
      <div className="flex-1 min-w-0">
        {isEditing ? (
          <input
            ref={inputRef}
            type="text"
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            onBlur={handleSave}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            maxLength={200}
            className="w-full text-sm text-default bg-surface border border-default rounded px-2 py-0.5 focus:outline-none focus:border-tertiary"
            aria-label="Edit goal text"
          />
        ) : (
          <span
            className={`text-sm cursor-pointer hover:text-info ${goal.achieved ? 'line-through text-tertiary' : 'text-default'}`}
            onClick={() => !disabled && setIsEditing(true)}
            title="Click to edit"
          >
            {goal.text}
          </span>
        )}
        {error && (
          <p className="text-xs text-danger mt-0.5" role="alert">{error}</p>
        )}
      </div>

      {/* Delete button (visible on hover) */}
      {!isEditing && (
        <button
          type="button"
          onClick={handleDelete}
          disabled={disabled || isLoading}
          className="flex-shrink-0 p-0.5 text-tertiary hover:text-danger opacity-0 group-hover:opacity-100 transition-opacity"
          aria-label={`Delete goal: ${goal.text}`}
        >
          <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M4 4l8 8M12 4l-8 8" />
          </svg>
        </button>
      )}
    </li>
  )
}
