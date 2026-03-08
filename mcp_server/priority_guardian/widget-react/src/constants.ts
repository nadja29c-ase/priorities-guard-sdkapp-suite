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

// Circle badge dimensions (use with rounded-full) - V7: w-6 h-6
export const BADGE_CIRCLE_CLASS = 'w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold flex-shrink-0'

// Bar segment and legend dot colors for TimeAllocationBar (Widget C)
// Uses solid midtone tokens for better visibility on 12px height bar
// P1: info (blue), P2: discovery (purple), P3: caution (yellow), other: visible neutral gray
export const BAR_COLORS: Record<string, string> = {
  P1: 'bg-info-solid',
  P2: 'bg-discovery-solid',
  P3: 'bg-caution-solid',
  other: 'bg-[var(--gray-500)]',
}

// SVG stroke colors for HourRing (Widget C+) — CSS custom properties from SDK tokens
// These are the same colors as BAR_COLORS but as CSS variable references for SVG stroke
export const RING_STROKE_COLORS: Record<string, string> = {
  P1: 'var(--color-background-info-solid, var(--blue-400, #0285ff))',
  P2: 'var(--color-background-discovery-solid, var(--purple-400, #924ff7))',
  P3: 'var(--color-background-caution-solid, var(--yellow-400, #ffc300))',
}

// Card left border colors (Widget D) — 4px left border for visual hierarchy
// Uses solid colors for visibility: P1 blue, P2 purple, P3 yellow
export const BORDER_COLORS: Record<string, string> = {
  P1: 'border-l-4 border-l-[var(--color-background-info-solid,#0285ff)]',
  P2: 'border-l-4 border-l-[var(--color-background-discovery-solid,#924ff7)]',
  P3: 'border-l-4 border-l-[var(--color-background-caution-solid,#ffc300)]',
}
