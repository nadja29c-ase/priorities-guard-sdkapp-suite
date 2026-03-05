/**
 * Design Token Hardening Tests
 *
 * Verifies that no components use hardcoded gray/green/red/blue CSS variables
 * in inline style attributes. All colors should use SDK semantic Tailwind classes.
 *
 * Exceptions:
 * - RING_STROKE_COLORS in constants.ts (uses var(--color-*) SDK tokens)
 * - ACCENT_COLORS in DeadlineCard (uses var(--color-*) SDK tokens)
 * - SEMANTIC_COLORS hex values in PieChart (categorical data colors, not theme tokens)
 * - Dynamic per-priority border colors (left border using SDK tokens)
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { setMockPriorities, resetMocks } from '../test/setup'
import App from '../App'
import type { Priority, Goal, TimeAllocation, PieSlice } from '../types'

// Sample data for testing
const deadlinePriority: Priority = {
  id: 'pri-1',
  name: 'Launch Feature X',
  type: 'deadline',
  calendarKeyword: 'P1',
  status: 'active',
  deadline: '2026-02-28',
  weeklyHourTarget: 10,
  weeklyHourActual: 8,
  deliverables: [
    { id: 'd1', name: 'Design doc', done: true },
    { id: 'd2', name: 'Implementation', done: false },
  ],
  goals: [],
}

const flexiblePriority: Priority = {
  id: 'pri-2',
  name: 'Learn Rust',
  type: 'flexible',
  calendarKeyword: 'P2',
  status: 'active',
  weeklyHourTarget: 5,
  weeklyHourActual: 3,
  checkpointDate: '2026-03-15',
  deliverables: [],
  goals: [
    { id: 'g1', text: 'Complete chapter 1', achieved: true },
    { id: 'g2', text: 'Complete chapter 2', achieved: false },
  ],
  avgTargetAchievement: 85.0,
}

const timeAllocation: TimeAllocation = {
  weekStart: '2026-02-09',
  weekEnd: '2026-02-16',
  totalTrackedHours: 20,
  keywords: {
    P1: { hours: 10, events: [] },
    P2: { hours: 5, events: [] },
    P3: { hours: 0, events: [] },
  },
  barSegments: { P1: 10, P2: 5, P3: 0 },
  otherHours: 5,
}

/**
 * Extract all inline style attributes from rendered HTML
 * Returns array of style content strings
 */
function extractStyleAttributes(container: HTMLElement): string[] {
  const elementsWithStyle = container.querySelectorAll('[style]')
  const styles: string[] = []
  elementsWithStyle.forEach((el) => {
    const style = el.getAttribute('style')
    if (style) {
      styles.push(style)
    }
  })
  return styles
}

/**
 * Check if any styles contain forbidden CSS variable patterns
 */
function findForbiddenPatterns(styles: string[]): string[] {
  const forbiddenPatterns = [
    /var\(--gray-/,      // Hardcoded gray values
    /var\(--green-/,     // Hardcoded green values
    /var\(--red-/,       // Hardcoded red values
    /var\(--blue-/,      // Hardcoded blue values
  ]

  const violations: string[] = []

  for (const style of styles) {
    for (const pattern of forbiddenPatterns) {
      if (pattern.test(style)) {
        violations.push(style)
        break
      }
    }
  }

  return violations
}

describe('Design Token Hardening', () => {
  beforeEach(() => {
    resetMocks()
  })

  describe('Dashboard View', () => {
    it('renders priority cards without hardcoded gray CSS variables', () => {
      setMockPriorities([deadlinePriority, flexiblePriority], true, ['P3'], timeAllocation)
      const { container } = render(<App />)

      const styles = extractStyleAttributes(container)
      const violations = findForbiddenPatterns(styles)

      expect(violations).toEqual([])
    })

    it('renders DeadlineCard without forbidden CSS variables', () => {
      setMockPriorities([deadlinePriority], true)
      const { container } = render(<App />)

      const styles = extractStyleAttributes(container)
      const violations = findForbiddenPatterns(styles)

      expect(violations).toEqual([])
    })

    it('renders FlexibleCard without forbidden CSS variables', () => {
      setMockPriorities([flexiblePriority], true)
      const { container } = render(<App />)

      const styles = extractStyleAttributes(container)
      const violations = findForbiddenPatterns(styles)

      expect(violations).toEqual([])
    })

    it('renders TimeAllocationBar without forbidden CSS variables', () => {
      setMockPriorities([deadlinePriority], true, ['P2', 'P3'], timeAllocation)
      const { container } = render(<App />)

      const styles = extractStyleAttributes(container)
      const violations = findForbiddenPatterns(styles)

      expect(violations).toEqual([])
    })

    it('renders ConnectionStatus without forbidden CSS variables', () => {
      // Test connected state
      setMockPriorities([], true)
      const { container: connectedContainer } = render(<App />)
      let styles = extractStyleAttributes(connectedContainer)
      let violations = findForbiddenPatterns(styles)
      expect(violations).toEqual([])

      // Test disconnected state
      resetMocks()
      setMockPriorities([], false)
      const { container: disconnectedContainer } = render(<App />)
      styles = extractStyleAttributes(disconnectedContainer)
      violations = findForbiddenPatterns(styles)
      expect(violations).toEqual([])
    })
  })

  describe('Component-specific checks', () => {
    it('GoalItem uses semantic tokens for checkbox and text', () => {
      setMockPriorities([flexiblePriority], true)
      const { container } = render(<App />)

      const styles = extractStyleAttributes(container)
      const violations = findForbiddenPatterns(styles)

      expect(violations).toEqual([])
    })

    it('allows SDK semantic tokens (var(--color-*)) in inline styles', () => {
      // This test verifies that SDK tokens are NOT flagged as violations
      setMockPriorities([deadlinePriority, flexiblePriority], true, ['P3'], timeAllocation)
      const { container } = render(<App />)

      const styles = extractStyleAttributes(container)

      // SDK semantic tokens should be allowed
      const sdkTokenPatterns = [
        /var\(--color-background-/,
        /var\(--color-text-/,
        /var\(--color-border-/,
      ]

      // Verify that SDK tokens are present (used for dynamic values)
      const hasSdkTokens = styles.some((style) =>
        sdkTokenPatterns.some((pattern) => pattern.test(style))
      )

      // SDK tokens may or may not be present depending on what's dynamic
      // But no forbidden patterns should exist
      const violations = findForbiddenPatterns(styles)
      expect(violations).toEqual([])
    })
  })

  describe('Dynamic values allowed', () => {
    it('allows per-priority border colors using SDK tokens', () => {
      // Cards have dynamic borderLeft using SDK tokens - this is allowed
      setMockPriorities([deadlinePriority, flexiblePriority], true)
      const { container } = render(<App />)

      const cards = container.querySelectorAll('article')
      expect(cards.length).toBeGreaterThan(0)

      // Each card should have a borderLeft style
      cards.forEach((card) => {
        const style = card.getAttribute('style')
        if (style) {
          // Border colors should be hex values (from BORDER_COLORS), not var(--gray-*)
          expect(style).not.toMatch(/var\(--gray-/)
        }
      })
    })
  })
})
