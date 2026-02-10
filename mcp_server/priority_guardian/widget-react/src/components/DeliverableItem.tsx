import { useState, useRef, useEffect } from 'react'
import type { Deliverable } from '../types'

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
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [isEditing])

  const handleToggle = async () => {
    if (isLoading || disabled) return
    setIsLoading(true)
    try {
      await onToggle(deliverable.id, !deliverable.done)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSaveEdit = async () => {
    if (isLoading || !editName.trim()) return
    if (editName.trim() === deliverable.name) {
      setIsEditing(false)
      return
    }
    setIsLoading(true)
    try {
      await onRename(deliverable.id, editName.trim())
      setIsEditing(false)
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
    try {
      await onDelete(deliverable.id)
    } finally {
      setIsLoading(false)
      setShowDeleteConfirm(false)
    }
  }

  if (showDeleteConfirm) {
    return (
      <li className="flex items-center gap-2 p-2 bg-surface-secondary rounded">
        <span className="text-xs text-default flex-1">Remove "{deliverable.name}"?</span>
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
        >
          No
        </button>
      </li>
    )
  }

  return (
    <li className="flex items-center gap-2 group">
      {/* Checkbox */}
      <button
        type="button"
        onClick={handleToggle}
        disabled={isLoading || disabled}
        className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 ${
          deliverable.done
            ? 'bg-tertiary border-tertiary'
            : 'border-default hover:border-strong'
        } ${isLoading ? 'opacity-50' : ''}`}
        role="checkbox"
        aria-checked={deliverable.done}
        aria-label={`Mark "${deliverable.name}" as ${deliverable.done ? 'not done' : 'done'}`}
      >
        {deliverable.done && (
          <svg className="w-2.5 h-2.5 text-surface" viewBox="0 0 12 12" fill="none">
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
          className="flex-1 text-sm text-default bg-surface border border-default rounded px-2 py-0.5 focus:outline-none focus:ring-1 focus:ring-info"
          aria-label="Edit deliverable name"
        />
      ) : (
        <span
          className={`flex-1 text-sm cursor-pointer ${deliverable.done ? 'text-tertiary line-through' : 'text-default'}`}
          onDoubleClick={() => !disabled && setIsEditing(true)}
          title="Double-click to edit"
        >
          {deliverable.name}
        </span>
      )}

      {/* Actions (visible on hover) */}
      {!isEditing && !disabled && (
        <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            type="button"
            onClick={() => setIsEditing(true)}
            className="p-1 text-tertiary hover:text-default"
            aria-label={`Edit "${deliverable.name}"`}
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M11.5 2.5l2 2M2 14l.5-2 9-9 2 2-9 9-2.5.5z"/>
            </svg>
          </button>
          <button
            type="button"
            onClick={() => setShowDeleteConfirm(true)}
            className="p-1 text-tertiary hover:text-danger"
            aria-label={`Delete "${deliverable.name}"`}
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 4h10M6 4V3a1 1 0 011-1h2a1 1 0 011 1v1M13 4v9a1 1 0 01-1 1H4a1 1 0 01-1-1V4"/>
            </svg>
          </button>
        </div>
      )}
    </li>
  )
}
