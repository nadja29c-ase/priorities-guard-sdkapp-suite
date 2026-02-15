interface FullscreenHeaderProps {
  onMinimize: () => void
}

export function FullscreenHeader({ onMinimize }: FullscreenHeaderProps) {
  return (
    <div className="flex items-center justify-between px-4 py-3 mb-4 rounded-xl bg-surface border border-default">
      <span className="text-sm font-semibold text-default">
        My Priorities
      </span>
      <button
        type="button"
        onClick={onMinimize}
        className="text-xs px-2.5 py-1 rounded-lg transition-colors hover:bg-surface-secondary text-secondary"
        title="Minimize to inline card"
        aria-label="Minimize dashboard"
      >
        Minimize
      </button>
    </div>
  )
}
