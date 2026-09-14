/**
 * Inline density redesign (inc_card_size_fix2.md).
 *
 * Central regression this file guards against: inline mode must never render
 * DeadlineCard/FlexibleCard (or any of their rich-card chrome) again. Absence
 * is asserted structurally (role="article", which only those two components'
 * root element uses in this codebase — confirmed by reading both files), not
 * by a class-string or snapshot, per the increment's own instruction to learn
 * from the width increment's Codex-caught test gap: assert what actually
 * changed, not a value that would pass either way.
 */

import { describe, it, expect } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../App'
import { setMockPriorities, mockOpenai } from '../test/setup'
import type { Priority } from '../types'
import { daysUntil, formatDate } from '../utils'
import { t } from '../i18n'

const deadlinePriority: Priority = {
  id: 'pri-1',
  name: 'Launch Feature X',
  type: 'deadline',
  calendarKeyword: 'P1',
  status: 'active',
  deadline: '2026-10-01',
  weeklyHourTarget: 10,
  weeklyHourActual: 8,
  checkpointDate: undefined,
  deliverables: [
    { id: 'd1', name: 'Design doc', done: true },
    { id: 'd2', name: 'Implementation', done: false },
  ],
  goals: [],
}

const flexiblePriorityWithAvg: Priority = {
  id: 'pri-2',
  name: 'This Is A Deliberately Very Long Priority Name That Should Truncate Visually',
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

const flexiblePriorityNoAvgNoCheckpoint: Priority = {
  id: 'pri-3',
  name: 'Family time',
  type: 'flexible',
  calendarKeyword: 'P3',
  status: 'active',
  deadline: undefined,
  weeklyHourTarget: 8,
  weeklyHourActual: 1,
  checkpointDate: undefined,
  avgTargetAchievement: null,
  deliverables: [],
  goals: [],
}

function renderInMode(mode: 'inline' | 'fullscreen', priorities: Priority[]) {
  mockOpenai.displayMode = mode
  setMockPriorities(priorities, true)
  return render(<App />)
}

describe('Inline density — DeadlineCard/FlexibleCard never mount in inline mode', () => {
  it('renders zero rich cards (role="article") in inline mode with priorities present', () => {
    renderInMode('inline', [deadlinePriority, flexiblePriorityWithAvg])
    expect(screen.queryAllByRole('article')).toHaveLength(0)
  })

  it('positive control: fullscreen mode DOES render rich cards (role="article") for the same data', () => {
    renderInMode('fullscreen', [deadlinePriority, flexiblePriorityWithAvg])
    expect(screen.queryAllByRole('article')).toHaveLength(2)
  })

  it('inline mode still renders the priority names and data, just via the compact renderer', () => {
    renderInMode('inline', [deadlinePriority])
    expect(screen.getByText('Launch Feature X')).toBeInTheDocument()
  })
})

describe('Inline density — host-driven displayMode transition swaps renderer (structural, not CSS)', () => {
  it('switches from compact rows to rich cards and back via openai:set_globals', () => {
    renderInMode('inline', [deadlinePriority])
    expect(screen.queryAllByRole('article')).toHaveLength(0)

    mockOpenai.displayMode = 'fullscreen'
    act(() => { window.dispatchEvent(new Event('openai:set_globals')) })
    expect(screen.queryAllByRole('article')).toHaveLength(1)

    mockOpenai.displayMode = 'inline'
    act(() => { window.dispatchEvent(new Event('openai:set_globals')) })
    expect(screen.queryAllByRole('article')).toHaveLength(0)
  })
})

describe('Inline density — compact row content, per priority type', () => {
  it('deadline row: shows doneCount/totalCount and a daysUntil-based status line', () => {
    renderInMode('inline', [deadlinePriority])
    expect(screen.getByText('1/2')).toBeInTheDocument()

    // Actually assert the status line, not just the lead metric — this test's
    // own name previously claimed to cover it without doing so.
    const days = daysUntil(deadlinePriority.deadline!)
    const expectedStatusLine = days > 0
      ? t('dDaysLeft', { n: days })
      : days === 0
        ? t('dueToday')
        : t('dDaysOverdue', { n: Math.abs(days) })
    expect(screen.getByText(expectedStatusLine)).toBeInTheDocument()
  })

  it('flexible row with avgTargetAchievement: shows rounded percentage and the by-checkpoint status line', () => {
    renderInMode('inline', [flexiblePriorityWithAvg])
    expect(screen.getByText('~84%')).toBeInTheDocument()

    // Actually assert the by-checkpoint status line, not just the lead metric.
    const expectedStatusLine = `${t('by')} ${formatDate(flexiblePriorityWithAvg.checkpointDate!)}`
    expect(screen.getByText(expectedStatusLine)).toBeInTheDocument()
  })

  it('flexible row with null avgTargetAchievement: shows "Not enough data yet", not a false claim of active tracking', () => {
    renderInMode('inline', [flexiblePriorityNoAvgNoCheckpoint])
    expect(screen.getByText('Not enough data yet')).toBeInTheDocument()
  })

  it('flexible row without checkpointDate: omits the status line entirely rather than inventing filler copy', () => {
    const { container } = renderInMode('inline', [flexiblePriorityNoAvgNoCheckpoint])
    // No <p> status line should exist for this row — the only <p> elements in
    // inline mode come from InlinePriorityRow's optional status line.
    expect(container.querySelectorAll('p')).toHaveLength(0)
  })
})

describe('Inline density — accessibility', () => {
  it('badge is non-color-only: the keyword text itself is present, not just a colored dot', () => {
    renderInMode('inline', [deadlinePriority])
    expect(screen.getByText('P1')).toBeInTheDocument()
  })

  it('truncation is visual-only: the full (long) name remains in the accessible text content despite the truncate class', () => {
    renderInMode('inline', [flexiblePriorityWithAvg])
    const nameNode = screen.getByText(flexiblePriorityWithAvg.name)
    expect(nameNode).toBeInTheDocument()
    expect(nameNode.className).toMatch(/truncate/)
    // The full, untruncated string is the actual text content — truncation
    // never happened at the DOM/text level, only via CSS overflow clipping.
    expect(nameNode.textContent).toBe(flexiblePriorityWithAvg.name)
  })

  it('rows are static: no button role, no tabIndex, no click handler surface (approved design: CTA is the sole path to fullscreen)', () => {
    renderInMode('inline', [deadlinePriority])
    expect(screen.queryByRole('button', { name: /launch feature x/i })).not.toBeInTheDocument()
    // The only inline-mode button should be the existing CTA.
    expect(screen.getByRole('button', { name: /open full dashboard/i })).toBeInTheDocument()

    // Checking role/name absence alone would pass for a focusable, clickable
    // row that simply omitted role="button" or used a different accessible
    // name — neither of which getByRole('button', {...}) would ever match.
    // Assert tabIndex directly on the row element itself.
    const nameNode = screen.getByText(deadlinePriority.name)
    const row = nameNode.closest('div[class*="rounded-xl"]')
    expect(row).toBeTruthy()
    expect(row).not.toHaveAttribute('tabindex')
    expect(row).not.toHaveAttribute('role')
  })
})

describe('Inline density — no nested scrolling introduced (canon item 52, structural check)', () => {
  it('inline priority list container has no overflow-y-auto / overflow-y-scroll class', () => {
    const { container } = renderInMode('inline', [
      deadlinePriority,
      flexiblePriorityWithAvg,
      flexiblePriorityNoAvgNoCheckpoint,
    ])
    const overflowEls = container.querySelectorAll('[class*="overflow-y-auto"], [class*="overflow-y-scroll"]')
    expect(overflowEls.length).toBe(0)
  })
})

describe('Inline density — fullscreen regression (unchanged behavior)', () => {
  it('fullscreen still renders full deliverables/goals content via the unchanged PriorityCardWrapper branch', () => {
    renderInMode('fullscreen', [deadlinePriority])
    expect(screen.getByText('Design doc')).toBeInTheDocument()
    expect(screen.getByText('Implementation')).toBeInTheDocument()
  })
})

describe('Inline density — no new host-bridge tool calls from the compact renderer', () => {
  // Scope, precisely: this checks window.openai.callTool (the host-bridge
  // channel) only, not fetch(). InlinePriorityRow never calls fetch — the
  // only fetch() in this codebase (widgetErrorReporter's reportWidgetError)
  // fires from the top-level ErrorBoundary on a render crash, not from
  // normal rendering, so it isn't exercised by mounting either mode and
  // isn't what "no new calls from the compact renderer" is checking here.
  //
  // Mounting the widget already fires pre-existing callTool calls unrelated
  // to display mode (the Inc 89 diagnostic mount ping, and the
  // timeAllocation backfill when it's missing on connected data) — neither
  // depends on isInline. The correct check for "no new calls introduced by
  // the inline renderer" is that inline and fullscreen produce the
  // IDENTICAL call count for the same data, not that either produces zero.
  it('inline and fullscreen fire the same number of callTool calls for identical data', () => {
    const priorities = [deadlinePriority, flexiblePriorityWithAvg, flexiblePriorityNoAvgNoCheckpoint]

    const inline = renderInMode('inline', priorities)
    const inlineCallCount = mockOpenai.callTool.mock.calls.length
    inline.unmount()

    mockOpenai.callTool.mockClear()

    renderInMode('fullscreen', priorities)
    const fullscreenCallCount = mockOpenai.callTool.mock.calls.length

    expect(inlineCallCount).toBe(fullscreenCallCount)
  })
})

describe('Inline density — Add Priority routes through fullscreen first (regression guard)', () => {
  // Real bug caught in review: handleOpenAddForm only redirected to fullscreen
  // on mobile ("desktop: open the form inline — no display mode change" was the
  // pre-redesign assumption). AddPriorityForm is a multi-step form with local,
  // unpersisted field state (name/deadline/weeklyHourTarget/checkpointDate/
  // initialGoalText all live in useState inside the form itself) — if it were
  // ever allowed to mount while isInline, or if displayMode flipped to inline
  // while it was open, that state would be silently destroyed. The fix routes
  // through the entry point (handleOpenAddForm), not a render-time gate, so the
  // form only ever mounts via the unchanged fullscreen branch.
  it('clicking "Add a new priority" while inline transitions to fullscreen before the form mounts', async () => {
    mockOpenai.displayMode = 'inline'
    setMockPriorities([], true, ['P1', 'P2', 'P3'])
    render(<App />)

    expect(screen.queryAllByRole('article')).toHaveLength(0)

    await userEvent.click(screen.getByRole('button', { name: /add a new priority/i }))

    // Fullscreen-only marker present proves displayMode actually flipped —
    // not just that the form happens to render into whatever container exists.
    expect(screen.getByRole('button', { name: /minimize dashboard/i })).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  // Second real bug caught in review of the fix above: handleOpenAddForm is a
  // click handler — it never runs for a cold-start resume where widgetState
  // (addFormOpen: true) was persisted from a prior fullscreen session and the
  // host now reports inline. isAddingPriority's render block has no isInline
  // gate at all, so without a separate guard this path renders the full form
  // straight into the compact inline view on mount, unconditionally. Fixed by
  // computing needsFullscreenForAdd once (a plain const, not an effect) and
  // feeding it into both the displayMode and desktopLocalFullscreenIntentRef
  // initializers, so the correct state lands on the very first render.
  it('resuming with a persisted addFormOpen while the host reports inline forces fullscreen on mount', () => {
    mockOpenai.displayMode = 'inline'
    mockOpenai.widgetState = { addFormOpen: true }
    setMockPriorities([], true, ['P1', 'P2', 'P3'])
    render(<App />)

    expect(screen.getByRole('button', { name: /minimize dashboard/i })).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  it('a plain inline mount with no persisted addFormOpen stays inline (no over-triggering)', () => {
    mockOpenai.displayMode = 'inline'
    setMockPriorities([deadlinePriority], true)
    render(<App />)

    expect(screen.queryByRole('button', { name: /minimize dashboard/i })).not.toBeInTheDocument()
    expect(screen.queryAllByRole('article')).toHaveLength(0)
  })
})
