import { Button } from '@openai/apps-sdk-ui/components/Button'
import { Check } from '@openai/apps-sdk-ui/components/Icon'

interface HeaderProps {
  canSave: boolean
  showSaved: boolean
  onSaveClick: () => void
}

export function Header({ canSave, showSaved, onSaveClick }: HeaderProps) {
  return (
    <div className="flex justify-between items-center mb-6">
      <div className="flex-1">
        <p className="heading-sm text-default mb-1">Your Clarity Board</p>
        <p className="text-sm text-secondary">
          Your thoughts grouped into clusters. Use the chat to rename, split, or reprioritize them.
        </p>
      </div>
      <div className="flex items-center gap-3 ml-4">
        {showSaved && (
          <span
            className="flex items-center gap-1 text-xs text-success font-medium"
            aria-live="polite"
          >
            <Check className="w-3.5 h-3.5" />
            Saved
          </span>
        )}
        <Button
          color="primary"
          variant="solid"
          onClick={onSaveClick}
          disabled={!canSave}
        >
          Save
        </Button>
      </div>
    </div>
  )
}
