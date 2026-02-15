/**
 * Rotatable chevron icon for collapsible sections.
 */

interface ChevronIconProps {
  expanded: boolean
  className?: string
}

export function ChevronIcon({ expanded, className = '' }: ChevronIconProps) {
  return (
    <svg
      className={`w-4 h-4 transition-transform duration-200 ${expanded ? 'rotate-90' : ''} ${className}`}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M6 4l4 4-4 4" />
    </svg>
  )
}
