import { useState, useRef, useEffect } from 'react'
import { Button } from './Button'
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
  const [isHovered, setIsHovered] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isOpen])

  const errorId = `deliverable-error-${priorityId}`

  const handleAdd = async () => {
    if (isAdding || disabled) return
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
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        disabled={disabled}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
          fontSize: '12px',
          color: isHovered ? 'var(--color-text-primary, #0d0d0d)' : 'var(--color-text-secondary, #737373)',
          opacity: disabled ? 0.5 : 1,
          background: 'none',
          border: 'none',
          cursor: disabled ? 'not-allowed' : 'pointer',
          padding: 0,
        }}
        aria-label={t('addDeliverable')}
      >
        <svg style={{ width: '14px', height: '14px' }} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <path d="M8 3v10M3 8h10"/>
        </svg>
        {t('addDeliverable')}
      </button>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
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
        style={{
          width: '100%',
          fontSize: '14px',
          color: 'var(--color-text-primary, #0d0d0d)',
          background: 'var(--color-background-primary, #fff)',
          border: '1px solid var(--color-border, #e5e5e5)',
          borderRadius: '8px',
          padding: '8px 12px',
          outline: 'none',
        }}
        aria-label={t('deliverableNamePlaceholder')}
        aria-describedby={error ? errorId : undefined}
      />
      {/* Row 2: Add + Cancel buttons */}
      <div style={{ display: 'flex', gap: '8px' }}>
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
        <p
          id={errorId}
          style={{
            fontSize: '12px',
            color: 'var(--color-text-danger, #dc2626)',
          }}
          role="alert"
        >
          {error}
        </p>
      )}
    </div>
  )
}
