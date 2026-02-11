/**
 * Shared constants for Priority Guardian Widget.
 */

// Badge colors using SDK semantic tokens
// P1: info (blue), P2: discovery (purple), P3: warning (yellow/orange)
export const BADGE_COLORS: Record<string, string> = {
  P1: 'bg-info-soft-alpha text-info',
  P2: 'bg-discovery-soft-alpha text-discovery',
  P3: 'bg-warning-soft-alpha text-warning',
}

// Circle badge dimensions (use with rounded-full)
export const BADGE_CIRCLE_CLASS = 'w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold flex-shrink-0'
