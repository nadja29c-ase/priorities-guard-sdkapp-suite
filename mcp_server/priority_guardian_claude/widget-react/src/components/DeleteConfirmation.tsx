import { useEffect, useRef } from 'react'
import { Button } from './Button'
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
    ? t('deleteWithKeyword', { keyword: calendarKeyword, name: itemName })
    : t('deleteItem', { name: itemName })

  const subtitle = itemType === 'priority'
    ? t('deleteSubtitlePriority')
    : t('deleteSubtitleDeliverable')

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 50,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0, 0, 0, 0.5)',
      }}
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-dialog-title"
      aria-describedby="delete-dialog-description"
    >
      <div
        ref={modalRef}
        style={{
          background: 'var(--color-background-primary, #fff)',
          borderRadius: '16px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          padding: '24px',
          maxWidth: '384px',
          width: '100%',
          margin: '0 16px',
        }}
      >
        <h2
          id="delete-dialog-title"
          style={{
            fontSize: '18px',
            fontWeight: 600,
            color: 'var(--color-text-primary, #0d0d0d)',
            marginBottom: '8px',
          }}
        >
          {title}
        </h2>
        <p
          id="delete-dialog-description"
          style={{
            fontSize: '14px',
            color: 'var(--color-text-secondary, #737373)',
            marginBottom: '24px',
          }}
        >
          {subtitle}
        </p>
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
          <Button
            color="secondary"
            variant="ghost"
            size="sm"
            onClick={onCancel}
            disabled={isDeleting}
            data-color="secondary"
          >
            {t('cancel')}
          </Button>
          <Button
            color="danger"
            variant="solid"
            size="sm"
            onClick={onConfirm}
            disabled={isDeleting}
            aria-label={t('confirmDeleteType', { type: itemType })}
          >
            {isDeleting ? t('deleting') : t('delete')}
          </Button>
        </div>
      </div>
    </div>
  )
}
