/**
 * Rotatable chevron icon for collapsible sections (V7 style).
 * Points down by default, rotates 180deg to point up when expanded.
 */

interface ChevronIconProps {
  expanded: boolean
  className?: string
}

export function ChevronIcon({ expanded, className = '' }: ChevronIconProps) {
  return (
    <svg
      className={`w-3.5 h-3.5 ${className}`}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      style={{
        transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
        transition: 'transform 150ms ease-out',
      }}
    >
      <path d="M4 6l4 4 4-4" />
    </svg>
  )
}
