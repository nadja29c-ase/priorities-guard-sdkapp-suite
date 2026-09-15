/**
 * Inline density pass (inc_cardsize_fix_3.md — "Increment 3").
 *
 * Not to be confused with the reverted Increment 2 (compact-row redesign,
 * InlinePriorityRow.tsx, no longer exists). This increment keeps
 * DeadlineCard/FlexibleCard structurally identical in both modes — same
 * JSX tree, same content, same interactions — and only tightens spacing/
 * sizing values via a new isInline prop threaded App.tsx -> PriorityCardWrapper
 * -> DeadlineCard/FlexibleCard -> GoalSection/HourRing.
 *
 * Central regression this file guards against: inline mode must keep
 * rendering the SAME rich cards fullscreen does (role="article",
 * DeadlineCard/FlexibleCard's full content) — not a compact substitute.
 * That's the opposite assertion from the old (deleted) InlineDensity.test.tsx,
 * which is the point.
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
    // (defaultSectionsExpanded={!isInline}, pre-existing, unrelated to this
    // increment) — so the section headers/counts are what's checked here,
    // not the individual collapsed-section item text.
    renderInMode('inline', [deadlinePriority, flexiblePriority])
    expect(screen.getByText('E2E Deliverables')).toBeInTheDocument()
    expect(screen.getByText('(1/2)')).toBeInTheDocument()
    expect(screen.getByText('1-Month Goal')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /edit priority: launch feature x/i })).toBeInTheDocument()
  })
})

describe('Card density — isInline=true renders tightened spacing/sizing classes', () => {
  it('main[role="main"] carries the pg-inline padding-override class', () => {
    const { container } = renderInMode('inline', [deadlinePriority])
    const main = container.querySelector('main[role="main"]')
    expect(main).toHaveClass('pg-inline')
  })

  it('card container uses gap-2, not gap-5', () => {
    const { container } = renderInMode('inline', [deadlinePriority, flexiblePriority])
    const cardContainer = container.querySelector('main[role="main"] > div.flex.flex-col')
    expect(cardContainer).toHaveClass('gap-2')
    expect(cardContainer).not.toHaveClass('gap-5')
  })

  it('DeadlineCard: banner py-1.5, content p-4, header mb-2, lead-metric mb-3, footer pt-2', () => {
    const { container } = renderInMode('inline', [deadlinePriority])
    const banner = screen.getByTestId('deadline-banner')
    expect(banner).toHaveClass('py-1.5')
    expect(banner).not.toHaveClass('py-2.5')

    // Content padding wrapper — the div immediately after the banner.
    const contentArea = banner.nextElementSibling
    expect(contentArea).toHaveClass('p-4')
    expect(contentArea).not.toHaveClass('p-5')

    // Header row — badge + name + edit/delete buttons; structural, not
    // text-based (screen.getByText('P1') is ambiguous — P1 also appears in
    // the calendar-keyword-reminder paragraph elsewhere in the card).
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

  it('FlexibleCard: card padding p-4, header mb-2, stat-row mb-3', () => {
    const { container } = renderInMode('inline', [flexiblePriority])
    const card = screen.getByRole('article', { name: flexiblePriority.name })
    expect(card).toHaveClass('p-4')
    expect(card).not.toHaveClass('p-5')

    // Structural, not text-based — 'P2' is ambiguous (also appears in the
    // calendar-keyword-reminder paragraph elsewhere in the card). Header
    // row is the article's first child.
    const headerRow = card.firstElementChild
    expect(headerRow).toHaveClass('mb-2')
    expect(headerRow).not.toHaveClass('mb-3')

    const statRow = container.querySelector('.flex.items-center.gap-4')
    expect(statRow).toHaveClass('mb-3')
    expect(statRow).not.toHaveClass('mb-4')
  })

  it('GoalSection footer: pt-2, not pt-3', () => {
    const { container } = renderInMode('inline', [flexiblePriority])
    const goalsFooter = container.querySelector('.border-t.border-subtle')
    expect(goalsFooter).toHaveClass('pt-2')
    expect(goalsFooter).not.toHaveClass('pt-3')
  })

  it('HourRing: w-14 h-14 (56px), not w-16 h-16 (64px)', () => {
    const { container } = renderInMode('inline', [flexiblePriority])
    const ring = container.querySelector('svg[role="img"]')?.closest('div.relative')
    expect(ring).toHaveClass('w-14')
    expect(ring).toHaveClass('h-14')
    expect(ring).not.toHaveClass('w-16')
    expect(ring).not.toHaveClass('h-16')
  })
})

describe('Card density — isInline=false (fullscreen) renders exactly today\'s unchanged values', () => {
  it('main[role="main"] does NOT carry pg-inline', () => {
    const { container } = renderInMode('fullscreen', [deadlinePriority])
    const main = container.querySelector('main[role="main"]')
    expect(main).not.toHaveClass('pg-inline')
  })

  it('card container uses gap-5, not gap-2', () => {
    const { container } = renderInMode('fullscreen', [deadlinePriority, flexiblePriority])
    const cardContainer = container.querySelector('main[role="main"] > div.flex.flex-col')
    expect(cardContainer).toHaveClass('gap-5')
    expect(cardContainer).not.toHaveClass('gap-2')
  })

  it('DeadlineCard: banner py-2.5, content p-5, header mb-3, lead-metric mb-4, footer pt-3 — unchanged', () => {
    const { container } = renderInMode('fullscreen', [deadlinePriority])
    const banner = screen.getByTestId('deadline-banner')
    expect(banner).toHaveClass('py-2.5')
    expect(banner).not.toHaveClass('py-1.5')

    const contentArea = banner.nextElementSibling
    expect(contentArea).toHaveClass('p-5')
    expect(contentArea).not.toHaveClass('p-4')

    const headerRow = contentArea?.firstElementChild
    expect(headerRow).toHaveClass('mb-3')
    expect(headerRow).not.toHaveClass('mb-2')

    const doneCount = screen.getByText('1', { selector: 'span' })
    const leadMetricRow = doneCount.closest('div')
    expect(leadMetricRow).toHaveClass('mb-4')
    expect(leadMetricRow).not.toHaveClass('mb-3')

    const footer = container.querySelector('.border-t.border-subtle')
    expect(footer).toHaveClass('pt-3')
    expect(footer).not.toHaveClass('pt-2')
  })

  it('FlexibleCard: card padding p-5, header mb-3, stat-row mb-4 — unchanged', () => {
    const { container } = renderInMode('fullscreen', [flexiblePriority])
    const card = screen.getByRole('article', { name: flexiblePriority.name })
    expect(card).toHaveClass('p-5')
    expect(card).not.toHaveClass('p-4')

    const headerRow = card.firstElementChild
    expect(headerRow).toHaveClass('mb-3')
    expect(headerRow).not.toHaveClass('mb-2')

    const statRow = container.querySelector('.flex.items-center.gap-4')
    expect(statRow).toHaveClass('mb-4')
    expect(statRow).not.toHaveClass('mb-3')
  })

  it('GoalSection footer: pt-3, unchanged', () => {
    const { container } = renderInMode('fullscreen', [flexiblePriority])
    const goalsFooter = container.querySelector('.border-t.border-subtle')
    expect(goalsFooter).toHaveClass('pt-3')
    expect(goalsFooter).not.toHaveClass('pt-2')
  })

  it('HourRing: w-16 h-16 (64px), unchanged', () => {
    const { container } = renderInMode('fullscreen', [flexiblePriority])
    const ring = container.querySelector('svg[role="img"]')?.closest('div.relative')
    expect(ring).toHaveClass('w-16')
    expect(ring).toHaveClass('h-16')
    expect(ring).not.toHaveClass('w-14')
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

describe('Card density — second pass: gap-2, mt-2 margins, collapsed-state dead space removed', () => {
  it('inline card container uses gap-2 (not the first pass\'s gap-3)', () => {
    const { container } = renderInMode('inline', [deadlinePriority, flexiblePriority])
    const cardContainer = container.querySelector('main[role="main"] > div.flex.flex-col')
    expect(cardContainer).toHaveClass('gap-2')
    expect(cardContainer).not.toHaveClass('gap-3')
    expect(cardContainer).not.toHaveClass('gap-5')
  })

  it('CalendarConnectionMinimal uses mt-2 (not mt-4)', () => {
    renderInMode('inline', [deadlinePriority])
    const indicator = screen.getByText('Google Calendar connected').closest('div')
    expect(indicator).toHaveClass('mt-2')
    expect(indicator).not.toHaveClass('mt-4')
  })

  it('ExpandButton uses mt-2 (not mt-4) but keeps py-2.5 unchanged — button padding was explicitly declined, not touched', () => {
    renderInMode('inline', [deadlinePriority])
    const button = screen.getByRole('button', { name: /open full dashboard/i })
    expect(button).toHaveClass('mt-2')
    expect(button).not.toHaveClass('mt-4')
    expect(button).toHaveClass('py-2.5')
    expect(button).not.toHaveClass('py-2')
  })

  it('DeadlineCard toggle button: no margin class when collapsed (default inline state), mb-1 once expanded', async () => {
    renderInMode('inline', [deadlinePriority])
    const toggle = screen.getByRole('button', { name: /e2e deliverables/i })
    // Collapsed by default in inline mode (defaultDeliverablesExpanded={!isInline}).
    expect(toggle).not.toHaveClass('mb-1')
    expect(toggle).not.toHaveClass('mb-2')

    await userEvent.click(toggle)
    expect(toggle).toHaveClass('mb-1')
    expect(toggle).not.toHaveClass('mb-2')
  })

  it('GoalSection toggle button: no margin class when collapsed (default inline state), mb-1 once expanded', async () => {
    renderInMode('inline', [flexiblePriority])
    const toggle = screen.getByRole('button', { name: /1-month goal/i })
    expect(toggle).not.toHaveClass('mb-1')
    expect(toggle).not.toHaveClass('mb-2')

    await userEvent.click(toggle)
    expect(toggle).toHaveClass('mb-1')
    expect(toggle).not.toHaveClass('mb-2')
  })

  it('fullscreen DeadlineCard toggle button keeps mb-2 unconditionally, regardless of expanded state', async () => {
    // Real regression this test guards against: the first draft of this fix
    // gated the margin on `expanded` only, with no isInline check — since
    // fullscreen's sections start expanded by default, that silently shrank
    // fullscreen's toggle margin too (mb-2 -> mb-1), breaking the "fullscreen
    // never changes" invariant this pass and the whole prior increment were
    // built around. Caught by e2e/card-density.spec.ts's fullscreen-height
    // assertion (1194.5px -> 1182.5px), fixed by keeping fullscreen's branch
    // a flat, unconditional 'mb-2' — not state-dependent at all, matching
    // its original pre-this-pass behavior exactly in both states.
    renderInMode('fullscreen', [deadlinePriority])
    const toggle = screen.getByRole('button', { name: /e2e deliverables/i })
    // Fullscreen defaults to expanded.
    expect(toggle).toHaveClass('mb-2')
    expect(toggle).not.toHaveClass('mb-1')

    await userEvent.click(toggle)
    // Still mb-2 after collapsing — fullscreen's value never depends on state.
    expect(toggle).toHaveClass('mb-2')
    expect(toggle).not.toHaveClass('mb-1')
  })

  it('fullscreen GoalSection toggle button keeps mb-2 unconditionally, regardless of expanded state', async () => {
    // GoalSection's toggle only responds to clicks when isCollapsible
    // (goals.length > 1 || !expanded) — flexiblePriority's single goal
    // wouldn't actually let this test collapse it from its expanded default
    // (1 goal + already expanded = not collapsible), so the click would be
    // a no-op and the test wouldn't really exercise the collapsed state.
    // Two goals keeps it collapsible either way.
    const twoGoalsPriority: Priority = {
      ...flexiblePriority,
      goals: [
        { id: 'g1', text: 'Finish book', achieved: false },
        { id: 'g2', text: 'Run a 5k', achieved: false },
      ],
    }
    renderInMode('fullscreen', [twoGoalsPriority])
    const toggle = screen.getByRole('button', { name: /1-month goals/i })
    expect(toggle).toHaveClass('mb-2')
    expect(toggle).not.toHaveClass('mb-1')

    await userEvent.click(toggle)
    expect(toggle).toHaveClass('mb-2')
    expect(toggle).not.toHaveClass('mb-1')
  })
})
