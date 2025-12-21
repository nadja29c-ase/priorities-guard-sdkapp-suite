import '@testing-library/jest-dom'
import { vi, afterEach } from 'vitest'

// Typed toolOutput structure (loose but structural)
type ToolOutput = {
  structuredContent?: { clusters?: unknown[] }
} | undefined

// Mock window.openai
const mockOpenai = {
  theme: 'light' as 'light' | 'dark' | undefined,
  toolOutput: undefined as ToolOutput,
  callTool: vi.fn(),
}

Object.defineProperty(window, 'openai', {
  value: mockOpenai,
  writable: true,
})

// Helper to set mock clusters
export function setMockClusters(clusters: unknown[]) {
  mockOpenai.toolOutput = {
    structuredContent: {
      clusters,
    },
  }
}

// Helper to reset mocks
export function resetMocks() {
  mockOpenai.toolOutput = undefined
  mockOpenai.theme = 'light'
  mockOpenai.callTool.mockReset()
  document.documentElement.removeAttribute('data-theme')
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
