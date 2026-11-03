/**
 * Inc 89 cleanup — fullscreen diagnostics off (PG_DIAG_FULLSCREEN = false)
 *
 * While the flag was on, every host openai:set_globals event sent two
 * record_widget_diagnostic tool calls (set_globals + displayMode.change) and every
 * mount sent one more — ~66–70 extra MCP requests per render in production.
 *
 * Also guards the Inc 89.10 desktop fullscreen intent guard (c1fddf1), which had no
 * test of its own: the diagnostics were the only thing that observed it.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import App from '../App'
import { setMockPriorities, resetMocks, mockOpenai } from '../test/setup'

const DIAGNOSTIC_TOOL = 'record_widget_diagnostic'

function diagnosticCalls() {
  return mockOpenai.callTool.mock.calls.filter(([name]) => name === DIAGNOSTIC_TOOL)
}

function hostSetGlobals(displayMode: 'inline' | 'fullscreen') {
  mockOpenai.displayMode = displayMode
  act(() => {
    window.dispatchEvent(new Event('openai:set_globals'))
  })
}

describe('Inc 89 cleanup: fullscreen diagnostics are off', () => {
  beforeEach(() => {
    resetMocks()
    mockOpenai.displayMode = 'inline'
    setMockPriorities([], true)
  })

  it('a mount sends no diagnostic tool call', () => {
    // Bug that would still pass: a diagnostic emitted later than mount, e.g. on
    // set_globals — covered by the next test.
    render(<App />)
    expect(diagnosticCalls()).toHaveLength(0)
  })

  it('host set_globals events send no diagnostic tool calls', () => {
    // Bug that would still pass: diagnostics re-routed through a channel other than
    // window.openai.callTool (e.g. fetch) — not observed here; the only diagnostic
    // reporter in the widget uses callTool (widgetErrorReporter.ts).
    render(<App />)
    for (let i = 0; i < 10; i++) {
      hostSetGlobals(i % 2 === 0 ? 'inline' : 'fullscreen')
    }
    expect(diagnosticCalls()).toHaveLength(0)
  })

  it('expand and minimize send no diagnostic tool calls', () => {
    // Bug that would still pass: none of the diagnostic emitters — all three call
    // sites (mount, set_globals, logDisplayModeChange) are exercised by this file.
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Open full dashboard' }))
    fireEvent.click(screen.getByRole('button', { name: 'Minimize dashboard' }))
    expect(diagnosticCalls()).toHaveLength(0)
  })
})

describe('Inc 89.10 desktop fullscreen intent guard (regression)', () => {
  beforeEach(() => {
    resetMocks()
    mockOpenai.displayMode = 'inline'
    setMockPriorities([], true)
  })

  it('a stale host inline sync does not revert the widget-owned desktop fullscreen', () => {
    // Bug that would still pass: a guard that is never released — covered by the
    // next test.
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Open full dashboard' }))
    expect(screen.getByRole('button', { name: 'Minimize dashboard' })).toBeInTheDocument()

    // Desktop: the host still reports inline while the widget shows fullscreen
    hostSetGlobals('inline')
    hostSetGlobals('inline')

    expect(screen.getByRole('button', { name: 'Minimize dashboard' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Open full dashboard' })).not.toBeInTheDocument()
  })

  it('after the user minimizes, host syncs apply again', () => {
    // Bug that would still pass: a guard that also blocks host 'fullscreen' syncs while
    // set — not exercised (the guard only checks hostMode === 'inline').
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Open full dashboard' }))
    fireEvent.click(screen.getByRole('button', { name: 'Minimize dashboard' }))
    expect(screen.getByRole('button', { name: 'Open full dashboard' })).toBeInTheDocument()

    // Guard released: a host fullscreen sync is followed, then a host inline sync too
    hostSetGlobals('fullscreen')
    expect(screen.getByRole('button', { name: 'Minimize dashboard' })).toBeInTheDocument()
    hostSetGlobals('inline')
    expect(screen.getByRole('button', { name: 'Open full dashboard' })).toBeInTheDocument()
  })
})
