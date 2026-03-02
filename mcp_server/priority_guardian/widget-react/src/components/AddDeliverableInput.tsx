import { useState, useRef, useEffect } from 'react'
import { Button } from '@openai/apps-sdk-ui/components/Button'

interface AddDeliverableInputProps {
  priorityId: string
  onAdd: (priorityId: string, name: string) => Promise<void>
  disabled?: boolean
}

export function AddDeliverableInput({
  priorityId,
  onAdd,
  disabled = false,
}: AddDeliverableInputProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [name, setName] = useState('')
  const [isAdding, setIsAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isOpen])

  const handleAdd = async () => {
    if (!name.trim()) {
      setError('Name is required')
      return
    }
    setError(null)
    setIsAdding(true)
    try {
      await onAdd(priorityId, name.trim())
      setName('')
      setIsOpen(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save. Try again.")
    } finally {
      setIsAdding(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleAdd()
    } else if (e.key === 'Escape') {
      setName('')
      setIsOpen(false)
      setError(null)
    }
  }

  const handleCancel = () => {
    setName('')
    setIsOpen(false)
    setError(null)
  }

  if (!isOpen) {
    return (
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        disabled={disabled}
        className="flex items-center gap-1 text-xs text-secondary hover:text-default disabled:opacity-50"
        aria-label="Add new deliverable"
      >
        <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <path d="M8 3v10M3 8h10"/>
        </svg>
        Add deliverable
      </button>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <input
          ref={inputRef}
          type="text"
          value={name}
          onChange={(e) => {
            setName(e.target.value)
            if (error) setError(null)
          }}
          onKeyDown={handleKeyDown}
          disabled={isAdding}
          placeholder="Deliverable name"
          className="flex-1 text-sm text-default bg-surface border border-default rounded-lg px-3 py-2 focus:outline-none focus:border-tertiary"
          aria-label="New deliverable name"
          aria-describedby={error ? 'deliverable-error' : undefined}
        />
        <Button
          color="primary"
          variant="solid"
          size="sm"
          onClick={handleAdd}
          disabled={isAdding || !name.trim()}
        >
          {isAdding ? 'Adding...' : 'Add'}
        </Button>
        <Button
          color="secondary"
          variant="ghost"
          size="sm"
          onClick={handleCancel}
          disabled={isAdding}
        >
          Cancel
        </Button>
      </div>
      {error && (
        <p id="deliverable-error" className="text-xs text-danger" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
