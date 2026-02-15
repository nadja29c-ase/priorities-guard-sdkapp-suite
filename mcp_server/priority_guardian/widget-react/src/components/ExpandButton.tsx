interface ExpandButtonProps {
  onClick: () => void
}

export function ExpandButton({ onClick }: ExpandButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full mt-4 p-3 border border-default rounded-xl hover:border-strong hover:bg-surface-secondary/50 transition-colors flex items-center justify-center gap-2 text-secondary hover:text-default"
      aria-label="Open full dashboard"
    >
      <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M10 2h4v4M6 14H2v-4M14 2L9 7M2 14l5-5" />
      </svg>
      <span className="text-sm font-medium">Open full dashboard</span>
    </button>
  )
}
