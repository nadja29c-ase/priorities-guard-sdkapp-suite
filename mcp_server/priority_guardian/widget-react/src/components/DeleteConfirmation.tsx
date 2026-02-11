import { useEffect, useRef } from 'react'
import { Button } from '@openai/apps-sdk-ui/components/Button'

interface DeleteConfirmationProps {
  itemName: string
  itemType: 'priority' | 'deliverable'
  calendarKeyword?: string
  onConfirm: () => void
  onCancel: () => void
  isDeleting: boolean
}

export function DeleteConfirmation({
  itemName,
  itemType,
  calendarKeyword,
  onConfirm,
  onCancel,
  isDeleting,
}: DeleteConfirmationProps) {
  const cancelButtonRef = useRef<HTMLButtonElement>(null)

  // Auto-focus Cancel button on open (safe default)
  useEffect(() => {
    cancelButtonRef.current?.focus()
  }, [])

  // ESC key closes modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isDeleting) {
        onCancel()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onCancel, isDeleting])

  // Handle backdrop click
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget && !isDeleting) {
      onCancel()
    }
  }

  // Format message based on item type
  const title = itemType === 'priority' && calendarKeyword
    ? `Delete ${calendarKeyword}: ${itemName}?`
    : `Delete ${itemName}?`

  const subtitle = itemType === 'priority'
    ? 'This will also delete all deliverables. This cannot be undone.'
    : 'This cannot be undone.'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-dialog-title"
    >
      <div className="bg-surface rounded-2xl shadow-xl p-6 max-w-sm w-full mx-4">
        <h2 id="delete-dialog-title" className="text-lg font-semibold text-default mb-2">
          {title}
        </h2>
        <p className="text-sm text-secondary mb-6">
          {subtitle}
        </p>
        <div className="flex gap-3 justify-end">
          <Button
            ref={cancelButtonRef}
            color="secondary"
            variant="ghost"
            size="sm"
            onClick={onCancel}
            disabled={isDeleting}
          >
            Cancel
          </Button>
          <Button
            color="danger"
            variant="solid"
            size="sm"
            onClick={onConfirm}
            disabled={isDeleting}
            aria-label={`Confirm delete ${itemType}`}
          >
            {isDeleting ? 'Deleting...' : 'Delete'}
          </Button>
        </div>
      </div>
    </div>
  )
}
