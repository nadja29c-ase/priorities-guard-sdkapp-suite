import { useEffect, useRef } from 'react'
import { Button } from '@openai/apps-sdk-ui/components/Button'
import { t } from '../i18n'

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
  const modalRef = useRef<HTMLDivElement>(null)

  // Auto-focus Cancel button on open (safe default)
  useEffect(() => {
    // Find the Cancel button within the modal and focus it
    const cancelButton = modalRef.current?.querySelector<HTMLButtonElement>('[data-color="secondary"]')
    cancelButton?.focus()
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

  // Focus trap — Tab/Shift+Tab stay within modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return
      if (!modalRef.current) return
      if (!modalRef.current.contains(document.activeElement)) return

      // Query all focusable elements
      const focusableSelector = 'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      const allFocusable = modalRef.current.querySelectorAll<HTMLElement>(focusableSelector)

      // Filter to visible elements only
      const focusable = Array.from(allFocusable).filter(el => el.offsetParent !== null)
      if (focusable.length === 0) return

      const first = focusable[0]
      const last = focusable[focusable.length - 1]

      if (e.shiftKey && document.activeElement === first) {
        // Shift+Tab on first → wrap to last
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        // Tab on last → wrap to first
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Handle backdrop click
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget && !isDeleting) {
      onCancel()
    }
  }

  // Format message based on item type
  const title = itemType === 'priority' && calendarKeyword
    ? t('deleteWithKeyword').replace('{keyword}', calendarKeyword).replace('{name}', itemName)
    : t('deleteItem').replace('{name}', itemName)

  const subtitle = itemType === 'priority'
    ? t('deleteSubtitlePriority')
    : t('deleteSubtitleDeliverable')

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-dialog-title"
    >
      <div ref={modalRef} className="bg-surface rounded-2xl shadow-xl p-6 max-w-sm w-full mx-4">
        <h2 id="delete-dialog-title" className="text-lg font-semibold text-default mb-2">
          {title}
        </h2>
        <p className="text-sm text-secondary mb-6">
          {subtitle}
        </p>
        <div className="flex gap-3 justify-end">
          <Button
            color="secondary"
            variant="ghost"
            size="sm"
            onClick={onCancel}
            disabled={isDeleting}
          >
            {t('cancel')}
          </Button>
          <Button
            color="danger"
            variant="solid"
            size="sm"
            onClick={onConfirm}
            disabled={isDeleting}
            aria-label={t('confirmDeleteType').replace('{type}', itemType)}
          >
            {isDeleting ? t('deleting') : t('delete')}
          </Button>
        </div>
      </div>
    </div>
  )
}
