/**
 * Unit tests for widgetErrorReporter module.
 *
 * Tests the reporter logic: URL, payload shape, keepalive, truncation,
 * per-session cap, deduplication, and silent failure.
 */

import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import {
  reportWidgetError,
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
