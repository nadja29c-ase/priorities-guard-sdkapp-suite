import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'
import { Button } from '@openai/apps-sdk-ui/components/Button'

interface SaveModalProps {
  isOpen: boolean
  onCancel: () => void
  onConfirm: () => void
  isSaving: boolean
  triggerRef?: RefObject<HTMLButtonElement | null>
}

export function SaveModal({ isOpen, onCancel, onConfirm, isSaving, triggerRef }: SaveModalProps) {
  const cancelRef = useRef<HTMLButtonElement>(null)
  const saveRef = useRef<HTMLButtonElement>(null)

  // Focus Cancel button when modal opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => cancelRef.current?.focus(), 0)
    }
  }, [isOpen])

  if (!isOpen) return null

  const handleClose = () => {
    onCancel()
    setTimeout(() => triggerRef?.current?.focus(), 0)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      handleClose()
      return
    }

    if (e.key === 'Tab') {
      const focusables = [cancelRef.current, saveRef.current].filter(Boolean) as HTMLElement[]
      const first = focusables[0]
      const last = focusables[focusables.length - 1]

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      } else if (!focusables.includes(document.activeElement as HTMLElement)) {
        // Focus escaped somehow, bring it back
        e.preventDefault()
        first.focus()
      }
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="save-modal-title"
      aria-describedby="save-modal-description"
      tabIndex={-1}
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center"
      onClick={(e) => {
        if (e.target === e.currentTarget) handleClose()
      }}
      onKeyDown={handleKeyDown}
    >
      <div className="bg-surface rounded-xl p-6 max-w-[400px] w-[90%] shadow-xl">
        <h3 id="save-modal-title" className="heading-sm text-default mb-3">Save Board?</h3>
        <p id="save-modal-description" className="text-sm text-secondary mb-5">
          This will replace your previously saved board. Continue?
          <br />
          <span className="text-xs text-secondary">Note: you can have only 1 saved Clarity Board.</span>
        </p>
        <div className="flex gap-3 justify-end">
          <Button ref={cancelRef} color="secondary" variant="outline" onClick={handleClose} disabled={isSaving}>
            Cancel
          </Button>
          <Button ref={saveRef} color="primary" variant="solid" onClick={onConfirm} disabled={isSaving}>
            {isSaving ? 'Saving...' : 'Save'}
          </Button>
        </div>
      </div>
    </div>
  )
}
