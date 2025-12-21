import { Button } from '@openai/apps-sdk-ui/components/Button'

interface SaveModalProps {
  isOpen: boolean
  onCancel: () => void
  onConfirm: () => void
  isSaving: boolean
}

export function SaveModal({ isOpen, onCancel, onConfirm, isSaving }: SaveModalProps) {
  if (!isOpen) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="save-modal-title"
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel()
      }}
    >
      <div className="bg-surface rounded-xl p-6 max-w-[400px] w-[90%] shadow-xl">
        <h3 id="save-modal-title" className="heading-sm text-default mb-3">Save Board?</h3>
        <p className="text-sm text-secondary mb-5">
          This will replace your previously saved board. Continue?
          <br />
          <span className="text-xs text-secondary">Note: you can have only 1 saved Clarity Board.</span>
        </p>
        <div className="flex gap-3 justify-end">
          <Button color="secondary" variant="outline" onClick={onCancel} disabled={isSaving}>
            Cancel
          </Button>
          <Button color="primary" variant="solid" onClick={onConfirm} disabled={isSaving}>
            {isSaving ? 'Saving...' : 'Save'}
          </Button>
        </div>
      </div>
    </div>
  )
}
