import '@testing-library/jest-dom'

// Mock ResizeObserver for jsdom (not available in jsdom environment)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
;(globalThis as any).ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
