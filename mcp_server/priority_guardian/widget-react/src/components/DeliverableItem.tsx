import { useState, useRef, useEffect } from 'react'
import type { Deliverable } from '../types'
import { t } from '../i18n'

interface DeliverableItemProps {
  deliverable: Deliverable
  onToggle: (deliverableId: string, done: boolean) => Promise<void>
  onRename: (deliverableId: string, name: string) => Promise<void>
  onDelete: (deliverableId: string) => Promise<void>
  disabled?: boolean
}

export function DeliverableItem({
  deliverable,
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
    if (isPendingRef.current || disabled) return

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
    if (isLoading) return
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
    if (isLoading) return
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

  if (showDeleteConfirm) {
    return (
      <li className="flex items-center gap-2 p-2 bg-surface-secondary rounded">
        <span className="text-xs text-default flex-1">{t('removeItem').replace('{name}', deliverable.name)}</span>
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
        >
          {t('no')}
        </button>
      </li>
    )
  }

  return (
    <li className="pb-2 border-b border-subtle last:border-b-0 last:pb-0">
      {error && (
        <p className="text-xs text-danger mb-1" role="alert">{error}</p>
      )}
      <div className="flex items-center gap-2 group">
      {/* Checkbox */}
      <button
        type="button"
        onClick={handleToggle}
        disabled={disabled}
        className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 ${
          displayedDone
            ? 'bg-tertiary border-tertiary'
            : 'border-default hover:border-strong'
        }`}
        role="checkbox"
        aria-checked={displayedDone}
        aria-disabled={disabled}
        aria-label={`Mark "${deliverable.name}" as ${displayedDone ? 'not done' : 'done'}`}
      >
        {displayedDone && (
          <svg className="w-2.5 h-2.5 text-surface" viewBox="0 0 12 12" fill="none" aria-hidden="true">
            <path d="M2 6L5 9L10 3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )}
      </button>

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
          className="flex-1 text-sm text-default bg-surface border border-default rounded-lg px-3 py-2 focus:outline-none focus:border-tertiary"
          aria-label="Edit deliverable name"
        />
      ) : (
        <span
          className={`flex-1 text-sm cursor-pointer break-words ${displayedDone ? 'text-tertiary line-through' : 'text-default'}`}
          onDoubleClick={() => !disabled && setIsEditing(true)}
          title="Double-click to edit"
        >
          {deliverable.name}
        </span>
      )}

      {/* Actions (visible on hover) */}
      {!isEditing && !disabled && (
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            type="button"
            onClick={() => setIsEditing(true)}
            className="p-1 text-tertiary hover:text-default"
            aria-label={`Edit "${deliverable.name}"`}
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <path d="M11.5 2.5l2 2M2 14l.5-2 9-9 2 2-9 9-2.5.5z"/>
            </svg>
          </button>
          <button
            type="button"
            onClick={() => setShowDeleteConfirm(true)}
            className="p-1 text-tertiary hover:text-danger"
            aria-label={`Delete "${deliverable.name}"`}
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <path d="M2 4h12M5.5 4V2.5a1 1 0 011-1h3a1 1 0 011 1V4"/>
              <path d="M12.5 4v9a1.5 1.5 0 01-1.5 1.5H5a1.5 1.5 0 01-1.5-1.5V4"/>
              <path d="M6.5 7v5M8 7v5M9.5 7v5"/>
            </svg>
          </button>
        </div>
      )}
      </div>
    </li>
  )
}
