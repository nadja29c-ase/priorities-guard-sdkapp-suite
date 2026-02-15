interface FullscreenHeaderProps {
  onMinimize: () => void
}

export function FullscreenHeader({ onMinimize }: FullscreenHeaderProps) {
  return (
    <div
      className="flex items-center justify-between px-4 py-3 mb-4 rounded-xl"
      style={{
        background: 'var(--gray-0, #ffffff)',
        border: '1px solid var(--gray-100, #ededed)',
      }}
    >
      <span
        className="text-sm font-semibold"
        style={{ color: 'var(--gray-900, #181818)' }}
      >
        My Priorities
      </span>
      <button
        onClick={onMinimize}
        className="text-xs px-2.5 py-1 rounded-lg transition-colors hover:bg-surface-secondary"
        style={{
          color: 'var(--gray-500, #5d5d5d)',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
        }}
        title="Minimize to inline card"
        aria-label="Minimize dashboard"
      >
        Minimize
      </button>
    </div>
  )
}
