/**
 * Unit tests for widgetErrorReporter module.
 *
 * Tests the reporter logic: URL, payload shape, keepalive, truncation,
 * per-session cap, deduplication, and silent failure.
 */

import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import {
  reportWidgetError,
  reportWidgetDiagnostic,
  __resetReporterStateForTesting,
} from '../widgetErrorReporter'

const EXPECTED_URL =
  'https://priorities-guard-sdkapp-suite.onrender.com/api/priority-guardian/widget-error'

describe('widgetErrorReporter', () => {
  let mockFetch: Mock

  beforeEach(() => {
    __resetReporterStateForTesting()
    mockFetch = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', mockFetch)
  })

  it('sends POST to correct URL', async () => {
    await reportWidgetError({ name: 'Error', message: 'test' })

    expect(mockFetch).toHaveBeenCalledTimes(1)
    expect(mockFetch.mock.calls[0][0]).toBe(EXPECTED_URL)
  })

  it('sends correct payload shape', async () => {
    await reportWidgetError({
      name: 'TypeError',
      message: 'x is not a function',
      stack: 'at foo (bar.js:1)',
      componentStack: '\n    at App\n    at ErrorBoundary',
    })

    const [, options] = mockFetch.mock.calls[0]
    const body = JSON.parse(options.body)

    expect(body).toEqual({
      name: 'TypeError',
      message: 'x is not a function',
      stack: 'at foo (bar.js:1)',
      componentStack: '\n    at App\n    at ErrorBoundary',
      ua: navigator.userAgent,
    })
  })

  it('uses keepalive: true', async () => {
    await reportWidgetError({ name: 'Error', message: 'test' })

    const [, options] = mockFetch.mock.calls[0]
    expect(options.keepalive).toBe(true)
  })

  it('sends Content-Type: application/json header', async () => {
    await reportWidgetError({ name: 'Error', message: 'test' })

    const [, options] = mockFetch.mock.calls[0]
    expect(options.headers).toEqual({ 'Content-Type': 'application/json' })
  })

  it('truncates stack to 2000 characters', async () => {
    const longStack = 'x'.repeat(5000)
    await reportWidgetError({ name: 'Error', message: 'test', stack: longStack })

    const [, options] = mockFetch.mock.calls[0]
    const body = JSON.parse(options.body)

    expect(body.stack.length).toBe(2000)
    expect(body.stack).toBe('x'.repeat(2000))
  })

  it('truncates componentStack to 2000 characters', async () => {
    const longComponentStack = 'y'.repeat(5000)
    await reportWidgetError({
      name: 'Error',
      message: 'test',
      componentStack: longComponentStack,
    })

    const [, options] = mockFetch.mock.calls[0]
    const body = JSON.parse(options.body)

    expect(body.componentStack.length).toBe(2000)
    expect(body.componentStack).toBe('y'.repeat(2000))
  })

  it('swallows fetch rejection without throwing', async () => {
    mockFetch.mockRejectedValue(new Error('network error'))

    // Should not throw
    await expect(
      reportWidgetError({ name: 'Error', message: 'test' })
    ).resolves.toBeUndefined()
  })

  it('enforces per-session cap of 10 reports with distinct messages', async () => {
    // Send 11 distinct error messages
    for (let i = 1; i <= 11; i++) {
      await reportWidgetError({ name: 'Error', message: `error ${i}` })
    }

    // Only first 10 should have been sent
    expect(mockFetch).toHaveBeenCalledTimes(10)
  })

  it('enforces deduplication by name+message', async () => {
    // Same error 5 times
    for (let i = 0; i < 5; i++) {
      await reportWidgetError({ name: 'TypeError', message: 'same error' })
    }

    // Should only send once
    expect(mockFetch).toHaveBeenCalledTimes(1)
  })

  it('cap and dedup interaction: 5 distinct messages each repeated 3 times', async () => {
    // 5 distinct errors, each called 3 times = 15 total calls
    for (let round = 0; round < 3; round++) {
      for (let i = 1; i <= 5; i++) {
        await reportWidgetError({ name: 'Error', message: `distinct ${i}` })
      }
    }

    // Dedup wins: only 5 unique errors sent (cap of 10 never reached)
    expect(mockFetch).toHaveBeenCalledTimes(5)
  })

  it('handles non-Error rejection-style payload with null stack', async () => {
    await reportWidgetError({
      name: undefined,
      message: 'plain string rejection',
      stack: null,
    })

    const [, options] = mockFetch.mock.calls[0]
    const body = JSON.parse(options.body)

    // null stack should not appear in body (undefined is omitted in JSON)
    expect(body.message).toBe('plain string rejection')
    expect(body.stack).toBeUndefined()
    expect(body.name).toBeUndefined()
  })

  it('uses custom ua when provided in payload', async () => {
    await reportWidgetError({ message: 'x', ua: 'custom-ua-string' })

    const [, options] = mockFetch.mock.calls[0]
    const body = JSON.parse(options.body)

    expect(body.ua).toBe('custom-ua-string')
  })

  it('omits undefined fields from payload', async () => {
    await reportWidgetError({
      message: 'only message',
    })

    const [, options] = mockFetch.mock.calls[0]
    const body = JSON.parse(options.body)

    expect(body).toEqual({
      message: 'only message',
      ua: navigator.userAgent,
    })
    expect('name' in body).toBe(false)
    expect('stack' in body).toBe(false)
    expect('componentStack' in body).toBe(false)
  })
})

