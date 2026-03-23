/**
 * Shared constants for Priority Guardian Claude Widget.
 *
 * CSS variables use host tokens with fallback values.
 * useHostStyles(app) injects host CSS variables but token names may differ.
 */

// Badge colors - inline styles with fallbacks (no Tailwind in Claude widget)
export const BADGE_COLORS: Record<string, { bg: string; text: string }> = {
  P1: { bg: 'rgba(2, 133, 255, 0.12)', text: '#0285ff' },
  P2: { bg: 'rgba(146, 79, 247, 0.12)', text: '#924ff7' },
  P3: { bg: 'rgba(255, 195, 0, 0.12)', text: '#e0ac00' },
}

// Bar segment colors for TimeAllocationBar
export const BAR_COLORS: Record<string, string> = {
  P1: '#0285ff',
  P2: '#924ff7',
  P3: '#ffc300',
  other: 'var(--color-background-secondary, #e5e5e5)',
}

// SVG stroke colors for HourRing
export const RING_STROKE_COLORS: Record<string, string> = {
  P1: '#0285ff',
  P2: '#924ff7',
  P3: '#ffc300',
}

// Card left border colors
export const BORDER_COLORS: Record<string, string> = {
  P1: '#0285ff',
  P2: '#924ff7',
  P3: '#ffc300',
}

// Icon stroke colors (calendar icon in deadline banner)
export const ICON_STROKE_COLORS: Record<string, string> = {
  P1: '#0285ff',
  P2: '#924ff7',
  P3: '#e0ac00',
}
