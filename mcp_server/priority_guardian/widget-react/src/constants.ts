/**
 * Shared constants for Priority Guardian Widget.
 */

// Badge colors using neutral SDK semantic tokens (theme-adaptive)
// P1: info (blue), P2: discovery (purple), P3: caution (yellow)
export const BADGE_COLORS: Record<string, string> = {
  P1: 'bg-info-soft-alpha text-info',
  P2: 'bg-discovery-soft-alpha text-discovery',
  P3: 'bg-caution-soft-alpha text-caution',
}

// Circle badge dimensions (use with rounded-full)
export const BADGE_CIRCLE_CLASS = 'w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold flex-shrink-0'

// Bar segment and legend dot colors for TimeAllocationBar (Widget C)
// Uses solid midtone tokens for better visibility on 12px height bar
// P1: info (blue), P2: discovery (purple), P3: caution (yellow), other: neutral gray
export const BAR_COLORS: Record<string, string> = {
  P1: 'bg-info-solid',
  P2: 'bg-discovery-solid',
  P3: 'bg-caution-solid',
  other: 'bg-surface-tertiary',
}