// ============ reportWidgetDiagnostic tests (Inc 89 / 89.8) ============
// Inc 89.8: Routes through window.openai.callTool() instead of fetch()

// We need to declare the openai property once as configurable at module level,
// then we can reassign it in tests.
const windowWithOpenai = window as Window & { openai?: unknown }

describe('reportWidgetDiagnostic (Inc 89.8 - callTool)', () => {
  let mockCallTool: Mock

  beforeEach(() => {
    __resetReporterStateForTesting()
    mockCallTool = vi.fn().mockResolvedValue({ success: true })
    windowWithOpenai.openai = { callTool: mockCallTool }
  })

  it('calls window.openai.callTool with correct tool name', async () => {
    await reportWidgetDiagnostic({ event: 'mount' })

    expect(mockCallTool).toHaveBeenCalledTimes(1)
    expect(mockCallTool.mock.calls[0][0]).toBe('record_widget_diagnostic')
  })

  it('sends correct payload shape with data', async () => {
    await reportWidgetDiagnostic({
      event: 'displayMode.change',
      data: { caller: 'test', next: 'fullscreen' },
    })

    const args = mockCallTool.mock.calls[0][1]

    expect(args.event).toBe('displayMode.change')
    expect(args.data).toEqual({ caller: 'test', next: 'fullscreen' })
    expect(args.ts).toBeTypeOf('number')
    expect(args.ua).toBe(navigator.userAgent)
  })

  it('enforces per-session cap of 200 diagnostics', async () => {
    // Send 201 diagnostic events
    for (let i = 1; i <= 201; i++) {
      await reportWidgetDiagnostic({ event: `event-${i}` })
    }

    // Only first 200 should have been sent
    expect(mockCallTool).toHaveBeenCalledTimes(200)
  })

  it('does NOT dedup same events (unlike error reporter)', async () => {
    // Same event 5 times
    for (let i = 0; i < 5; i++) {
      await reportWidgetDiagnostic({ event: 'mount' })
    }

    // Should send all 5 (no dedup)
    expect(mockCallTool).toHaveBeenCalledTimes(5)
  })

  it('swallows callTool rejection without throwing', async () => {
    mockCallTool.mockRejectedValue(new Error('host error'))

    // Should not throw
    await expect(
      reportWidgetDiagnostic({ event: 'test' })
    ).resolves.toBeUndefined()
  })

  it('skips silently when window.openai is undefined', async () => {
    windowWithOpenai.openai = undefined

    // Should not throw, should not call anything
    await expect(
      reportWidgetDiagnostic({ event: 'test' })
    ).resolves.toBeUndefined()
  })

  it('skips silently when window.openai exists but callTool is undefined', async () => {
    windowWithOpenai.openai = {}

    // Should not throw
    await expect(
      reportWidgetDiagnostic({ event: 'test' })
    ).resolves.toBeUndefined()
  })

  it('__resetReporterStateForTesting resets diagnosticCount', async () => {
    // Send 15 diagnostics (under cap)
    for (let i = 0; i < 15; i++) {
      await reportWidgetDiagnostic({ event: `event-${i}` })
    }
    expect(mockCallTool).toHaveBeenCalledTimes(15)

    // Reset state
    __resetReporterStateForTesting()
    mockCallTool.mockClear()

    // Should be able to send 20 more
    for (let i = 0; i < 20; i++) {
      await reportWidgetDiagnostic({ event: `event-${i}` })
    }
    expect(mockCallTool).toHaveBeenCalledTimes(20)
  })

  it('defaults data to empty object when not provided', async () => {
    await reportWidgetDiagnostic({ event: 'mount' })

    const args = mockCallTool.mock.calls[0][1]

    expect(args.data).toEqual({})
  })
})
