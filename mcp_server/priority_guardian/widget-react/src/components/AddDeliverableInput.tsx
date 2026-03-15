import { useState, useRef, useEffect } from 'react'
import { Button } from '@openai/apps-sdk-ui/components/Button'
import { t } from '../i18n'

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
      setError(t('deliverableNameRequired'))
      return
    }
    setError(null)
    setIsAdding(true)
    try {
      await onAdd(priorityId, name.trim())
      setName('')
      setIsOpen(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('couldntSave'))
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
        aria-label={t('addDeliverable')}
      >
        <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <path d="M8 3v10M3 8h10"/>
        </svg>
        {t('addDeliverable')}
      </button>
    )
  }

  return (
    <div className="space-y-2">
      {/* Row 1: Input full width */}
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
        placeholder={t('deliverableNamePlaceholder')}
        className="w-full text-sm text-default bg-surface border border-default rounded-lg px-3 py-2 focus:outline-none focus:border-tertiary"
        aria-label={t('deliverableNamePlaceholder')}
        aria-describedby={error ? 'deliverable-error' : undefined}
      />
      {/* Row 2: Add + Cancel buttons */}
      <div className="flex gap-2">
        <Button
          color="primary"
          variant="solid"
          size="sm"
          onClick={handleAdd}
          disabled={isAdding || !name.trim()}
        >
          {isAdding ? t('adding') : t('add')}
        </Button>
        <Button
          color="secondary"
          variant="ghost"
          size="sm"
          onClick={handleCancel}
          disabled={isAdding}
        >
          {t('cancel')}
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
