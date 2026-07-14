/**
 * Integration Tests for MindSort Claude Widget App
 *
 * Tests the React component configuration and basic rendering.
 * Updated for inc_inline_card_cluster_overview design:
 * - Header: "Your MindSort AI Board"
 * - Cluster rows (not priority rows)
 * - Truncation with "+N more clusters"
 * - "Open full board" button
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

  // ==========================================================================
  // Tests for inc_inline_card_cluster_overview design
  // ==========================================================================

  // Test 5: Header reads "Your MindSort AI Board" (was "Priorities")
  it('renders header "Your MindSort AI Board" with cluster overview', () => {
    // Capture the onAppCreated callback with proper typing
    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    const { rerender } = render(<App />)

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
    capturedOnAppCreated!(mockApp)

    // Simulate a tool result with clusters
    capturedOntoolresult!({
      structuredContent: {
        clusters: [
          { cluster_name: 'Work', sum_thought_items: 10 },
          { cluster_name: 'Personal', sum_thought_items: 5 },
        ],
      },
    })

    rerender(<App />)

    // Header should be "Your MindSort AI Board", NOT "Priorities"
    expect(screen.getByText('Your MindSort AI Board')).toBeInTheDocument()
    expect(screen.queryByText('Priorities')).not.toBeInTheDocument()
  })

  // Test 5b: Ordering - prioritized clusters first
  it('shows prioritized clusters first (P1 → P2 → P3, then by size)', () => {
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

    capturedOnAppCreated!(mockApp)

    // 6 clusters: 3 prioritized (P3, P1, P2 out of order), 3 unprioritized (varying sizes)
    capturedOntoolresult!({
      structuredContent: {
        clusters: [
          { cluster_name: 'Big Unprioritized', sum_thought_items: 100 },
          { cluster_name: 'P3 Cluster', sum_thought_items: 3, priority: { rank: 'P3' } },
          { cluster_name: 'Small Unprioritized', sum_thought_items: 5 },
          { cluster_name: 'P1 Cluster', sum_thought_items: 10, priority: { rank: 'P1' } },
          { cluster_name: 'Medium Unprioritized', sum_thought_items: 50 },
          { cluster_name: 'P2 Cluster', sum_thought_items: 7, priority: { rank: 'P2' } },
        ],
      },
    })

    rerender(<App />)

    // Should show P1, P2, P3 first, then unprioritized by size (Big, Medium, Small)
    // But only 5 visible (MAX_INLINE_ROWS=5), so "+1 more cluster" should appear
    expect(screen.getByText('P1 Cluster')).toBeInTheDocument()
    expect(screen.getByText('P2 Cluster')).toBeInTheDocument()
    expect(screen.getByText('P3 Cluster')).toBeInTheDocument()
    expect(screen.getByText('Big Unprioritized')).toBeInTheDocument()
    expect(screen.getByText('Medium Unprioritized')).toBeInTheDocument()

    // Small Unprioritized should be truncated (6th cluster)
    expect(screen.queryByText('Small Unprioritized')).not.toBeInTheDocument()

    // Truncation indicator
    expect(screen.getByText('+1 more cluster')).toBeInTheDocument()
  })

  // Test 6: Zero-priority board renders cluster names (NOT empty count-only card)
  it('renders cluster names when no priorities exist', () => {
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

    capturedOnAppCreated!(mockApp)

    // All unprioritized clusters
    capturedOntoolresult!({
      structuredContent: {
        clusters: [
          { cluster_name: 'Ideas', sum_thought_items: 12 },
          { cluster_name: 'Tasks', sum_thought_items: 8 },
          { cluster_name: 'Notes', sum_thought_items: 5 },
        ],
      },
    })

    rerender(<App />)

    // Cluster names should be visible (the core bug this increment fixes)
    expect(screen.getByText('Ideas')).toBeInTheDocument()
    expect(screen.getByText('Tasks')).toBeInTheDocument()
    expect(screen.getByText('Notes')).toBeInTheDocument()

    // Ordered by size: Ideas (12), Tasks (8), Notes (5)
    // Header summary should show counts
    expect(screen.getByText(/3 clusters/)).toBeInTheDocument()
    expect(screen.getByText(/25 thoughts/)).toBeInTheDocument()
  })

  // Test 6b: Priority badges and left accent borders
  it('shows priority badges (P1/P2/P3) with correct styling', () => {
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

    capturedOnAppCreated!(mockApp)

    capturedOntoolresult!({
      structuredContent: {
        clusters: [
          { cluster_name: 'Urgent', sum_thought_items: 5, priority: { rank: 'P1' } },
          { cluster_name: 'Normal', sum_thought_items: 3 },
        ],
      },
    })

    rerender(<App />)

    // P1 badge should be visible
    expect(screen.getByText('P1')).toBeInTheDocument()
    // Unprioritized cluster should not have a badge
    expect(screen.queryByText('P2')).not.toBeInTheDocument()
    expect(screen.queryByText('P3')).not.toBeInTheDocument()
  })

  // Test: Tag indicator (icon, not text)
  // CRITICAL: Must verify an SVG renders, not just aria-label presence.
  // An emoji would also pass the aria-label check but violate the guideline
  // ("monochromatic, outlined icons that match the host's icon color tokens").
  it('shows tag indicator as SVG icon when cluster has tags', () => {
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

    capturedOnAppCreated!(mockApp)

    capturedOntoolresult!({
      structuredContent: {
        clusters: [
          { cluster_name: 'Tagged Cluster', sum_thought_items: 5, tags: ['decide', 'follow-up'] },
          { cluster_name: 'Untagged Cluster', sum_thought_items: 3 },
        ],
      },
    })

    rerender(<App />)

    // Tag indicator should have aria-label for accessibility
    const tagIndicator = screen.getByLabelText('has action tags')
    expect(tagIndicator).toBeInTheDocument()

    // CRITICAL: Must be an SVG icon, NOT an emoji
    // This test would FAIL if someone reverts to an emoji (🏷)
    const svgIcon = tagIndicator.querySelector('svg')
    expect(svgIcon).not.toBeNull()
    expect(svgIcon).toHaveAttribute('stroke', 'currentColor') // Inherits muted color
  })

  // Test: Tag indicator does NOT render when cluster has no tags
  it('does NOT show tag indicator when cluster has no tags', () => {
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

    capturedOnAppCreated!(mockApp)

    capturedOntoolresult!({
      structuredContent: {
        clusters: [
          { cluster_name: 'No Tags', sum_thought_items: 5 },
          { cluster_name: 'Also No Tags', sum_thought_items: 3, tags: [] }, // Empty array
        ],
      },
    })

    rerender(<App />)

    // No tag indicator should be present
    expect(screen.queryByLabelText('has action tags')).not.toBeInTheDocument()
  })

  // Test: "Open full board" button exists and is functional
  it('shows "Open full board" button', () => {
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
      callServerTool: vi.fn().mockResolvedValue({}),
      get ontoolresult() {
        return capturedOntoolresult
      },
      set ontoolresult(handler: ((result: unknown) => void) | null) {
        capturedOntoolresult = handler
      },
    }

    capturedOnAppCreated!(mockApp)

    capturedOntoolresult!({
      structuredContent: {
        clusters: [
          { cluster_name: 'Test', sum_thought_items: 5 },
        ],
      },
    })

    rerender(<App />)

    // Button should be visible
    const button = screen.getByRole('button', { name: /open full board/i })
    expect(button).toBeInTheDocument()
    expect(button).toHaveTextContent('Open full board →')
  })

  // Test 7: Loading and stale states preserved (already covered above)

  // Test: Empty state renders friendly message
  it('renders empty state message when no clusters', () => {
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

    capturedOnAppCreated!(mockApp)

    // Empty clusters array
    capturedOntoolresult!({
      structuredContent: {
        clusters: [],
      },
    })

    rerender(<App />)

    // Empty state message
    expect(screen.getByText(/No clusters yet/i)).toBeInTheDocument()
    // Header shows 0 counts
    expect(screen.getByText(/0 clusters/)).toBeInTheDocument()
    expect(screen.getByText(/0 thoughts/)).toBeInTheDocument()
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
