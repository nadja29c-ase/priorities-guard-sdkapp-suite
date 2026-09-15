/**
 * Card density: two passes (inc_cardsize_fix_3.md — "Increment 3") and one
 * unification (inc_fullscreen_size_fix.md — "Increment 4").
 *
 * Not to be confused with the reverted Increment 2 (compact-row redesign,
 * InlinePriorityRow.tsx, no longer exists). Increment 3 kept DeadlineCard/
 * FlexibleCard structurally identical in both modes and tightened spacing/
 * sizing values in inline mode only, via an isInline prop threaded App.tsx
 * -> PriorityCardWrapper -> DeadlineCard/FlexibleCard -> GoalSection/HourRing.
 * Increment 4 deliberately retired that split: fullscreen adopts the same
 * tightened values, the ternaries collapse to one value each, and isInline
 * is removed from all five components' props (verified unused by grep, then
 * confirmed by this file's — and every other existing test file's — behavior
 * tests still passing unmodified with the prop gone).
 *
 * Central regression this file guards against: inline mode must keep
 * rendering the SAME rich cards fullscreen does (role="article",
 * DeadlineCard/FlexibleCard's full content) — not a compact substitute.
 * That's the opposite assertion from the old (deleted) InlineDensity.test.tsx,
 * which is the point.
 *
 * Test strategy for collapsed values (Increment 4's own instruction): assert
 * the concrete class independently in each mode, never mode-to-mode equality.
 * Once a ternary collapses, both modes execute the identical line of code —
 * an equality check would just compare that value to itself and catch
 * nothing (a future edit breaking both modes to the same wrong value would
 * still pass an equality-only test).
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../App'
import { setMockPriorities, mockOpenai } from '../test/setup'
import type { Priority } from '../types'

const deadlinePriority: Priority = {
  id: 'pri-1',
  name: 'Launch Feature X',
  type: 'deadline',
  calendarKeyword: 'P1',
  status: 'active',
  deadline: '2026-10-01',
  weeklyHourTarget: undefined,
  weeklyHourActual: undefined,
  checkpointDate: undefined,
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
  deadline: undefined,
  weeklyHourTarget: 5,
  weeklyHourActual: 3,
  checkpointDate: '2026-11-15',
  avgTargetAchievement: 84.0,
  deliverables: [],
  goals: [{ id: 'g1', text: 'Finish book', achieved: false }],
}

const MODES = ['inline', 'fullscreen'] as const

function renderInMode(mode: 'inline' | 'fullscreen', priorities: Priority[]) {
  mockOpenai.displayMode = mode
  setMockPriorities(priorities, true)
  return render(<App />)
}

describe('Card density — rich cards still render as themselves in inline mode (regression guard vs. Increment 2)', () => {
  it('inline mode renders DeadlineCard/FlexibleCard (role="article"), not a compact substitute', () => {
    renderInMode('inline', [deadlinePriority, flexiblePriority])
    expect(screen.queryAllByRole('article')).toHaveLength(2)
  })

  it('inline mode still renders full card content — deliverables section, goals section, edit affordances', () => {
    // Deliverables/goals sections are collapsed by default in inline mode
    // (defaultSectionsExpanded={!isInline} in App.tsx — content-visibility
    // logic, unrelated to and untouched by either density increment) — so
    // the section headers/counts are what's checked here, not the
    // individual collapsed-section item text.
    renderInMode('inline', [deadlinePriority, flexiblePriority])
    expect(screen.getByText('E2E Deliverables')).toBeInTheDocument()
    expect(screen.getByText('(1/2)')).toBeInTheDocument()
    expect(screen.getByText('1-Month Goal')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /edit priority: launch feature x/i })).toBeInTheDocument()
  })
})

describe('Card density — both modes render the same collapsed spacing/sizing values (Increment 4)', () => {
  describe('App.tsx card container: gap-2', () => {
    for (const mode of MODES) {
      it(mode, () => {
        const { container } = renderInMode(mode, [deadlinePriority, flexiblePriority])
        const cardContainer = container.querySelector('main[role="main"] > div.flex.flex-col')
        expect(cardContainer).toHaveClass('gap-2')
        expect(cardContainer).not.toHaveClass('gap-3')
        expect(cardContainer).not.toHaveClass('gap-5')
      })
    }
  })

  describe('DeadlineCard: banner py-1.5, content p-4, header mb-2, lead-metric mb-3, footer pt-2', () => {
    for (const mode of MODES) {
      it(mode, () => {
        const { container } = renderInMode(mode, [deadlinePriority])
        const banner = screen.getByTestId('deadline-banner')
        expect(banner).toHaveClass('py-1.5')
        expect(banner).not.toHaveClass('py-2.5')

        // Content padding wrapper — the div immediately after the banner.
        const contentArea = banner.nextElementSibling
        expect(contentArea).toHaveClass('p-4')
        expect(contentArea).not.toHaveClass('p-5')

        // Header row — structural, not text-based (screen.getByText('P1') is
        // ambiguous: P1 also appears in the calendar-keyword-reminder
        // paragraph elsewhere in the card).
        const headerRow = contentArea?.firstElementChild
        expect(headerRow).toHaveClass('mb-2')
        expect(headerRow).not.toHaveClass('mb-3')

        const doneCount = screen.getByText('1', { selector: 'span' })
        const leadMetricRow = doneCount.closest('div')
        expect(leadMetricRow).toHaveClass('mb-3')
        expect(leadMetricRow).not.toHaveClass('mb-4')

        // Footer — the collapsible E2E Deliverables section wrapper.
        const footer = container.querySelector('.border-t.border-subtle')
        expect(footer).toHaveClass('pt-2')
        expect(footer).not.toHaveClass('pt-3')
      })
    }
  })

  describe('FlexibleCard: card p-4, header mb-2, stat-row mb-3', () => {
    for (const mode of MODES) {
      it(mode, () => {
        const { container } = renderInMode(mode, [flexiblePriority])
        const card = screen.getByRole('article', { name: flexiblePriority.name })
        expect(card).toHaveClass('p-4')
        expect(card).not.toHaveClass('p-5')

        // Structural, not text-based — 'P2' is ambiguous (also appears in
        // the calendar-keyword-reminder paragraph elsewhere in the card).
        const headerRow = card.firstElementChild
        expect(headerRow).toHaveClass('mb-2')
        expect(headerRow).not.toHaveClass('mb-3')

        const statRow = container.querySelector('.flex.items-center.gap-4')
        expect(statRow).toHaveClass('mb-3')
        expect(statRow).not.toHaveClass('mb-4')
      })
    }
  })

  describe('GoalSection footer: pt-2', () => {
    for (const mode of MODES) {
      it(mode, () => {
        const { container } = renderInMode(mode, [flexiblePriority])
        const goalsFooter = container.querySelector('.border-t.border-subtle')
        expect(goalsFooter).toHaveClass('pt-2')
        expect(goalsFooter).not.toHaveClass('pt-3')
      })
    }
  })

  describe('HourRing: w-14 h-14 (56px)', () => {
    for (const mode of MODES) {
      it(mode, () => {
        const { container } = renderInMode(mode, [flexiblePriority])
        const ring = container.querySelector('svg[role="img"]')?.closest('div.relative')
        expect(ring).toHaveClass('w-14')
        expect(ring).toHaveClass('h-14')
        expect(ring).not.toHaveClass('w-16')
        expect(ring).not.toHaveClass('h-16')
      })
    }
  })

  describe('DeadlineCard toggle-button margin: mb-1 when expanded, nothing when collapsed — now identical logic in both modes', () => {
    for (const mode of MODES) {
      it(mode, async () => {
        renderInMode(mode, [deadlinePriority])
        const toggle = screen.getByRole('button', { name: /e2e deliverables/i })
        // Inline defaults collapsed (defaultSectionsExpanded={!isInline});
        // fullscreen defaults expanded — so assert the *transition* here
        // rather than a fixed starting class, since Increment 4 made the
        // state-dependent behavior identical, not the default state.
        await userEvent.click(toggle) // flip once, whichever direction
        const afterFirstClick = toggle.className.includes('mb-1')
        await userEvent.click(toggle) // flip back
        const afterSecondClick = toggle.className.includes('mb-1')
        // Exactly one of the two states should have mb-1 (expanded) and the
        // other should have neither mb-1 nor mb-2 (collapsed) — proves the
        // margin tracks expanded/collapsed state, with no mb-2 anywhere.
        expect(toggle).not.toHaveClass('mb-2')
        expect(afterFirstClick).not.toBe(afterSecondClick)
      })
    }
  })

  describe('GoalSection toggle-button margin: mb-1 when expanded, nothing when collapsed — now identical logic in both modes', () => {
    // Two goals so the toggle is collapsible from either starting state
    // (isCollapsible = goals.length > 1 || !expanded — a single goal that's
    // already expanded isn't collapsible, which would make the click below
    // a no-op and the test wouldn't actually exercise a state change).
    const twoGoalsPriority: Priority = {
      ...flexiblePriority,
      goals: [
        { id: 'g1', text: 'Finish book', achieved: false },
        { id: 'g2', text: 'Run a 5k', achieved: false },
      ],
    }

    for (const mode of MODES) {
      it(mode, async () => {
        renderInMode(mode, [twoGoalsPriority])
        const toggle = screen.getByRole('button', { name: /1-month goals/i })
        await userEvent.click(toggle)
        const afterFirstClick = toggle.className.includes('mb-1')
        await userEvent.click(toggle)
        const afterSecondClick = toggle.className.includes('mb-1')
        expect(toggle).not.toHaveClass('mb-2')
        expect(afterFirstClick).not.toBe(afterSecondClick)
      })
    }
  })
})

describe('Card density — no font-size class changed in either mode', () => {
  it('HourRing center text keeps text-sm / text-2xs in both modes', () => {
    const inline = renderInMode('inline', [flexiblePriority])
    const inlineActual = screen.getByText('3h')
    expect(inlineActual).toHaveClass('text-sm')
    inline.unmount()

    renderInMode('fullscreen', [flexiblePriority])
    const fullscreenActual = screen.getByText('3h')
    expect(fullscreenActual).toHaveClass('text-sm')
  })

  it('card name heading keeps text-sm in both modes', () => {
    const inline = renderInMode('inline', [deadlinePriority])
    expect(screen.getByText('Launch Feature X')).toHaveClass('text-sm')
    inline.unmount()

    renderInMode('fullscreen', [deadlinePriority])
    expect(screen.getByText('Launch Feature X')).toHaveClass('text-sm')
  })
})

describe('Card density — inline-only components (CalendarConnectionMinimal, ExpandButton): unaffected by Increment 4, never had a fullscreen path', () => {
  it('CalendarConnectionMinimal uses mt-2', () => {
    renderInMode('inline', [deadlinePriority])
    const indicator = screen.getByText('Google Calendar connected').closest('div')
    expect(indicator).toHaveClass('mt-2')
    expect(indicator).not.toHaveClass('mt-4')
  })

  it('ExpandButton uses mt-2 but keeps py-2.5 unchanged — button padding was explicitly declined, not touched, in Increment 3', () => {
    renderInMode('inline', [deadlinePriority])
    const button = screen.getByRole('button', { name: /open full dashboard/i })
    expect(button).toHaveClass('mt-2')
    expect(button).not.toHaveClass('mt-4')
    expect(button).toHaveClass('py-2.5')
    expect(button).not.toHaveClass('py-2')
  })
})
