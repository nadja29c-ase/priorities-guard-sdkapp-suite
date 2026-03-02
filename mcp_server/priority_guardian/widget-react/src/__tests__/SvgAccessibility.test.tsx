/**
 * SVG Accessibility Tests
 *
 * Verifies that all SVG elements have proper ARIA attributes:
 * - Decorative SVGs: aria-hidden="true"
 * - Data visualization SVGs: role="img" + aria-label
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ChevronIcon } from '../components/ChevronIcon'
import { ExpandButton } from '../components/ExpandButton'
import { HourRing } from '../components/HourRing'
import { PieChart } from '../components/PieChart'
import type { PieSlice } from '../types'

describe('SVG Accessibility', () => {
  describe('Decorative SVGs (aria-hidden="true")', () => {
    describe('ChevronIcon', () => {
      it('renders with aria-hidden="true"', () => {
        const { container } = render(<ChevronIcon expanded={false} />)

        const svg = container.querySelector('svg')
        expect(svg).toHaveAttribute('aria-hidden', 'true')
      })

      it('maintains aria-hidden when expanded', () => {
        const { container } = render(<ChevronIcon expanded={true} />)

        const svg = container.querySelector('svg')
        expect(svg).toHaveAttribute('aria-hidden', 'true')
      })
    })

    describe('ExpandButton', () => {
      it('SVG has aria-hidden="true"', () => {
        const { container } = render(<ExpandButton onClick={() => {}} />)

        const svg = container.querySelector('svg')
        expect(svg).toHaveAttribute('aria-hidden', 'true')
      })

      it('button has descriptive aria-label', () => {
        render(<ExpandButton onClick={() => {}} />)

        const button = screen.getByRole('button')
        expect(button).toHaveAttribute('aria-label', 'Open full dashboard')
      })
    })
  })

  describe('Data Visualization SVGs (role="img" + aria-label)', () => {
    describe('HourRing', () => {
      it('has role="img"', () => {
        render(<HourRing actual={2} target={5} keyword="P1" />)

        const svg = screen.getByRole('img')
        expect(svg).toHaveAttribute('role', 'img')
      })

      it('has descriptive aria-label', () => {
        render(<HourRing actual={2} target={5} keyword="P1" />)

        const svg = screen.getByRole('img')
        const ariaLabel = svg.getAttribute('aria-label')

        expect(ariaLabel).toContain('2h')
        expect(ariaLabel).toContain('5h')
      })

      it('aria-label reflects actual values', () => {
        render(<HourRing actual={3.5} target={10} keyword="P2" />)

        const svg = screen.getByRole('img')
        const ariaLabel = svg.getAttribute('aria-label')

        expect(ariaLabel).toContain('3.5h')
        expect(ariaLabel).toContain('10h')
      })

      it('does NOT have aria-hidden', () => {
        render(<HourRing actual={2} target={5} keyword="P1" />)

        const svg = screen.getByRole('img')
        expect(svg).not.toHaveAttribute('aria-hidden')
      })
    })

    describe('PieChart', () => {
      const sampleSlices: PieSlice[] = [
        { label: 'P1: Ship v1.0', type: 'priority', keyword: 'P1', hours: 10 },
        { label: 'Meetings', type: 'semantic', hours: 5 },
      ]

      it('has role="img"', () => {
        render(
          <PieChart
            slices={sampleSlices}
            totalHours={15}
            weekStart="2025-01-06"
            weekEnd="2025-01-12"
          />
        )

        const svg = screen.getByRole('img')
        expect(svg).toHaveAttribute('role', 'img')
      })

      it('has descriptive aria-label', () => {
        render(
          <PieChart
            slices={sampleSlices}
            totalHours={15}
            weekStart="2025-01-06"
            weekEnd="2025-01-12"
          />
        )

        const svg = screen.getByRole('img')
        const ariaLabel = svg.getAttribute('aria-label')

        expect(ariaLabel).toContain('15')
        expect(ariaLabel).toContain('hours')
        expect(ariaLabel).toContain('2')  // number of categories
      })

      it('does NOT have aria-hidden', () => {
        render(
          <PieChart
            slices={sampleSlices}
            totalHours={15}
            weekStart="2025-01-06"
            weekEnd="2025-01-12"
          />
        )

        const svg = screen.getByRole('img')
        expect(svg).not.toHaveAttribute('aria-hidden')
      })

      it('legend dots have aria-hidden="true"', () => {
        render(
          <PieChart
            slices={sampleSlices}
            totalHours={15}
            weekStart="2025-01-06"
            weekEnd="2025-01-12"
          />
        )

        // Legend dots are span elements with rounded-full class
        const legendDots = document.querySelectorAll('span.rounded-full')
        expect(legendDots.length).toBeGreaterThan(0)

        legendDots.forEach(dot => {
          expect(dot).toHaveAttribute('aria-hidden', 'true')
        })
      })
    })
  })
})
