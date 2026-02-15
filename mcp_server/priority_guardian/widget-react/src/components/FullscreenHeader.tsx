import { Button } from '@openai/apps-sdk-ui/components/Button'

interface FullscreenHeaderProps {
  onMinimize: () => void
}

export function FullscreenHeader({ onMinimize }: FullscreenHeaderProps) {
  return (
    <div className="flex items-center justify-between mb-4">
      <h2 className="text-lg font-semibold text-default">My Priorities</h2>
      <Button
        color="secondary"
        variant="ghost"
        size="sm"
        onClick={onMinimize}
        aria-label="Minimize dashboard"
      >
        <svg className="w-4 h-4 mr-1" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M4 8h8" />
        </svg>
        Minimize
      </Button>
    </div>
  )
}
