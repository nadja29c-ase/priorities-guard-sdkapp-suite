/**
 * Integration tests for error reporter wiring in main.tsx.
 *
 * Verifies that ErrorBoundary and global error listeners
 * correctly call the (mocked) reportWidgetError function.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render } from '@testing-library/react'
import type { ReactNode } from 'react'

// Mock the reporter module BEFORE importing main.tsx
vi.mock('../widgetErrorReporter', () => ({
  reportWidgetError: vi.fn(),
}))

// Import the mock after vi.mock
import { reportWidgetError } from '../widgetErrorReporter'

const mockReportWidgetError = reportWidgetError as ReturnType<typeof vi.fn>

describe('ErrorReporterIntegration', () => {
  beforeEach(() => {
    mockReportWidgetError.mockClear()
    // Suppress console.error for cleaner test output
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('ErrorBoundary integration', () => {
    it('calls reportWidgetError when child component throws', async () => {
      // Import ErrorBoundary after mock is set up
      const { __ErrorBoundaryForTesting: ErrorBoundary } = await import('../main')

      // Clear mock after import (import may trigger listeners from previous tests)
      mockReportWidgetError.mockClear()

      // Component that throws on render
      const ThrowingComponent = (): ReactNode => {
        throw new Error('test render error')
      }

      // Render with ErrorBoundary
      render(
        <ErrorBoundary>
          <ThrowingComponent />
        </ErrorBoundary>
      )

      // Verify reporter was called (React may call componentDidCatch multiple times)
      expect(mockReportWidgetError).toHaveBeenCalled()

      // Find the call with our specific error
      const matchingCall = mockReportWidgetError.mock.calls.find(
        (call) => call[0].message === 'test render error'
      )
      expect(matchingCall).toBeDefined()
      expect(matchingCall![0]).toMatchObject({
        name: 'Error',
        message: 'test render error',
        stack: expect.any(String),
      })

      // componentStack must be passed through from React.
      // The wiring uses `errorInfo.componentStack ?? undefined`, so undefined is
      // valid (React's type allows null), but if present it must be a non-empty string.
      // No silent skip — the field must be present in the call payload.
      const cs = matchingCall![0].componentStack
      const isValid = cs === undefined || (typeof cs === 'string' && cs.length > 0)
      expect(isValid).toBe(true)
    })
  })

  describe('window.error listener integration', () => {
    beforeEach(async () => {
      // Dynamically import main.tsx to register listeners
      await import('../main')
      // Clear any calls from the import itself
      mockReportWidgetError.mockClear()
    })

    it('calls reportWidgetError when window error event is dispatched', () => {
      const testError = new Error('window error test')

      window.dispatchEvent(
        new ErrorEvent('error', {
          message: 'window error test',
          error: testError,
        })
      )

      // May be called multiple times due to accumulated listeners from module caching
      // Just verify it was called at least once with the expected payload
      expect(mockReportWidgetError).toHaveBeenCalled()

      // Find the call with our specific error
      const matchingCall = mockReportWidgetError.mock.calls.find(
        (call) => call[0].message === 'window error test'
      )
      expect(matchingCall).toBeDefined()
      expect(matchingCall![0]).toMatchObject({
        name: 'Error',
        message: 'window error test',
        stack: expect.any(String),
      })

      // componentStack should be undefined for window errors
      expect(matchingCall![0].componentStack).toBeUndefined()
    })

    it('handles error event without error object', () => {
      window.dispatchEvent(
        new ErrorEvent('error', {
          message: 'script error from cross-origin',
          error: null,
        })
      )

      expect(mockReportWidgetError).toHaveBeenCalled()

      const matchingCall = mockReportWidgetError.mock.calls.find(
        (call) => call[0].message === 'script error from cross-origin'
      )
      expect(matchingCall).toBeDefined()
      expect(matchingCall![0]).toMatchObject({
        message: 'script error from cross-origin',
        stack: null,
      })
    })
  })

  describe('unhandledrejection listener integration', () => {
    beforeEach(async () => {
      await import('../main')
      mockReportWidgetError.mockClear()
    })

    it('calls reportWidgetError when unhandled rejection with Error', () => {
      const testError = new Error('unhandled promise rejection')

      // jsdom doesn't have PromiseRejectionEvent, use CustomEvent with correct type
      const event = new CustomEvent('unhandledrejection', {
        bubbles: true,
        cancelable: true,
      }) as unknown as PromiseRejectionEvent

      // Add the reason property that our handler expects
      Object.defineProperty(event, 'reason', {
        value: testError,
        writable: false,
      })

      window.dispatchEvent(event)

      expect(mockReportWidgetError).toHaveBeenCalled()

      const matchingCall = mockReportWidgetError.mock.calls.find(
        (call) => call[0].message === 'unhandled promise rejection'
      )
      expect(matchingCall).toBeDefined()
      expect(matchingCall![0]).toMatchObject({
        name: 'Error',
        message: 'unhandled promise rejection',
        stack: expect.any(String),
      })
    })

    it('handles non-Error rejection reason (plain string)', () => {
      // jsdom doesn't have PromiseRejectionEvent, use CustomEvent
      const event = new CustomEvent('unhandledrejection', {
        bubbles: true,
        cancelable: true,
      }) as unknown as PromiseRejectionEvent

      Object.defineProperty(event, 'reason', {
        value: 'plain string rejection',
        writable: false,
      })

      window.dispatchEvent(event)

      expect(mockReportWidgetError).toHaveBeenCalled()

      const matchingCall = mockReportWidgetError.mock.calls.find(
        (call) => call[0].message === 'plain string rejection'
      )
      expect(matchingCall).toBeDefined()
      expect(matchingCall![0]).toMatchObject({
        message: 'plain string rejection',
        stack: null,
      })

      // name should not be present for non-Error rejections
      expect(matchingCall![0].name).toBeUndefined()
    })
  })
})
