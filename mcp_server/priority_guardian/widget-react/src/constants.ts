/**
 * Shared constants for Priority Guardian Widget.
 */

// Badge colors using SDK primitive tokens (no semantic meaning)
// P1: blue, P2: purple, P3: teal - neutral visual distinction only
export const BADGE_COLORS: Record<string, string> = {
  P1: 'bg-[var(--blue-400)] text-white',
  P2: 'bg-[var(--purple-400)] text-white',
  P3: 'bg-[var(--green-400)] text-white',
}

// Circle badge dimensions (use with rounded-full)
export const BADGE_CIRCLE_CLASS = 'w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold flex-shrink-0'
