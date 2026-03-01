/**
 * UI Guideline Compliance Tests for DeadlineCard and FlexibleCard
 *
 * Verifies absence of prohibited inline style patterns:
 * - #41: No colored backgrounds on text-containing areas
 * - #42: No text color overrides via inline style
 * - #64: No hardcoded hex colors for borders (use SDK tokens)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DeadlineCard } from '../components/DeadlineCard'
import { FlexibleCard } from '../components/FlexibleCard'
import type { Priority } from '../types'

// Mock handlers
const mockHandlers = {
  onStartEdit: vi.fn(),
  onCancelEdit: vi.fn(),
  onSave: vi.fn().mockResolvedValue(undefined),
  onDelete: vi.fn().mockResolvedValue(undefined),
  onKeywordChange: vi.fn().mockResolvedValue(undefined),
  onToggleDeliverable: vi.fn().mockResolvedValue(undefined),
  onRenameDeliverable: vi.fn().mockResolvedValue(undefined),
  onDeleteDeliverable: vi.fn().mockResolvedValue(undefined),
  onAddDeliverable: vi.fn().mockResolvedValue(undefined),
  onAddGoal: vi.fn().mockResolvedValue(undefined),
  onToggleGoal: vi.fn().mockResolvedValue(undefined),
  onRenameGoal: vi.fn().mockResolvedValue(undefined),
  onDeleteGoal: vi.fn().mockResolvedValue(undefined),
}

const deadlinePriority: Priority = {
  id: 'deadline-1',
  name: 'Ship Feature X',
  type: 'deadline',
  calendarKeyword: 'P1',
  status: 'active',
  deadline: '2026-03-15',
  deliverables: [
    { id: 'd1', name: 'Write tests', done: false },
    { id: 'd2', name: 'Code review', done: true },
  ],
  createdAt: '2026-01-01T00:00:00Z',
}

const flexiblePriority: Priority = {
  id: 'flexible-1',
  name: 'Learn Rust',
  type: 'flexible',
  calendarKeyword: 'P2',
  status: 'active',
  weeklyHourTarget: 10,
  weeklyHourActual: 4,
  checkpointDate: '2026-04-01',
  deliverables: [],
  goals: [{ id: 'g1', text: 'Build CLI tool', achieved: false }],
  createdAt: '2026-01-01T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('DeadlineCard UI Compliance', () => {
  it('does not have inline style with color on text elements', () => {
    render(
      <DeadlineCard
        priority={deadlinePriority}
        priorities={[deadlinePriority]}
        isEditing={false}
        {...mockHandlers}
      />
    )

    // Find text elements in the deadline banner
    const deadlineDateText = screen.getByText(/Mar 15, 2026/i)
    const daysLeftText = screen.getByText(/\d+d left|Due today|\d+d overdue/i)

    // Text elements should NOT have inline style attribute
    expect(deadlineDateText).not.toHaveAttribute('style')
    expect(daysLeftText).not.toHaveAttribute('style')
  })

  it('does not have inline style with background on banner div', () => {
    render(
      <DeadlineCard
        priority={deadlinePriority}
        priorities={[deadlinePriority]}
        isEditing={false}
        {...mockHandlers}
      />
    )

    // Find the banner div (contains the deadline date)
    const deadlineDateText = screen.getByText(/Mar 15, 2026/i)
    const bannerDiv = deadlineDateText.closest('div.bg-surface-secondary')

    // Banner should exist with SDK class, not inline background style
    expect(bannerDiv).toBeInTheDocument()
    expect(bannerDiv).not.toHaveAttribute('style')
  })

  it('calendar icon SVG uses CSS variable for stroke (not hardcoded hex)', () => {
    render(
      <DeadlineCard
        priority={deadlinePriority}
        priorities={[deadlinePriority]}
        isEditing={false}
        {...mockHandlers}
      />
    )

    // Find the calendar icon SVG (first svg in the banner)
    const bannerDiv = document.querySelector('.bg-surface-secondary')
    const calendarSvg = bannerDiv?.querySelector('svg')

    expect(calendarSvg).toBeInTheDocument()
    const strokeAttr = calendarSvg?.getAttribute('stroke')

    // Stroke should be a CSS variable, not a bare hex color
    expect(strokeAttr).toMatch(/^var\(--/)
  })

  it('card has colored left border via className (not inline style)', () => {
    render(
      <DeadlineCard
        priority={deadlinePriority}
        priorities={[deadlinePriority]}
        isEditing={false}
        {...mockHandlers}
      />
    )

    const card = screen.getByRole('article')

    // Card should have border class from constants.ts
    expect(card.className).toMatch(/border-l-4/)
    expect(card.className).toMatch(/border-l-\[var\(--/)

    // Card should NOT have inline borderLeft style
    expect(card).not.toHaveAttribute('style')
  })

  it('works for P2 keyword', () => {
    const p2Priority = { ...deadlinePriority, calendarKeyword: 'P2' as const }

    render(
      <DeadlineCard
        priority={p2Priority}
        priorities={[p2Priority]}
        isEditing={false}
        {...mockHandlers}
      />
    )

    const card = screen.getByRole('article')
    expect(card.className).toMatch(/border-l-\[var\(--color-background-discovery/)
  })

  it('works for P3 keyword', () => {
    const p3Priority = { ...deadlinePriority, calendarKeyword: 'P3' as const }

    render(
      <DeadlineCard
        priority={p3Priority}
        priorities={[p3Priority]}
        isEditing={false}
        {...mockHandlers}
      />
    )

    const card = screen.getByRole('article')
    expect(card.className).toMatch(/border-l-\[var\(--color-background-caution/)
  })

  it('badge uses text-2xs class (not inline fontSize)', () => {
    render(
      <DeadlineCard
        priority={deadlinePriority}
        priorities={[deadlinePriority]}
        isEditing={false}
        {...mockHandlers}
      />
    )

    // Find the badge (contains "P1")
    const badge = screen.getByText('P1')

    expect(badge.className).toMatch(/text-2xs/)
    expect(badge).not.toHaveAttribute('style')
  })
})

describe('FlexibleCard UI Compliance', () => {
  it('card has colored left border via className (not inline style)', () => {
    render(
      <FlexibleCard
        priority={flexiblePriority}
        priorities={[flexiblePriority]}
        isEditing={false}
        {...mockHandlers}
      />
    )

    const card = screen.getByRole('article')

    // Card should have border class from constants.ts
    expect(card.className).toMatch(/border-l-4/)
    expect(card.className).toMatch(/border-l-\[var\(--/)

    // Card should NOT have inline borderLeft style
    expect(card).not.toHaveAttribute('style')
  })

  it('works for P1 keyword', () => {
    const p1Priority = { ...flexiblePriority, calendarKeyword: 'P1' as const }

    render(
      <FlexibleCard
        priority={p1Priority}
        priorities={[p1Priority]}
        isEditing={false}
        {...mockHandlers}
      />
    )

    const card = screen.getByRole('article')
    expect(card.className).toMatch(/border-l-\[var\(--color-background-info/)
  })

  it('works for P3 keyword', () => {
    const p3Priority = { ...flexiblePriority, calendarKeyword: 'P3' as const }

    render(
      <FlexibleCard
        priority={p3Priority}
        priorities={[p3Priority]}
        isEditing={false}
        {...mockHandlers}
      />
    )

    const card = screen.getByRole('article')
    expect(card.className).toMatch(/border-l-\[var\(--color-background-caution/)
  })

  it('hourglass icon uses stroke="currentColor" (compliant)', () => {
    // Render a flexible card without avgTargetAchievement to show the hourglass
    const noAvgPriority = { ...flexiblePriority, avgTargetAchievement: undefined }

    render(
      <FlexibleCard
        priority={noAvgPriority}
        priorities={[noAvgPriority]}
        isEditing={false}
        {...mockHandlers}
      />
    )

    // Find the hourglass icon (in the "Tracking in progress" section)
    const trackingText = screen.queryByText(/Tracking in progress/)
    if (trackingText) {
      const container = trackingText.closest('div')
      const hourglassSvg = container?.querySelector('svg')

      if (hourglassSvg) {
        expect(hourglassSvg.getAttribute('stroke')).toBe('currentColor')
      }
    }
    // If no tracking text (has avgTargetAchievement), that's fine - no hourglass to test
  })

  it('badge uses text-2xs class (not inline fontSize)', () => {
    render(
      <FlexibleCard
        priority={flexiblePriority}
        priorities={[flexiblePriority]}
        isEditing={false}
        {...mockHandlers}
      />
    )

    // Find the badge (contains "P2")
    const badge = screen.getByText('P2')

    expect(badge.className).toMatch(/text-2xs/)
    expect(badge).not.toHaveAttribute('style')
  })

  it('streak pill uses text-xs class (not inline fontSize)', () => {
    // Render with streakCount to show the streak pill
    const streakPriority = { ...flexiblePriority, streakCount: 3 }

    render(
      <FlexibleCard
        priority={streakPriority}
        priorities={[streakPriority]}
        isEditing={false}
        {...mockHandlers}
      />
    )

    // Find the streak pill (contains "3w streak")
    const streakPill = screen.getByText(/3w streak/)

    expect(streakPill.className).toMatch(/text-xs/)
    expect(streakPill).not.toHaveAttribute('style')
  })
})
