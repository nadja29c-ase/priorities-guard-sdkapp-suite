import '@testing-library/jest-dom'
import { vi } from 'vitest'

// Mock window.openai
const mockOpenai = {
  theme: 'light' as 'light' | 'dark',
  toolOutput: undefined as unknown,
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
}

// Helper to set theme
export function setMockTheme(theme: 'light' | 'dark') {
  mockOpenai.theme = theme
  document.documentElement.setAttribute('data-theme', theme)
}

// Export mock for direct access
export { mockOpenai }
