import type { RefObject } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { Button } from '@openai/apps-sdk-ui/components/Button'

interface SaveModalProps {
  isOpen: boolean
  onCancel: () => void
  onConfirm: () => void
  isSaving: boolean
  triggerRef?: RefObject<HTMLButtonElement | null>
}

export function SaveModal({ isOpen, onCancel, onConfirm, isSaving, triggerRef }: SaveModalProps) {
  if (!isOpen) return null

  const handleClose = () => {
    onCancel()
    // Restore focus to trigger button after modal closes
    // Use setTimeout to ensure DOM has updated
    setTimeout(() => {
      triggerRef?.current?.focus()
    }, 0)
  }

  return (
    <FocusTrap
      focusTrapOptions={{
        clickOutsideDeactivates: true,
        escapeDeactivates: true,
        onDeactivate: handleClose,
        // Prevent FocusTrap from calling onDeactivate when we manually close
        // since handleClose already handles focus restoration
        returnFocusOnDeactivate: false,
        // Fallback for testing environments where SDK Button may not be tabbable
        fallbackFocus: '[role="dialog"]',
      }}
    >
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
      >
        <div className="bg-surface rounded-xl p-6 max-w-[400px] w-[90%] shadow-xl">
          <h3 id="save-modal-title" className="heading-sm text-default mb-3">Save Board?</h3>
          <p id="save-modal-description" className="text-sm text-secondary mb-5">
            This will replace your previously saved board. Continue?
            <br />
            <span className="text-xs text-secondary">Note: you can have only 1 saved Clarity Board.</span>
          </p>
          <div className="flex gap-3 justify-end">
            <Button color="secondary" variant="outline" onClick={handleClose} disabled={isSaving} autoFocus>
              Cancel
            </Button>
            <Button color="primary" variant="solid" onClick={onConfirm} disabled={isSaving}>
              {isSaving ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </div>
      </div>
    </FocusTrap>
  )
}
