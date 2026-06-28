/**
 * Integration Tests for MindSort Claude Widget App
 *
 * Tests the React component configuration and basic rendering.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import App from '../App'

// Type for the mock app instance
interface MockApp {
  getHostContext: () => { displayMode: string }
  ontoolresult: ((result: unknown) => void) | null
  callServerTool?: ReturnType<typeof vi.fn>
  requestDisplayMode?: ReturnType<typeof vi.fn>
}

// Type for useApp config (minimal subset needed for tests)
interface UseAppConfig {
  appInfo: { name: string; version: string }
  capabilities: { availableDisplayModes: string[] }
  onAppCreated: (app: MockApp) => void
}

// Mock @modelcontextprotocol/ext-apps/react
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const mockUseApp = vi.fn((_config?: any) => ({ app: null as MockApp | null }))
const mockUseHostStyles = vi.fn()

vi.mock('@modelcontextprotocol/ext-apps/react', () => ({
  useApp: (config: UseAppConfig) => mockUseApp(config),
  useHostStyles: (...args: unknown[]) => mockUseHostStyles(...args),
}))

describe('App Component', () => {
  beforeEach(() => {
    mockUseApp.mockReset()
    mockUseHostStyles.mockReset()
    // Default: return app: null (not connected)
    mockUseApp.mockReturnValue({ app: null })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // Test 9: Mount + bridge - loading state
  it('shows loading state when not initialized', () => {
    render(<App />)
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  // Test 12: Inline-only capabilities - CRITICAL
  it('declares availableDisplayModes as ["inline"] only', () => {
    render(<App />)

    expect(mockUseApp).toHaveBeenCalled()
    const config = mockUseApp.mock.calls[0][0]

    expect(config.capabilities.availableDisplayModes).toEqual(['inline'])
  })

  it('does NOT include fullscreen in capabilities', () => {
    render(<App />)

    const config = mockUseApp.mock.calls[0][0]

    // Critical: Must NOT advertise fullscreen (would be half-wired control)
    expect(config.capabilities.availableDisplayModes).not.toContain('fullscreen')
    expect(config.capabilities.availableDisplayModes).not.toContain('pip')
  })

  it('declares correct appInfo', () => {
    render(<App />)

    const config = mockUseApp.mock.calls[0][0]

    expect(config.appInfo.name).toBe('MindSort')
    expect(config.appInfo.version).toBe('1.0.0')
  })

  it('provides onAppCreated callback', () => {
    render(<App />)

    const config = mockUseApp.mock.calls[0][0]

    expect(typeof config.onAppCreated).toBe('function')
  })

  // Test 10: Theming (useHostStyles is called)
  it('calls useHostStyles for host theming', () => {
    render(<App />)

    expect(mockUseHostStyles).toHaveBeenCalled()
  })

  // Test: No CRUD methods (read-only widget)
  it('does not call callServerTool (no CRUD)', () => {
    const mockApp: MockApp = {
      getHostContext: () => ({ displayMode: 'inline' }),
      callServerTool: vi.fn(),
      ontoolresult: null,
    }

    mockUseApp.mockReturnValue({ app: mockApp })

    render(<App />)

    // Widget should not initiate any CRUD calls
    expect(mockApp.callServerTool).not.toHaveBeenCalled()
  })

  // Test: No requestDisplayMode call (inline-only, no fullscreen toggle)
  it('does not call requestDisplayMode (inline-only)', () => {
    const mockApp: MockApp = {
      getHostContext: () => ({ displayMode: 'inline' }),
      requestDisplayMode: vi.fn(),
      ontoolresult: null,
    }

    mockUseApp.mockReturnValue({ app: mockApp })

    render(<App />)

    expect(mockApp.requestDisplayMode).not.toHaveBeenCalled()
  })

  // CRITICAL: Stale bridge shows BEFORE loading (guard ordering fix)
  it('shows stale session overlay after 3s timeout with no bridge', async () => {
    vi.useFakeTimers()

    mockUseApp.mockReturnValue({ app: null })

    render(<App />)

    // Initially shows loading (bridge hasn't timed out yet)
    expect(screen.getByText('Loading...')).toBeInTheDocument()
    expect(screen.queryByText('Session expired')).not.toBeInTheDocument()

    // Advance past the 3s stale timeout
    await act(async () => {
      vi.advanceTimersByTime(3100)
    })

    // NOW should show stale overlay, NOT loading
    // This is the critical test: stale guard must come BEFORE loading guard
    expect(screen.getByText('Session expired')).toBeInTheDocument()
    expect(screen.queryByText('Loading...')).not.toBeInTheDocument()

    vi.useRealTimers()
  })

  // Gap 2: ontoolresult → render path (proves clusters produce summary)
  it('renders priority summary when ontoolresult receives clusters', () => {
    // Capture the onAppCreated callback with proper typing
    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    const { rerender } = render(<App />)

    // Initially shows loading
    expect(screen.getByText('Loading...')).toBeInTheDocument()

    // Create a mock app with ontoolresult that we can capture
    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockApp: MockApp = {
      getHostContext: () => ({ displayMode: 'inline' }),
      get ontoolresult() {
        return capturedOntoolresult
      },
      set ontoolresult(handler: ((result: unknown) => void) | null) {
        capturedOntoolresult = handler
      },
    }

    // Invoke onAppCreated to register the ontoolresult handler
    // Non-null assertion: render() above captured this callback
    capturedOnAppCreated!(mockApp)

    // Simulate a tool result with clusters
    // Non-null assertion: onAppCreated above set the ontoolresult handler
    capturedOntoolresult!({
      structuredContent: {
        clusters: [
          {
            cluster_name: 'Work',
            sum_thought_items: 10,
            priority: { rank: 'P1' },
          },
          {
            cluster_name: 'Personal',
            sum_thought_items: 5,
          },
        ],
      },
    })

    // Need to rerender to see state updates
    rerender(<App />)

    // Verify summary renders with priority data
    expect(screen.getByText('Priorities')).toBeInTheDocument()
    expect(screen.getByText('Work')).toBeInTheDocument()
    expect(screen.getByText('P1')).toBeInTheDocument()
    // Count line: 2 clusters, 15 thoughts
    expect(screen.getByText(/2 clusters/)).toBeInTheDocument()
    expect(screen.getByText(/15 thoughts/)).toBeInTheDocument()
  })

  // Gap 2b: Empty state renders correctly
  it('renders empty state when clusters have no priorities', () => {
    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    const { rerender } = render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockApp: MockApp = {
      getHostContext: () => ({ displayMode: 'inline' }),
      get ontoolresult() {
        return capturedOntoolresult
      },
      set ontoolresult(handler: ((result: unknown) => void) | null) {
        capturedOntoolresult = handler
      },
    }

    // Non-null assertions: render() captured these callbacks
    capturedOnAppCreated!(mockApp)
    capturedOntoolresult!({
      structuredContent: {
        clusters: [
          { cluster_name: 'Unprioritized', sum_thought_items: 7 },
        ],
      },
    })

    rerender(<App />)

    // Empty state shows count line with "none prioritized yet"
    expect(screen.getByText(/none prioritized yet/)).toBeInTheDocument()
    expect(screen.getByText(/1 cluster/)).toBeInTheDocument()
    expect(screen.getByText(/7 thoughts/)).toBeInTheDocument()
  })
})

// Source file check: Verify forbidden functions are NOT used
// Using dynamic import check instead of Node fs to avoid type issues
describe('Source file compliance', () => {
  it('utils.ts does NOT export getEffectiveRank', async () => {
    const utils = await import('../utils')
    expect('getEffectiveRank' in utils).toBe(false)
    expect('getEffectiveSubclusterRank' in utils).toBe(false)
  })
})
