/**
 * Rotatable chevron icon for collapsible sections (V7 style).
 * Points down by default, rotates 180deg to point up when expanded.
 *
 * Copied verbatim from ChatGPT widget.
 */

interface ChevronIconProps {
  expanded: boolean
  className?: string
}

export function ChevronIcon({ expanded, className = '' }: ChevronIconProps) {
  return (
    <svg
      className={className}
      style={{
        width: '14px',
        height: '14px',
        transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
        transition: 'transform 150ms ease-out',
      }}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M4 6l4 4 4-4" />
    </svg>
  )
}
