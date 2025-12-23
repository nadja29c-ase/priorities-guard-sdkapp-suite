import { useEffect, useRef, useCallback } from 'react'
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
  const dialogRef = useRef<HTMLDivElement>(null)
  const firstButtonRef = useRef<HTMLButtonElement>(null)
  const lastButtonRef = useRef<HTMLButtonElement>(null)

  const handleClose = useCallback(() => {
    onCancel()
    setTimeout(() => triggerRef?.current?.focus(), 0)
  }, [onCancel, triggerRef])

  // Global keydown handler to catch Tab before it escapes
  useEffect(() => {
    if (!isOpen) return

    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopPropagation()
        handleClose()
        return
      }

      if (e.key === 'Tab') {
        const first = firstButtonRef.current
        const last = lastButtonRef.current
        
        if (!first || !last) return

        if (e.shiftKey) {
          // Shift+Tab: if on first, go to last
          if (document.activeElement === first) {
            e.preventDefault()
            e.stopPropagation()
            last.focus()
          } else if (document.activeElement !== last) {
            // Not on any modal button, force to last
            e.preventDefault()
            e.stopPropagation()
            last.focus()
          }
        } else {
          // Tab: if on last, go to first
          if (document.activeElement === last) {
            e.preventDefault()
            e.stopPropagation()
            first.focus()
          } else if (document.activeElement !== first) {
            // Not on any modal button, force to first
            e.preventDefault()
            e.stopPropagation()
            first.focus()
          }
        }
      }
    }

    // Use capture phase to intercept before anything else
    document.addEventListener('keydown', handleGlobalKeyDown, true)
    
    // Focus first button when modal opens
    setTimeout(() => firstButtonRef.current?.focus(), 10)

    return () => {
      document.removeEventListener('keydown', handleGlobalKeyDown, true)
    }
  }, [isOpen, handleClose])

  if (!isOpen) return null

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="save-modal-title"
      aria-describedby="save-modal-description"
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
          <button
            ref={firstButtonRef}
            onClick={handleClose}
            disabled={isSaving}
            className="px-4 py-2 text-sm font-medium rounded-lg border border-default bg-surface text-default hover:bg-surface-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-ring)] disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            ref={lastButtonRef}
            onClick={onConfirm}
            disabled={isSaving}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-[var(--color-primary)] text-white hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-ring)] disabled:opacity-50"
          >
            {isSaving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
