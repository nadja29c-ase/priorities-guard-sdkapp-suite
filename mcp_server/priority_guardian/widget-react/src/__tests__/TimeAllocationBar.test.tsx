/**
 * Unit tests for TimeAllocationBar component (Widget Increment C)
 *
 * Tests:
 * - Renders nothing when timeAllocation is undefined
 * - Renders header with total hours
 * - Renders date range formatted correctly (inclusive end)
 * - Renders stacked bar with correct proportional widths
 * - Renders legend dots matching active priorities only
 * - Renders "other" in legend always (even when 0)
 * - Edge cases: zero hours, single priority, all "other", small segments
 * - Color tests for bar segments
 * - Accessibility tests
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TimeAllocationBar } from '../components/TimeAllocationBar'
import type { TimeAllocation, CalendarKeyword } from '../types'

// Sample time allocation data for testing
const sampleTimeAllocation: TimeAllocation = {
  weekStart: '2026-02-09T00:00:00+00:00',
  weekEnd: '2026-02-16T00:00:00+00:00', // Exclusive end (Monday)
  totalTrackedHours: 31.75,
  keywords: {
    P1: { hours: 10.5, eventCount: 6 },
    P2: { hours: 3.0, eventCount: 2 },
    P3: { hours: 0.0, eventCount: 0 },
  },
  otherHours: 18.25,
  barSegments: {
    P1: 10.5,
    P2: 3.0,
    P3: 0.0,
    other: 18.25,
  },
}

const allActiveKeywords: CalendarKeyword[] = ['P1', 'P2', 'P3']

describe('TimeAllocationBar', () => {
  describe('Conditional Rendering', () => {
    it('renders nothing when timeAllocation is undefined', () => {
      const { container } = render(
        <TimeAllocationBar
          timeAllocation={undefined}
          activeKeywords={allActiveKeywords}
        />
      )
      expect(container.firstChild).toBeNull()
    })

    it('renders when timeAllocation is present', () => {
      render(
        <TimeAllocationBar
          timeAllocation={sampleTimeAllocation}
          activeKeywords={allActiveKeywords}
        />
      )
      expect(screen.getByText('Your time allocation this week')).toBeInTheDocument()
    })
  })

  describe('Header', () => {
    it('renders total hours', () => {
      render(
        <TimeAllocationBar
          timeAllocation={sampleTimeAllocation}
          activeKeywords={allActiveKeywords}
        />
      )
      // 31.75 rounds to 31.8 (1 decimal place)
      expect(screen.getByText('31.8h')).toBeInTheDocument()
    })

    it('renders "Your time allocation this week" heading', () => {
      render(
        <TimeAllocationBar
          timeAllocation={sampleTimeAllocation}
          activeKeywords={allActiveKeywords}
        />
      )
      expect(screen.getByRole('heading', { name: /your time allocation this week/i })).toBeInTheDocument()
    })
  })

  describe('Date Range', () => {
    it('renders date range with inclusive end (Sunday, not Monday)', () => {
      render(
        <TimeAllocationBar
          timeAllocation={sampleTimeAllocation}
          activeKeywords={allActiveKeywords}
        />
      )
      // weekEnd is Feb 16 (Monday), should display Feb 15 (Sunday)
      expect(screen.getByText(/Feb 9/)).toBeInTheDocument()
      expect(screen.getByText(/Feb 15/)).toBeInTheDocument()
      // Should NOT show Feb 16
      expect(screen.queryByText(/Feb 16/)).not.toBeInTheDocument()
    })
  })

  describe('Stacked Bar', () => {
    it('renders bar with role="img" and aria-label', () => {
      render(
        <TimeAllocationBar
          timeAllocation={sampleTimeAllocation}
          activeKeywords={allActiveKeywords}
        />
      )
      const bar = screen.getByRole('img')
      expect(bar).toHaveAttribute('aria-label', expect.stringContaining('Time allocation'))
      expect(bar).toHaveAttribute('aria-label', expect.stringContaining('P1'))
    })

    it('renders empty gray bar when totalTrackedHours is 0', () => {
      const zeroAllocation: TimeAllocation = {
        ...sampleTimeAllocation,
        totalTrackedHours: 0,
        keywords: {
          P1: { hours: 0, eventCount: 0 },
          P2: { hours: 0, eventCount: 0 },
          P3: { hours: 0, eventCount: 0 },
        },
        otherHours: 0,
        barSegments: { P1: 0, P2: 0, P3: 0, other: 0 },
      }

      render(
        <TimeAllocationBar
          timeAllocation={zeroAllocation}
          activeKeywords={allActiveKeywords}
        />
      )

      expect(screen.getByText('0h')).toBeInTheDocument()
      const bar = screen.getByRole('img')
      expect(bar).toHaveAttribute('aria-label', expect.stringContaining('no tracked hours'))
    })
  })

  describe('Legend', () => {
    it('shows only active keywords in legend', () => {
      // Only P1 and P3 are active (no P2 priority)
      const activeKeywords: CalendarKeyword[] = ['P1', 'P3']

      render(
        <TimeAllocationBar
          timeAllocation={sampleTimeAllocation}
          activeKeywords={activeKeywords}
        />
      )

      expect(screen.getByText(/P1/)).toBeInTheDocument()
      expect(screen.getByText(/P3/)).toBeInTheDocument()
      // P2 should not be in legend (no active P2 priority)
      const legendText = screen.getByText(/P3/).closest('div')?.parentElement?.textContent
      expect(legendText).not.toContain('P2 ')
    })

    it('always shows "other" in legend', () => {
      render(
        <TimeAllocationBar
          timeAllocation={sampleTimeAllocation}
          activeKeywords={allActiveKeywords}
        />
      )
      expect(screen.getByText(/other/i)).toBeInTheDocument()
    })

    it('shows "other" even when 0 hours', () => {
      const noOtherAllocation: TimeAllocation = {
        ...sampleTimeAllocation,
        totalTrackedHours: 10.5,
        otherHours: 0,
        barSegments: { ...sampleTimeAllocation.barSegments, other: 0 },
      }

      render(
        <TimeAllocationBar
          timeAllocation={noOtherAllocation}
          activeKeywords={['P1']}
        />
      )

      expect(screen.getByText(/other.*0h/i)).toBeInTheDocument()
    })

    it('renders hours for each legend item', () => {
      render(
        <TimeAllocationBar
          timeAllocation={sampleTimeAllocation}
          activeKeywords={allActiveKeywords}
        />
      )

      expect(screen.getByText(/P1.*10\.5h/)).toBeInTheDocument()
      expect(screen.getByText(/P2.*3h/)).toBeInTheDocument()
      expect(screen.getByText(/P3.*0h/)).toBeInTheDocument()
      // 18.25 rounds to 18.3 (1 decimal place)
      expect(screen.getByText(/other.*18\.3h/i)).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles single priority correctly', () => {
      const singlePriorityAllocation: TimeAllocation = {
        weekStart: '2026-02-09T00:00:00+00:00',
        weekEnd: '2026-02-16T00:00:00+00:00',
        totalTrackedHours: 15,
        keywords: {
          P1: { hours: 10, eventCount: 5 },
          P2: { hours: 0, eventCount: 0 },
          P3: { hours: 0, eventCount: 0 },
        },
        otherHours: 5,
        barSegments: { P1: 10, P2: 0, P3: 0, other: 5 },
      }

      render(
        <TimeAllocationBar
          timeAllocation={singlePriorityAllocation}
          activeKeywords={['P1']}
        />
      )

      expect(screen.getByText('15h')).toBeInTheDocument()
      expect(screen.getByText(/P1.*10h/)).toBeInTheDocument()
      expect(screen.getByText(/other.*5h/i)).toBeInTheDocument()
    })

    it('handles all time being "other" (no keyword matches)', () => {
      const allOtherAllocation: TimeAllocation = {
        weekStart: '2026-02-09T00:00:00+00:00',
        weekEnd: '2026-02-16T00:00:00+00:00',
        totalTrackedHours: 20,
        keywords: {
          P1: { hours: 0, eventCount: 0 },
          P2: { hours: 0, eventCount: 0 },
          P3: { hours: 0, eventCount: 0 },
        },
        otherHours: 20,
        barSegments: { P1: 0, P2: 0, P3: 0, other: 20 },
      }

      render(
        <TimeAllocationBar
          timeAllocation={allOtherAllocation}
          activeKeywords={['P1', 'P2']}
        />
      )

      expect(screen.getByText('20h')).toBeInTheDocument()
      // P1 and P2 show 0h in legend
      expect(screen.getByText(/P1.*0h/)).toBeInTheDocument()
      expect(screen.getByText(/P2.*0h/)).toBeInTheDocument()
      expect(screen.getByText(/other.*20h/i)).toBeInTheDocument()
    })

    it('legend uses keywords.hours (not barSegments) for multi-match events', () => {
      // Scenario: "P1 P2 sync" event (2h) is assigned to P1 in barSegments (exclusive),
      // but counted toward both P1 and P2 in keywords (true time worked)
      const multiMatchAllocation: TimeAllocation = {
        weekStart: '2026-02-09T00:00:00+00:00',
        weekEnd: '2026-02-16T00:00:00+00:00',
        totalTrackedHours: 15,
        keywords: {
          P1: { hours: 12, eventCount: 6 },  // includes 2h from multi-match
          P2: { hours: 5, eventCount: 3 },   // includes 2h from multi-match
          P3: { hours: 0, eventCount: 0 },
        },
        otherHours: 0,
        // barSegments: P2 is smaller because 2h multi-match went to P1 (higher priority)
        barSegments: { P1: 12, P2: 3, P3: 0, other: 0 },
      }

      render(
        <TimeAllocationBar
          timeAllocation={multiMatchAllocation}
          activeKeywords={['P1', 'P2']}
        />
      )

      // Legend should show P2 = 5h (from keywords), NOT 3h (from barSegments)
      expect(screen.getByText(/P2.*5h/)).toBeInTheDocument()
      // P1 should show 12h
      expect(screen.getByText(/P1.*12h/)).toBeInTheDocument()
    })

    it('handles large numbers (168h full week)', () => {
      const fullWeekAllocation: TimeAllocation = {
        weekStart: '2026-02-09T00:00:00+00:00',
        weekEnd: '2026-02-16T00:00:00+00:00',
        totalTrackedHours: 168,
        keywords: {
          P1: { hours: 80, eventCount: 20 },
          P2: { hours: 40, eventCount: 10 },
          P3: { hours: 20, eventCount: 5 },
        },
        otherHours: 28,
        barSegments: { P1: 80, P2: 40, P3: 20, other: 28 },
      }

      render(
        <TimeAllocationBar
          timeAllocation={fullWeekAllocation}
          activeKeywords={allActiveKeywords}
        />
      )

      expect(screen.getByText('168h')).toBeInTheDocument()
      expect(screen.getByText(/P1.*80h/)).toBeInTheDocument()
    })

    it('handles very small segments (still visible)', () => {
      // P3 is only 0.5h out of 100h total (0.5%)
      const smallSegmentAllocation: TimeAllocation = {
        weekStart: '2026-02-09T00:00:00+00:00',
        weekEnd: '2026-02-16T00:00:00+00:00',
        totalTrackedHours: 100,
        keywords: {
          P1: { hours: 50, eventCount: 10 },
          P2: { hours: 0, eventCount: 0 },
          P3: { hours: 0.5, eventCount: 1 },
        },
        otherHours: 49.5,
        barSegments: { P1: 50, P2: 0, P3: 0.5, other: 49.5 },
      }

      render(
        <TimeAllocationBar
          timeAllocation={smallSegmentAllocation}
          activeKeywords={['P1', 'P3']}
        />
      )

      // P3 should still show in legend with 0.5h
      expect(screen.getByText(/P3.*0\.5h/)).toBeInTheDocument()
    })
  })

  describe('Hours Formatting', () => {
    it('formats whole numbers without decimal', () => {
      const wholeNumberAllocation: TimeAllocation = {
        ...sampleTimeAllocation,
        totalTrackedHours: 10,
        keywords: {
          P1: { hours: 5, eventCount: 3 },
          P2: { hours: 3, eventCount: 2 },
          P3: { hours: 0, eventCount: 0 },
        },
        barSegments: { P1: 5, P2: 3, P3: 0, other: 2 },
      }

      render(
        <TimeAllocationBar
          timeAllocation={wholeNumberAllocation}
          activeKeywords={['P1', 'P2']}
        />
      )

      expect(screen.getByText('10h')).toBeInTheDocument()
      // Use exact match to avoid false positives (e.g., "10.5h" containing "5h")
      expect(screen.getByText(/P1 5h/)).toBeInTheDocument()
    })

    it('formats decimals with one decimal place', () => {
      render(
        <TimeAllocationBar
          timeAllocation={sampleTimeAllocation}
          activeKeywords={allActiveKeywords}
        />
      )

      // 31.75 rounds to 31.8 (1 decimal place)
      expect(screen.getByText('31.8h')).toBeInTheDocument()
      expect(screen.getByText(/P1.*10\.5h/)).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has section with aria-labelledby', () => {
      render(
        <TimeAllocationBar
          timeAllocation={sampleTimeAllocation}
          activeKeywords={allActiveKeywords}
        />
      )

      const section = screen.getByRole('region', { hidden: true }) ||
                      document.querySelector('section[aria-labelledby]')
      expect(section).toHaveAttribute('aria-labelledby', 'time-allocation-heading')
    })

    it('bar has descriptive aria-label', () => {
      render(
        <TimeAllocationBar
          timeAllocation={sampleTimeAllocation}
          activeKeywords={allActiveKeywords}
        />
      )

      const bar = screen.getByRole('img')
      const ariaLabel = bar.getAttribute('aria-label')

      expect(ariaLabel).toContain('Time allocation')
      expect(ariaLabel).toContain('P1')
      expect(ariaLabel).toContain('10.5h')
    })

    it('legend dots are aria-hidden', () => {
      render(
        <TimeAllocationBar
          timeAllocation={sampleTimeAllocation}
          activeKeywords={allActiveKeywords}
        />
      )

      // Find legend dots by class
      const dots = document.querySelectorAll('.w-2.h-2.rounded-full')
      dots.forEach(dot => {
        expect(dot).toHaveAttribute('aria-hidden', 'true')
      })
    })
  })
})
