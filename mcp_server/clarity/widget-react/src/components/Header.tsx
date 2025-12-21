import { Button } from '@openai/apps-sdk-ui/components/Button'

interface HeaderProps {
  canSave: boolean
  showSaved: boolean
  onSaveClick: () => void
}

export function Header({ canSave, showSaved, onSaveClick }: HeaderProps) {
  return (
    <div className="flex justify-between items-start mb-4">
      <div className="flex-1">
        <p className="heading-sm text-default mb-1">Clarity Board</p>
        <p className="text-sm text-secondary">
          Your thoughts grouped into clusters. Use the chat to rename, split, or reprioritize them.
        </p>
      </div>
      <div className="flex items-center gap-3 ml-4">
        {showSaved && (
          <span className="flex items-center gap-1 text-xs text-green-600 font-medium">
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z" />
            </svg>
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
