import { Button } from '@openai/apps-sdk-ui/components/Button'

interface DeleteConfirmationProps {
  itemName: string
  itemType: 'priority' | 'deliverable'
  onConfirm: () => void
  onCancel: () => void
  isDeleting: boolean
}

export function DeleteConfirmation({
  itemName,
  itemType,
  onConfirm,
  onCancel,
  isDeleting,
}: DeleteConfirmationProps) {
  return (
    <div
      className="p-3 bg-surface-secondary rounded-lg border border-danger-outline"
      role="alertdialog"
      aria-label={`Delete ${itemType} confirmation`}
      aria-live="polite"
    >
      <p className="text-sm text-default mb-3">
        Delete <strong>{itemName}</strong>?
        {itemType === 'priority' && ' This will also delete all deliverables.'}
        {' '}This cannot be undone.
      </p>
      <div className="flex gap-2">
        <Button
          color="danger"
          variant="outline"
          size="sm"
          onClick={onConfirm}
          disabled={isDeleting}
          aria-label={`Confirm delete ${itemType}`}
        >
          {isDeleting ? 'Deleting...' : 'Delete'}
        </Button>
        <Button
          color="secondary"
          variant="ghost"
          size="sm"
          onClick={onCancel}
          disabled={isDeleting}
        >
          Cancel
        </Button>
      </div>
    </div>
  )
}
