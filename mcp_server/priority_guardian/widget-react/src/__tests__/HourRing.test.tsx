/**
 * Unit tests for HourRing component (Widget Increment C+)
 *
 * Tests:
 * - Renders SVG with track circle and progress circle
 * - Shows formatted actual and target hours
 * - Uses correct stroke colors for P1/P2/P3
 * - Progress calculation (0%, 50%, 100%, over-target)
 * - Edge cases (0 actual, small values)
 * - Accessibility
 * - FlexibleCard integration
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { HourRing } from '../components/HourRing'
import { FlexibleCard } from '../components/FlexibleCard'
import type { Priority } from '../types'

// Ring geometry constants (must match component)
const RADIUS = 26
const CIRCUMFERENCE = 2 * Math.PI * RADIUS  // ~163.36

describe('HourRing', () => {
  describe('Rendering', () => {
    it('renders SVG with track and progress circles', () => {
      render(<HourRing actual={2.5} target={5} keyword="P1" />)

      const svg = document.querySelector('svg')
      expect(svg).toBeInTheDocument()

      // Should have two circles: track + progress
      const circles = document.querySelectorAll('circle')
      expect(circles.length).toBe(2)
    })

    it('shows formatted actual hours in center', () => {
      render(<HourRing actual={2} target={5} keyword="P1" />)
      expect(screen.getByText('2h')).toBeInTheDocument()
    })

    it('shows formatted target hours', () => {
      render(<HourRing actual={2} target={5} keyword="P1" />)
      expect(screen.getByText(/\/ 5h/)).toBeInTheDocument()
    })

    it('formats hours without unnecessary decimals', () => {
      render(<HourRing actual={3.0} target={10.0} keyword="P1" />)
      expect(screen.getByText('3h')).toBeInTheDocument()
      expect(screen.getByText(/\/ 10h/)).toBeInTheDocument()
    })

    it('formats hours with one decimal when needed', () => {
      render(<HourRing actual={3.25} target={5} keyword="P1" />)
      // 3.25 rounds to 3.3
      expect(screen.getByText('3.3h')).toBeInTheDocument()
    })
  })

  describe('Stroke Colors', () => {
    it('uses info blue for P1', () => {
      render(<HourRing actual={2} target={5} keyword="P1" />)

      const progressCircle = document.querySelectorAll('circle')[1]
      expect(progressCircle).toHaveAttribute(
        'stroke',
        expect.stringContaining('info-solid')
      )
    })

    it('uses discovery purple for P2', () => {
      render(<HourRing actual={2} target={5} keyword="P2" />)

      const progressCircle = document.querySelectorAll('circle')[1]
      expect(progressCircle).toHaveAttribute(
        'stroke',
        expect.stringContaining('discovery-solid')
      )
    })

    it('uses caution amber for P3', () => {
      render(<HourRing actual={2} target={5} keyword="P3" />)

      const progressCircle = document.querySelectorAll('circle')[1]
      expect(progressCircle).toHaveAttribute(
        'stroke',
        expect.stringContaining('caution-solid')
      )
    })

    it('track uses border-subtle color', () => {
      render(<HourRing actual={2} target={5} keyword="P1" />)

      const trackCircle = document.querySelectorAll('circle')[0]
      expect(trackCircle).toHaveAttribute(
        'stroke',
        'var(--color-border-subtle)'
      )
    })
  })

  describe('Progress Calculation', () => {
    it('renders 0% when actual is 0', () => {
      render(<HourRing actual={0} target={5} keyword="P1" />)

      // With 0%, there should be no progress circle (only track)
      const circles = document.querySelectorAll('circle')
      expect(circles.length).toBe(1)  // Only track circle
    })

    it('renders 50% progress arc', () => {
      render(<HourRing actual={2.5} target={5} keyword="P1" />)

      const progressCircle = document.querySelectorAll('circle')[1]
      const dashoffset = progressCircle.getAttribute('stroke-dashoffset')

      // 50% means dashoffset = circumference / 2
      const expectedOffset = CIRCUMFERENCE / 2
      expect(parseFloat(dashoffset!)).toBeCloseTo(expectedOffset, 1)
    })

    it('renders 100% progress arc', () => {
      render(<HourRing actual={5} target={5} keyword="P1" />)

      const progressCircle = document.querySelectorAll('circle')[1]
      const dashoffset = progressCircle.getAttribute('stroke-dashoffset')

      // 100% means dashoffset = 0
      expect(parseFloat(dashoffset!)).toBeCloseTo(0, 1)
    })

    it('caps at 100% when actual exceeds target', () => {
      render(<HourRing actual={7} target={5} keyword="P1" />)

      const progressCircle = document.querySelectorAll('circle')[1]
      const dashoffset = progressCircle.getAttribute('stroke-dashoffset')

      // Over-target still capped at 100% (dashoffset = 0)
      expect(parseFloat(dashoffset!)).toBeCloseTo(0, 1)
    })

    it('shows actual hours even when over target', () => {
      render(<HourRing actual={7} target={5} keyword="P1" />)

      // Should display "7h" not "5h"
      expect(screen.getByText('7h')).toBeInTheDocument()
      expect(screen.getByText(/\/ 5h/)).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('renders with 0 actual (empty track only)', () => {
      render(<HourRing actual={0} target={5} keyword="P1" />)

      expect(screen.getByText('0h')).toBeInTheDocument()
      expect(screen.getByText(/\/ 5h/)).toBeInTheDocument()

      // Only track circle, no progress arc
      const circles = document.querySelectorAll('circle')
      expect(circles.length).toBe(1)
    })

    it('handles very small actual values', () => {
      render(<HourRing actual={0.1} target={10} keyword="P1" />)

      // 0.1 rounds to 0.1
      expect(screen.getByText('0.1h')).toBeInTheDocument()

      // Progress circle should exist (1% progress)
      const circles = document.querySelectorAll('circle')
      expect(circles.length).toBe(2)
    })

    it('handles small target values', () => {
      render(<HourRing actual={0.25} target={0.5} keyword="P1" />)

      // 0.25 rounds to 0.3, 0.5 stays as 0.5
      expect(screen.getByText('0.3h')).toBeInTheDocument()
      expect(screen.getByText(/\/ 0\.5h/)).toBeInTheDocument()
    })

    it('handles large values', () => {
      render(<HourRing actual={45} target={40} keyword="P1" />)

      expect(screen.getByText('45h')).toBeInTheDocument()
      expect(screen.getByText(/\/ 40h/)).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has role="img" on SVG', () => {
      render(<HourRing actual={2} target={5} keyword="P1" />)

      const svg = document.querySelector('svg')
      expect(svg).toHaveAttribute('role', 'img')
    })

    it('has descriptive aria-label', () => {
      render(<HourRing actual={2} target={5} keyword="P1" />)

      const svg = document.querySelector('svg')
      const ariaLabel = svg?.getAttribute('aria-label')

      // Increment 61: accessibility labels use full "hours" word for VoiceOver
      expect(ariaLabel).toContain('2 hours')
      expect(ariaLabel).toContain('5 hours')
      expect(ariaLabel).toContain('week')
    })

    it('aria-label reflects actual values', () => {
      render(<HourRing actual={3.5} target={10} keyword="P2" />)

      const svg = document.querySelector('svg')
      const ariaLabel = svg?.getAttribute('aria-label')

      // Increment 61: accessibility labels use full "hours" word for VoiceOver
      expect(ariaLabel).toContain('3.5 hours')
      expect(ariaLabel).toContain('10 hours')
    })
  })
})

// FlexibleCard integration tests
describe('FlexibleCard + HourRing Integration', () => {
  const basePriority: Priority = {
    id: 'test-flex-1',
    name: 'Learn Rust',
    type: 'flexible',
    calendarKeyword: 'P2',
    status: 'active',
    deliverables: [],
    goals: [],
  }

  const mockHandlers = {
    onStartEdit: vi.fn(),
    onCancelEdit: vi.fn(),
    onSave: vi.fn().mockResolvedValue(undefined),
    onDelete: vi.fn().mockResolvedValue(undefined),
    onKeywordChange: vi.fn().mockResolvedValue(undefined),
    onAddGoal: vi.fn().mockResolvedValue(undefined),
    onToggleGoal: vi.fn().mockResolvedValue(undefined),
    onRenameGoal: vi.fn().mockResolvedValue(undefined),
    onDeleteGoal: vi.fn().mockResolvedValue(undefined),
    priorities: [],
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders HourRing when weeklyHourTarget is set', () => {
    const priority: Priority = {
      ...basePriority,
      weeklyHourTarget: 10,
    }

    render(
      <FlexibleCard
        priority={priority}
        isEditing={false}
        {...mockHandlers}
      />
    )

    // HourRing should be present with target hours
    expect(screen.getByText(/\/ 10h/)).toBeInTheDocument()

    // SVG ring should be present in header right column
    const svg = document.querySelector('svg[role="img"]')
    expect(svg).toBeInTheDocument()
  })

  it('does NOT render HourRing when weeklyHourTarget is null', () => {
    const priority: Priority = {
      ...basePriority,
      weeklyHourTarget: undefined,
    }

    render(
      <FlexibleCard
        priority={priority}
        isEditing={false}
        {...mockHandlers}
      />
    )

    // No SVG ring (only delete button in right column)
    const svg = document.querySelector('svg[role="img"]')
    expect(svg).not.toBeInTheDocument()
  })

  it('passes weeklyHourActual ?? 0 when actual is null', () => {
    const priority: Priority = {
      ...basePriority,
      weeklyHourTarget: 5,
      weeklyHourActual: undefined,  // null/undefined
    }

    render(
      <FlexibleCard
        priority={priority}
        isEditing={false}
        {...mockHandlers}
      />
    )

    // Should show "0h" for actual
    expect(screen.getByText('0h')).toBeInTheDocument()
    expect(screen.getByText(/\/ 5h/)).toBeInTheDocument()
  })

  it('passes weeklyHourActual when set', () => {
    const priority: Priority = {
      ...basePriority,
      weeklyHourTarget: 10,
      weeklyHourActual: 3.5,
    }

    render(
      <FlexibleCard
        priority={priority}
        isEditing={false}
        {...mockHandlers}
      />
    )

    // Should show actual hours
    expect(screen.getByText('3.5h')).toBeInTheDocument()
    expect(screen.getByText(/\/ 10h/)).toBeInTheDocument()
  })

  it('HourRing renders inside FlexibleCard content area', () => {
    const priority: Priority = {
      ...basePriority,
      weeklyHourTarget: 5,
    }

    render(
      <FlexibleCard
        priority={priority}
        isEditing={false}
        {...mockHandlers}
      />
    )

    // HourRing SVG should be present in the card
    const svg = document.querySelector('svg[role="img"]')
    expect(svg).toBeInTheDocument()

    // Priority name area is clickable to enter edit mode (title="Click to edit" is on h3)
    const nameArea = document.querySelector('h3[title="Click to edit"]')
    expect(nameArea).toBeInTheDocument()
  })

  it('HourRing does NOT render in edit mode', () => {
    const priority: Priority = {
      ...basePriority,
      weeklyHourTarget: 5,
      weeklyHourActual: 2,
    }

    render(
      <FlexibleCard
        priority={priority}
        isEditing={true}  // Edit mode
        {...mockHandlers}
      />
    )

    // Ring should not be visible
    const svg = document.querySelector('svg[role="img"]')
    expect(svg).not.toBeInTheDocument()

    // Instead, edit fields should be visible
    expect(screen.getByLabelText(/weekly hour target/i)).toBeInTheDocument()
  })
})
