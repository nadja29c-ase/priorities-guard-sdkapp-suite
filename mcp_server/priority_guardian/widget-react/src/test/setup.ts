import '@testing-library/jest-dom'
import { vi, afterEach } from 'vitest'
import type { Priority, ToolOutputData, TimeAllocation } from '../types'

// Typed toolOutput structure (loose but structural)
type ToolOutput = {
  structuredContent?: { data?: ToolOutputData }
} | undefined

// Mock window.openai
const mockOpenai = {
  theme: 'light' as 'light' | 'dark' | undefined,
  locale: 'en-US' as string | undefined,
  toolOutput: undefined as ToolOutput,
  callTool: vi.fn(),
  openExternal: vi.fn(),
  notifyIntrinsicHeight: vi.fn(),
  setWidgetState: vi.fn(),
  widgetState: undefined as Record<string, unknown> | undefined,
}

Object.defineProperty(window, 'openai', {
  value: mockOpenai,
  writable: true,
})

// Helper to set mock priorities
export function setMockPriorities(
  priorities: Priority[],
  googleConnected = false,
  availableKeywords: string[] = [],
  timeAllocation?: TimeAllocation
) {
  mockOpenai.toolOutput = {
    structuredContent: {
      data: {
        google_connected: googleConnected,
        priorities,
        available_keywords: availableKeywords,
        timeAllocation,
      },
    },
  }
}

// Helper to reset mocks
export function resetMocks() {
  mockOpenai.toolOutput = undefined
  mockOpenai.theme = 'light'
  mockOpenai.locale = 'en-US'
  mockOpenai.callTool.mockReset()
  mockOpenai.openExternal.mockReset()
  mockOpenai.notifyIntrinsicHeight.mockReset()
  mockOpenai.setWidgetState.mockReset()
  mockOpenai.widgetState = undefined
  document.documentElement.removeAttribute('data-theme')
}

// Helper to set mock locale for i18n testing
export function setMockLocale(locale: string) {
  mockOpenai.locale = locale
}

// Set document theme (what useDocumentTheme reads)
export function setMockDocumentTheme(theme: 'light' | 'dark') {
  document.documentElement.setAttribute('data-theme', theme)
}

// Set window.openai.theme (legacy fallback - use only for fallback tests)
export function setMockOpenaiTheme(theme: 'light' | 'dark') {
  mockOpenai.theme = theme
}

// Cleanup after each test to prevent state leakage
afterEach(() => {
  resetMocks()
})

// Export mock for direct access
export { mockOpenai }
