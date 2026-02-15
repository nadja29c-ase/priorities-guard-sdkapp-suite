interface ExpandButtonProps {
  onClick: () => void
}

export function ExpandButton({ onClick }: ExpandButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full mt-4 py-2.5 rounded-xl text-xs font-medium flex items-center justify-center gap-1.5 transition-colors hover:opacity-80"
      style={{
        color: 'var(--gray-0, #ffffff)',
        background: 'var(--gray-900, #181818)',
        border: 'none',
        cursor: 'pointer',
      }}
      aria-label="Open full dashboard"
    >
      Open full dashboard
      <svg
        className="w-3 h-3"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      >
        <path d="M6 4l4 4-4 4" />
      </svg>
    </button>
  )
}
