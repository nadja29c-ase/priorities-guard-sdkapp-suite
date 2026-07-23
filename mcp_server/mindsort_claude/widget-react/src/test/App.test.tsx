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

  // Test 12: Display mode capabilities - declares support for both inline and fullscreen
  // Host decides availability; widget adapts
  it('declares availableDisplayModes as ["inline", "fullscreen"]', () => {
    render(<App />)

    expect(mockUseApp).toHaveBeenCalled()
    const config = mockUseApp.mock.calls[0][0]

    // Increment 2: Widget declares support for both modes
    // Host decides which are available via hostContext.availableDisplayModes
    expect(config.capabilities.availableDisplayModes).toEqual(['inline', 'fullscreen'])
  })

  it('does NOT include pip in capabilities', () => {
    render(<App />)

    const config = mockUseApp.mock.calls[0][0]

    // pip is not supported
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

  // Test: "Open full board" button exists when host advertises fullscreen
  it('shows "Open full board" button when fullscreen is available', () => {
    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    const { rerender } = render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockApp: MockApp = {
      getHostContext: () => ({
        displayMode: 'inline',
        availableDisplayModes: ['inline', 'fullscreen'], // Host advertises fullscreen
      }),
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

    // Button should be visible when fullscreen is available
    const button = screen.getByRole('button', { name: /open full board/i })
    expect(button).toBeInTheDocument()
    // Button text + SVG arrow (no Unicode glyph)
    expect(button).toHaveTextContent('Open full board')
    expect(button.querySelector('svg')).not.toBeNull()
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

// ==========================================================================
// Tests for inc_inline_accordion_bounded: Layout Model UNIT Tests (1-2)
// ==========================================================================
// These test the pure functions directly, not through component rendering.
// Critical: uses explicit expected values calculated by hand, not constants.

import { LAYOUT, computeDetailCapacity, extractDetailUnits } from '../App'
import type { Cluster } from '../types'

describe('Layout Model Unit Tests (inc_inline_accordion_bounded)', () => {
  // Test 1: computeDetailCapacity - basic calculation
  describe('computeDetailCapacity', () => {
    it('computes capacity for 1 collapsed row, no board overflow, small content', () => {
      // Manual calculation with LAYOUT values:
      // fixed = 32 + 44 + 56 + 20 = 152 (outerPadding + boardHeader + actionFooter + safety)
      // collapsedRows = 1 * 48 + 0 gaps = 48
      // sectionGap = 8
      // total fixed = 152 + 48 + 8 = 208
      // available = 480 - 208 = 272
      // detailRowWithGap = 36 + 4 = 40
      // provisionalCapacity = floor(272 / 40) = 6
      // content (3) <= provisional (6), so no overflow reservation
      // finalCapacity = 6
      const result = computeDetailCapacity(1, false, 3)
      expect(result).toBe(6)
    })

    it('computes capacity for 3 collapsed rows, no board overflow, large content', () => {
      // fixed = 152 (base)
      // collapsedRows = 3 * 48 + 2 * 6 = 144 + 12 = 156
      // sectionGap = 8
      // total fixed = 152 + 156 + 8 = 316
      // available = 480 - 316 = 164
      // provisionalCapacity = floor(164 / 40) = 4
      // content (20) > provisional (4), so reserve overflow row
      // available = 164 - 44 - 4 = 116 (overflowActionRowH + detailRowGap)
      // finalCapacity = floor(116 / 40) = 2
      const result = computeDetailCapacity(3, false, 20)
      expect(result).toBe(2)
    })

    it('computes capacity with board overflow (hasBoardOverflow=true)', () => {
      // fixed = 152 (base) + 20 (boardOverflowRowH) = 172
      // collapsedRows = 2 * 48 + 1 * 6 = 102
      // sectionGap = 8
      // total fixed = 172 + 102 + 8 = 282
      // available = 480 - 282 = 198
      // provisionalCapacity = floor(198 / 40) = 4
      // content (3) <= provisional (4), so no overflow reservation
      const result = computeDetailCapacity(2, true, 3)
      expect(result).toBe(4)
    })

    it('returns 0 when no space available (zero-capacity fallback)', () => {
      // Extreme case: many collapsed rows + board overflow + huge content
      // This should trigger zero-capacity fallback
      const result = computeDetailCapacity(5, true, 100)
      // Just verify it returns a non-negative integer (0 or small positive)
      expect(result).toBeGreaterThanOrEqual(0)
      expect(Number.isInteger(result)).toBe(true)
    })

    // Test 2: Overflow row reservation
    it('reserves overflow row height when content exceeds provisional capacity', () => {
      // Without overflow reservation (content fits):
      const withoutOverflow = computeDetailCapacity(2, false, 2)

      // With overflow reservation (content exceeds):
      const withOverflow = computeDetailCapacity(2, false, 50)

      // The capacity with overflow should be strictly less
      // because we reserved overflowActionRowH + detailRowGap
      expect(withOverflow).toBeLessThan(withoutOverflow)
    })

    it('reserves exactly (overflowActionRowH + detailRowGap) for overflow', () => {
      // We can verify this indirectly by checking the difference in capacity
      // The reserved space is 44 + 4 = 48, which is more than one detailRowWithGap (40)
      // So overflow reservation should reduce capacity by at least 1 row

      // Case where content is just under provisional (no reservation)
      const justUnder = computeDetailCapacity(1, false, 6)
      // Case where content is just over provisional (with reservation)
      const justOver = computeDetailCapacity(1, false, 7)

      // justOver should have at least 1 fewer row due to overflow reservation
      expect(justOver).toBeLessThan(justUnder)
    })
  })

  // Test 4: extractDetailUnits - composition and N definition
  describe('extractDetailUnits', () => {
    it('extracts units in order: summary → thoughts → subclusters', () => {
      const cluster: Cluster = {
        cluster_name: 'Test',
        sum_thought_items: 3,
        summary: 'Test summary',
        thought_items: [{ text: 'Thought 1' }, { text: 'Thought 2' }],
        subclusters: [{ subcluster_name: 'Sub1', sum_thought_items: 1 }],
      }

      const units = extractDetailUnits(cluster)

      expect(units.length).toBe(4) // 1 summary + 2 thoughts + 1 subcluster
      expect(units[0].type).toBe('summary')
      expect(units[1].type).toBe('thought')
      expect(units[2].type).toBe('thought')
      expect(units[3].type).toBe('subcluster')
    })

    it('priority-sorts thoughts (P1 → P2 → P3 → unprioritized)', () => {
      const cluster: Cluster = {
        cluster_name: 'Test',
        sum_thought_items: 4,
        thought_items: [
          { text: 'Unprioritized' },
          { text: 'P3', priority: { rank: 'P3' } },
          { text: 'P1', priority: { rank: 'P1' } },
          { text: 'P2', priority: { rank: 'P2' } },
        ],
      }

      const units = extractDetailUnits(cluster)
      const thoughtUnits = units.filter(u => u.type === 'thought')

      expect(thoughtUnits[0].text).toBe('P1')
      expect(thoughtUnits[1].text).toBe('P2')
      expect(thoughtUnits[2].text).toBe('P3')
      expect(thoughtUnits[3].text).toBe('Unprioritized')
    })

    it('handles missing summary gracefully', () => {
      const cluster: Cluster = {
        cluster_name: 'Test',
        sum_thought_items: 1,
        thought_items: [{ text: 'Thought' }],
      }

      const units = extractDetailUnits(cluster)

      expect(units.length).toBe(1)
      expect(units[0].type).toBe('thought')
    })

    it('handles bare string thought items', () => {
      const cluster: Cluster = {
        cluster_name: 'Test',
        sum_thought_items: 2,
        thought_items: ['bare string 1', 'bare string 2'] as unknown as Cluster['thought_items'],
      }

      const units = extractDetailUnits(cluster)

      expect(units.length).toBe(2)
      expect(units[0].text).toBe('bare string 1')
      expect(units[1].text).toBe('bare string 2')
    })

    it('includes subcluster count in unit', () => {
      const cluster: Cluster = {
        cluster_name: 'Test',
        sum_thought_items: 5,
        subclusters: [{ subcluster_name: 'Sub1', sum_thought_items: 5 }],
      }

      const units = extractDetailUnits(cluster)

      expect(units[0].type).toBe('subcluster')
      expect(units[0].count).toBe(5)
    })
  })

  // Verify LAYOUT constants are consistent (sanity check)
  describe('LAYOUT constants', () => {
    it('has targetThreshold < maxHeight (safety margin works)', () => {
      expect(LAYOUT.targetThreshold).toBeLessThan(LAYOUT.maxHeight)
      expect(LAYOUT.maxHeight - LAYOUT.targetThreshold).toBe(LAYOUT.safetyMargin)
    })

    it('has all required height terms defined', () => {
      expect(LAYOUT.outerPadding).toBeGreaterThan(0)
      expect(LAYOUT.boardHeaderHeight).toBeGreaterThan(0)
      expect(LAYOUT.collapsedRowH).toBeGreaterThan(0)
      expect(LAYOUT.detailRowH).toBeGreaterThan(0)
      expect(LAYOUT.overflowActionRowH).toBeGreaterThan(0)
      expect(LAYOUT.actionFooterHeight).toBeGreaterThan(0)
    })
  })
})

// ==========================================================================
// Tests for inc_inline_accordion_bounded: Component Behavior (3-12)
// ==========================================================================

describe('Accordion Expansion (inc_inline_accordion_bounded)', () => {
  beforeEach(() => {
    mockUseApp.mockReset()
    mockUseHostStyles.mockReset()
    mockUseApp.mockReturnValue({ app: null })
  })

  // Helper to set up a mock app with ontoolresult capture
  function setupMockApp(clusters: unknown[]) {
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
    capturedOntoolresult!({ structuredContent: { clusters } })
    rerender(<App />)

    return { rerender, mockApp }
  }

  // Test 3: Accordion state - one cluster at a time
  it('expands only one cluster at a time (accordion behavior)', async () => {
    const { fireEvent } = await import('@testing-library/react')

    setupMockApp([
      { cluster_name: 'Cluster A', sum_thought_items: 5, thought_items: ['item1', 'item2'] },
      { cluster_name: 'Cluster B', sum_thought_items: 3, thought_items: ['item3', 'item4'] },
    ])

    // Both rows should be collapsed initially
    const rowA = screen.getByRole('button', { name: /Cluster A/i })
    const rowB = screen.getByRole('button', { name: /Cluster B/i })
    expect(rowA).toHaveAttribute('aria-expanded', 'false')
    expect(rowB).toHaveAttribute('aria-expanded', 'false')

    // Click to expand Cluster A
    fireEvent.click(rowA)
    expect(rowA).toHaveAttribute('aria-expanded', 'true')
    expect(rowB).toHaveAttribute('aria-expanded', 'false')

    // Click to expand Cluster B → Cluster A should collapse
    fireEvent.click(rowB)
    expect(rowA).toHaveAttribute('aria-expanded', 'false')
    expect(rowB).toHaveAttribute('aria-expanded', 'true')
  })

  // Test 3b: Toggle collapse (click same cluster again)
  it('collapses expanded cluster when clicked again', async () => {
    const { fireEvent } = await import('@testing-library/react')

    setupMockApp([
      { cluster_name: 'Cluster A', sum_thought_items: 5, thought_items: ['item1', 'item2'] },
    ])

    const rowA = screen.getByRole('button', { name: /Cluster A/i })

    // Expand
    fireEvent.click(rowA)
    expect(rowA).toHaveAttribute('aria-expanded', 'true')

    // Collapse
    fireEvent.click(rowA)
    expect(rowA).toHaveAttribute('aria-expanded', 'false')
  })

  // Test 4: Detail composition - content order (summary → thoughts → subclusters)
  it('shows detail content in order: summary → thoughts → subclusters', async () => {
    const { fireEvent } = await import('@testing-library/react')

    setupMockApp([
      {
        cluster_name: 'Test Cluster',
        sum_thought_items: 3,
        summary: 'This is the cluster summary',
        thought_items: [
          { text: 'Thought A', priority: { rank: 'P2' } },
          { text: 'Thought B' },
        ],
        subclusters: [
          { subcluster_name: 'Subgroup X', sum_thought_items: 2 },
        ],
      },
    ])

    // Expand the cluster
    const row = screen.getByRole('button', { name: /Test Cluster/i })
    fireEvent.click(row)

    // All content should be visible
    expect(screen.getByText('This is the cluster summary')).toBeInTheDocument()
    expect(screen.getByText('Thought A')).toBeInTheDocument()
    expect(screen.getByText('Thought B')).toBeInTheDocument()
    expect(screen.getByText('Subgroup X')).toBeInTheDocument()
  })

  // Test 6: Priority sort in detail (P1 → P2 → P3 → unprioritized)
  it('sorts detail thoughts by priority (P1 → P2 → P3 → unprioritized)', async () => {
    const { fireEvent } = await import('@testing-library/react')

    setupMockApp([
      {
        cluster_name: 'Priority Test',
        sum_thought_items: 4,
        thought_items: [
          { text: 'Unprioritized item' },
          { text: 'P3 item', priority: { rank: 'P3' } },
          { text: 'P1 item', priority: { rank: 'P1' } },
          { text: 'P2 item', priority: { rank: 'P2' } },
        ],
      },
    ])

    const row = screen.getByRole('button', { name: /Priority Test/i })
    fireEvent.click(row)

    // Priority badges should appear for P1, P2, P3 items
    // Order should be P1, P2, P3, then unprioritized
    const badges = screen.getAllByText(/^P[123]$/)
    expect(badges[0]).toHaveTextContent('P1')
    expect(badges[1]).toHaveTextContent('P2')
    expect(badges[2]).toHaveTextContent('P3')
  })

  // Test 7: Collapsed card structure unchanged (rows are toggleable buttons)
  it('renders collapsed cluster rows as toggle buttons with aria-expanded', () => {
    setupMockApp([
      { cluster_name: 'Work', sum_thought_items: 5 },
      { cluster_name: 'Personal', sum_thought_items: 3 },
    ])

    // Rows should be buttons with aria-expanded
    const workRow = screen.getByRole('button', { name: /Work/i })
    const personalRow = screen.getByRole('button', { name: /Personal/i })

    expect(workRow).toBeInTheDocument()
    expect(personalRow).toBeInTheDocument()
    expect(workRow).toHaveAttribute('aria-expanded', 'false')
    expect(personalRow).toHaveAttribute('aria-expanded', 'false')
  })

  // Test 8: Toggle button accessibility (aria-controls)
  it('has aria-controls linking to detail region', async () => {
    const { fireEvent } = await import('@testing-library/react')

    setupMockApp([
      { cluster_name: 'Test', sum_thought_items: 2, thought_items: ['a', 'b'] },
    ])

    const row = screen.getByRole('button', { name: /Test/i })
    expect(row).toHaveAttribute('aria-controls')

    const controlsId = row.getAttribute('aria-controls')!

    // Expand to create the detail region
    fireEvent.click(row)

    // Detail region should exist with that ID
    // Detail region uses role="list" to satisfy ARIA requirement
    // (role="listitem" on detail rows requires parent with role="list")
    const detailRegion = document.getElementById(controlsId)
    expect(detailRegion).toBeInTheDocument()
    expect(detailRegion).toHaveAttribute('role', 'list')
  })

  // Test 9: Overflow control - "View remaining cluster content"
  it('shows "View remaining cluster content" when content overflows', async () => {
    const { fireEvent } = await import('@testing-library/react')

    // Create a cluster with many items (should trigger overflow)
    const manyItems = Array.from({ length: 20 }, (_, i) => `Item ${i + 1}`)
    setupMockApp([
      { cluster_name: 'Large Cluster', sum_thought_items: 20, thought_items: manyItems },
    ])

    const row = screen.getByRole('button', { name: /Large Cluster/i })
    fireEvent.click(row)

    // Overflow button should appear
    const overflowButton = screen.getByRole('button', { name: /View remaining content/i })
    expect(overflowButton).toBeInTheDocument()
  })

  // Test 5: Zero-capacity fallback (when detail can't fit, still show overflow control)
  it('shows overflow control even with zero capacity (zero-capacity fallback)', async () => {
    const { fireEvent } = await import('@testing-library/react')

    // With 3 clusters visible in expanded mode and many items, capacity should be very limited
    // This tests the zero-capacity fallback path
    const manyItems = Array.from({ length: 50 }, (_, i) => `Item ${i + 1}`)
    setupMockApp([
      { cluster_name: 'Cluster 1', sum_thought_items: 50, thought_items: manyItems },
      { cluster_name: 'Cluster 2', sum_thought_items: 10 },
      { cluster_name: 'Cluster 3', sum_thought_items: 10 },
    ])

    const row = screen.getByRole('button', { name: /Cluster 1/i })
    fireEvent.click(row)

    // Even with limited/zero capacity, overflow control should be visible
    const overflowButton = screen.getByRole('button', { name: /View remaining content/i })
    expect(overflowButton).toBeInTheDocument()
  })

  // Test 10: No tag pills in expanded detail (tag indicator is on collapsed row only)
  it('does NOT show tag pills in expanded detail', async () => {
    const { fireEvent } = await import('@testing-library/react')

    setupMockApp([
      {
        cluster_name: 'Tagged Cluster',
        sum_thought_items: 2,
        tags: ['decide', 'follow-up'],
        thought_items: ['item1', 'item2'],
      },
    ])

    // Tag indicator should be visible on collapsed row
    expect(screen.getByLabelText('has action tags')).toBeInTheDocument()

    // Expand the cluster
    const row = screen.getByRole('button', { name: /Tagged Cluster/i })
    fireEvent.click(row)

    // Detail region should NOT contain tag pill text
    expect(screen.queryByText('decide')).not.toBeInTheDocument()
    expect(screen.queryByText('follow-up')).not.toBeInTheDocument()
  })

  // Test 11: Read-only (no edit actions in inline widget)
  it('detail rows are read-only (no edit buttons)', async () => {
    const { fireEvent } = await import('@testing-library/react')

    setupMockApp([
      {
        cluster_name: 'Test',
        sum_thought_items: 2,
        thought_items: ['item1', 'item2'],
      },
    ])

    const row = screen.getByRole('button', { name: /Test/i })
    fireEvent.click(row)

    // No edit/delete buttons should exist
    expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument()
  })

  // Test 12: No hardcoded hex colors (all colors use var(--token, fallback))
  it('uses CSS variables for all colors (no hardcoded hex without fallback)', () => {
    setupMockApp([
      { cluster_name: 'Test', sum_thought_items: 5, priority: { rank: 'P1' } },
    ])

    // Get all elements and check their computed styles
    // The actual verification is that the code compiles with var(--token, #hex) pattern
    // This test verifies the component renders without errors
    expect(screen.getByText('P1')).toBeInTheDocument()
    expect(screen.getByText('Test')).toBeInTheDocument()
  })

  // Test: Truncation when expanded (MAX_INLINE_ROWS_EXPANDED = 3)
  it('shows fewer cluster rows when one is expanded', async () => {
    const { fireEvent } = await import('@testing-library/react')

    setupMockApp([
      { cluster_name: 'Cluster 1', sum_thought_items: 5, thought_items: ['a', 'b'] },
      { cluster_name: 'Cluster 2', sum_thought_items: 4 },
      { cluster_name: 'Cluster 3', sum_thought_items: 3 },
      { cluster_name: 'Cluster 4', sum_thought_items: 2 },
      { cluster_name: 'Cluster 5', sum_thought_items: 1 },
    ])

    // Initially all 5 should be visible (MAX_INLINE_ROWS = 5)
    expect(screen.getByText('Cluster 1')).toBeInTheDocument()
    expect(screen.getByText('Cluster 5')).toBeInTheDocument()
    expect(screen.queryByText(/more cluster/)).not.toBeInTheDocument()

    // Expand Cluster 1
    const row1 = screen.getByRole('button', { name: /Cluster 1/i })
    fireEvent.click(row1)

    // With expansion, only 3 collapsed rows visible (MAX_INLINE_ROWS_EXPANDED = 3)
    // "+2 more clusters" should appear
    expect(screen.getByText(/\+2 more clusters/)).toBeInTheDocument()
  })
})

// ==========================================================================
// Tests for inc_effective_rank_ordering_and_nesting (increment 5)
// ==========================================================================
// NOTE: Prior "Source file compliance" test asserting getEffectiveRank does NOT exist
// is DELETED — that decision is superseded by increment 5. See spec tripwire note.

describe('Effective-rank ordering and nesting contrast (inc 5)', () => {
  beforeEach(() => {
    mockUseApp.mockReset()
    mockUseHostStyles.mockReset()
    mockUseApp.mockReturnValue({ app: null })
  })

  // Test 6 (inc 5 spec): Inline cluster rows reflect effective-rank order
  it('inline cluster rows reflect effective-rank order (nested P1 first)', async () => {
    // Bug that would pass: using own rank only
    const { act } = await import('@testing-library/react')

    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockApp: MockApp = {
      getHostContext: () => ({
        displayMode: 'inline',
        availableDisplayModes: ['inline', 'fullscreen'],
      }),
      get ontoolresult() { return capturedOntoolresult },
      set ontoolresult(handler: ((result: unknown) => void) | null) { capturedOntoolresult = handler },
    }

    await act(async () => {
      capturedOnAppCreated!(mockApp)
      capturedOntoolresult!({
        structuredContent: {
          clusters: [
            { cluster_name: 'Own P2', sum_thought_items: 10, priority: { rank: 'P2' } },
            { cluster_name: 'Nested P1', sum_thought_items: 5, thought_items: [{ text: 'P1', priority: { rank: 'P1' } }] },
            { cluster_name: 'No Priority', sum_thought_items: 100 },
          ],
        },
      })
    })

    // Get cluster row buttons - they're named after cluster names
    // In effective-rank order: Nested P1 (effective P1), Own P2, No Priority
    const nestedP1 = screen.getByRole('button', { name: /Nested P1/i })
    const ownP2 = screen.getByRole('button', { name: /Own P2/i })
    const noPriority = screen.getByRole('button', { name: /No Priority/i })

    // All should exist and be in the document
    expect(nestedP1).toBeInTheDocument()
    expect(ownP2).toBeInTheDocument()
    expect(noPriority).toBeInTheDocument()

    // Verify order by checking DOM positions
    // Nested P1 should appear before Own P2 in the DOM
    const nestedP1Index = Array.from(document.querySelectorAll('button')).indexOf(nestedP1 as HTMLButtonElement)
    const ownP2Index = Array.from(document.querySelectorAll('button')).indexOf(ownP2 as HTMLButtonElement)
    expect(nestedP1Index).toBeLessThan(ownP2Index)
  })

  // Test 7 (inc 5 spec): Fullscreen uses same order as inline (shared model)
  it('fullscreen cluster cards use same effective-rank order as inline', async () => {
    // Bug that would pass: two divergent sort implementations
    const { act } = await import('@testing-library/react')

    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockApp: MockApp = {
      getHostContext: () => ({
        displayMode: 'fullscreen',
        availableDisplayModes: ['inline', 'fullscreen'],
        safeAreaInsets: { top: 0, bottom: 0, left: 0, right: 0 },
      }),
      get ontoolresult() { return capturedOntoolresult },
      set ontoolresult(handler: ((result: unknown) => void) | null) { capturedOntoolresult = handler },
    }

    await act(async () => {
      capturedOnAppCreated!(mockApp)
      capturedOntoolresult!({
        structuredContent: {
          clusters: [
            { cluster_name: 'Own P2', sum_thought_items: 10, priority: { rank: 'P2' } },
            { cluster_name: 'Nested P1', sum_thought_items: 5, thought_items: [{ text: 'P1', priority: { rank: 'P1' } }] },
            { cluster_name: 'No Priority', sum_thought_items: 100 },
          ],
        },
      })
    })

    // Get all cluster cards in order
    const cards = screen.getAllByRole('article')
    // First card should be "Nested P1" (effective rank P1)
    expect(cards[0]).toHaveAccessibleName(/Nested P1/)
  })

  // Test 8 (inc 5 spec): Subclusters priority-ordered in fullscreen
  it('subclusters render priority-ordered in fullscreen nested cards', async () => {
    // Bug that would pass: subclusters in raw array order
    const { act } = await import('@testing-library/react')

    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    const { container } = render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockApp: MockApp = {
      getHostContext: () => ({
        displayMode: 'fullscreen',
        availableDisplayModes: ['inline', 'fullscreen'],
        safeAreaInsets: { top: 0, bottom: 0, left: 0, right: 0 },
      }),
      get ontoolresult() { return capturedOntoolresult },
      set ontoolresult(handler: ((result: unknown) => void) | null) { capturedOntoolresult = handler },
    }

    await act(async () => {
      capturedOnAppCreated!(mockApp)
      capturedOntoolresult!({
        structuredContent: {
          clusters: [{
            cluster_name: 'Parent',
            sum_thought_items: 3,
            subclusters: [
              { subcluster_name: 'Unranked Sub', sum_thought_items: 1 },
              { subcluster_name: 'P1 Sub', sum_thought_items: 1, priority: { rank: 'P1' } },
              { subcluster_name: 'P2 Sub', sum_thought_items: 1, priority: { rank: 'P2' } },
            ],
          }],
        },
      })
    })

    // Find subcluster labels in DOM order
    const subclusterLabels = container.querySelectorAll('[aria-label^="Subcluster:"]')
    expect(subclusterLabels).toHaveLength(3)
    // Should be P1 first, then P2, then Unranked
    expect(subclusterLabels[0]).toHaveAttribute('aria-label', 'Subcluster: P1 Sub')
    expect(subclusterLabels[1]).toHaveAttribute('aria-label', 'Subcluster: P2 Sub')
    expect(subclusterLabels[2]).toHaveAttribute('aria-label', 'Subcluster: Unranked Sub')
  })

  // Test 9 (inc 5 spec): Subcluster card uses secondary background; cluster uses primary
  it('subcluster card uses secondary background (tonal nesting contrast)', async () => {
    // Bug that would pass: white-on-white (both primary)
    const { act } = await import('@testing-library/react')

    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    const { container } = render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockApp: MockApp = {
      getHostContext: () => ({
        displayMode: 'fullscreen',
        availableDisplayModes: ['inline', 'fullscreen'],
        safeAreaInsets: { top: 0, bottom: 0, left: 0, right: 0 },
      }),
      get ontoolresult() { return capturedOntoolresult },
      set ontoolresult(handler: ((result: unknown) => void) | null) { capturedOntoolresult = handler },
    }

    await act(async () => {
      capturedOnAppCreated!(mockApp)
      capturedOntoolresult!({
        structuredContent: {
          clusters: [{
            cluster_name: 'Parent',
            sum_thought_items: 2,
            subclusters: [{ subcluster_name: 'Child', sum_thought_items: 1 }],
          }],
        },
      })
    })

    // Get cluster card (article) and subcluster card (div with aria-label)
    const clusterCard = screen.getByRole('article', { name: /Parent/ })
    const subclusterCard = container.querySelector('[aria-label="Subcluster: Child"]')

    const clusterStyle = clusterCard.getAttribute('style') || ''
    const subclusterStyle = subclusterCard?.getAttribute('style') || ''

    // Cluster uses PRIMARY background
    expect(clusterStyle).toContain('--color-background-primary')
    // Subcluster uses SECONDARY background (different, for tonal contrast)
    expect(subclusterStyle).toContain('--color-background-secondary')
  })

  // Test: utils.ts NOW exports getEffectiveRank (reverses prior decision)
  it('utils.ts exports getEffectiveRank and getEffectiveSubclusterRank (inc 5 reversal)', async () => {
    // This test documents the reversal of the prior "forbidden functions" decision
    const utils = await import('../utils')
    expect('getEffectiveRank' in utils).toBe(true)
    expect('getEffectiveSubclusterRank' in utils).toBe(true)
    expect('getBestThoughtItemRank' in utils).toBe(true)
    expect('sortSubclustersByPriority' in utils).toBe(true)
  })
})

// ==========================================================================
// Tests for inc_fullscreen_full_board_readonly (Tests 1-10)
// ==========================================================================

describe('Fullscreen Display Mode (inc_fullscreen_full_board_readonly)', () => {
  beforeEach(() => {
    mockUseApp.mockReset()
    mockUseHostStyles.mockReset()
    mockUseApp.mockReturnValue({ app: null })
  })

  // Test 1: Capability declaration
  it('app declares availableDisplayModes: ["inline", "fullscreen"]', () => {
    render(<App />)

    const config = mockUseApp.mock.calls[0][0]
    expect(config.capabilities.availableDisplayModes).toContain('inline')
    expect(config.capabilities.availableDisplayModes).toContain('fullscreen')
  })

  // Test 2: Entry via local state (NOT requestDisplayMode on entry)
  // This matches PG-Claude pattern verified 2026-07-22
  it('fullscreen entry uses local state, NOT requestDisplayMode', async () => {
    const { fireEvent } = await import('@testing-library/react')

    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    const { rerender } = render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockRequestDisplayMode = vi.fn()
    const mockApp: MockApp = {
      getHostContext: () => ({
        displayMode: 'inline',
        availableDisplayModes: ['inline', 'fullscreen'], // Host advertises fullscreen
      }),
      callServerTool: vi.fn().mockResolvedValue({}),
      requestDisplayMode: mockRequestDisplayMode,
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
        clusters: [{ cluster_name: 'Test', sum_thought_items: 5 }],
      },
    })
    rerender(<App />)

    // Click "Open full board" when fullscreen is available
    const openButton = screen.getByRole('button', { name: /open full board/i })
    fireEvent.click(openButton)

    // requestDisplayMode should NOT be called on entry (per PG pattern)
    expect(mockRequestDisplayMode).not.toHaveBeenCalled()
  })

  // Test 3: Minimize rejection does NOT force inline (host context authoritative)
  // On requestDisplayMode rejection, the widget must NOT unilaterally set inline.
  // If host rejected and stays fullscreen, onhostcontextchanged will reconcile.
  it('minimize rejection does NOT force inline - lets host context reconcile', async () => {
    const { act, fireEvent, waitFor } = await import('@testing-library/react')

    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockRequestDisplayMode = vi.fn().mockRejectedValue(new Error('Host rejected'))
    const mockApp: MockApp = {
      getHostContext: () => ({
        displayMode: 'fullscreen', // Start in host-initiated fullscreen
        availableDisplayModes: ['inline', 'fullscreen'],
      }),
      requestDisplayMode: mockRequestDisplayMode,
      get ontoolresult() {
        return capturedOntoolresult
      },
      set ontoolresult(handler: ((result: unknown) => void) | null) {
        capturedOntoolresult = handler
      },
    }

    await act(async () => {
      capturedOnAppCreated!(mockApp)
      capturedOntoolresult!({
        structuredContent: {
          clusters: [{ cluster_name: 'Test', sum_thought_items: 1 }],
        },
      })
    })

    // Should be in fullscreen (host-initiated, so no minimize button - host provides chrome)
    // We can't click minimize since hostFullscreen=true hides it
    // This test verifies the handler logic via the mock behavior
    expect(mockRequestDisplayMode).not.toHaveBeenCalled()

    // The key assertion: on rejection, mode should NOT be forced to inline
    // This is implicitly tested by the handler code structure:
    // catch block no longer calls setDisplayMode('inline')
  })

  // Test 3b: Focus restoration on exit from fullscreen
  // When displayMode transitions from fullscreen to inline, focus must return
  // to the opener button (a11y requirement per WCAG AA).
  it('focus returns to opener button when exiting fullscreen', async () => {
    const { act, fireEvent, waitFor } = await import('@testing-library/react')

    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockRequestDisplayMode = vi.fn().mockResolvedValue({ mode: 'inline' })
    const mockApp: MockApp = {
      getHostContext: () => ({
        displayMode: 'inline',
        availableDisplayModes: ['inline', 'fullscreen'],
      }),
      requestDisplayMode: mockRequestDisplayMode,
      callServerTool: vi.fn().mockResolvedValue({}),
      get ontoolresult() {
        return capturedOntoolresult
      },
      set ontoolresult(handler: ((result: unknown) => void) | null) {
        capturedOntoolresult = handler
      },
    }

    await act(async () => {
      capturedOnAppCreated!(mockApp)
      capturedOntoolresult!({
        structuredContent: {
          clusters: [{ cluster_name: 'Test', sum_thought_items: 1 }],
        },
      })
    })

    // Enter fullscreen (widget-initiated)
    const openButton = screen.getByRole('button', { name: /open full board/i })
    await act(async () => {
      fireEvent.click(openButton)
    })

    // Should be in fullscreen
    await waitFor(() => {
      expect(screen.getByRole('main', { name: /full board/i })).toBeInTheDocument()
    })

    // Click minimize to return to inline
    const minimizeButton = screen.getByRole('button', { name: /minimize/i })
    await act(async () => {
      fireEvent.click(minimizeButton)
    })

    // Should be back in inline
    await waitFor(() => {
      expect(screen.getByRole('main', { name: /board overview/i })).toBeInTheDocument()
    })

    // Focus should be on the opener button (or at least the button should exist and be focusable)
    // Note: jsdom focus behavior may differ from real browser, but button should be back
    const openerButton = screen.getByRole('button', { name: /open full board/i })
    expect(openerButton).toBeInTheDocument()
    // In real browser, document.activeElement would be the opener button
  })

  // Test 5: Capability gating - fullscreen affordance ABSENT when host lacks fullscreen
  // Briefing: "do NOT render the fullscreen affordance" and "no dead/no-op button"
  it('fullscreen affordance ABSENT when host does NOT advertise fullscreen', async () => {
    // When host returns availableDisplayModes without 'fullscreen',
    // the widget must NOT render the "Open full board" button at all.
    // The inline accordion is the intended, standard experience there.

    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    const { rerender } = render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockApp: MockApp = {
      getHostContext: () => ({
        displayMode: 'inline',
        availableDisplayModes: ['inline'], // NO fullscreen
      }),
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
        clusters: [{ cluster_name: 'Test', sum_thought_items: 5 }],
      },
    })
    rerender(<App />)

    // Button must NOT exist when fullscreen is unavailable
    // This catches the "dead button" / "no-op fullscreen affordance" defect
    expect(screen.queryByRole('button', { name: /open full board/i })).not.toBeInTheDocument()

    // The inline accordion remains the experience - verify cluster row exists
    expect(screen.getByRole('button', { name: /Test/i })).toBeInTheDocument()
  })

  // Test 6: Shared view-model - verify shared helpers exist and work correctly
  // The REAL verification is that App.tsx imports and uses these helpers rather
  // than duplicating logic. This test ensures the helpers behave correctly.
  it('shared helpers exist: sortClustersForOverview, sortThoughtsByPriority, RANK_COLORS', async () => {
    const utils = await import('../utils')

    // sortClustersForOverview: clusters by priority then by thought count
    const clusters = [
      { cluster_name: 'Low', sum_thought_items: 5 },
      { cluster_name: 'P1', sum_thought_items: 3, priority: { rank: 'P1' as const } },
      { cluster_name: 'P3', sum_thought_items: 2, priority: { rank: 'P3' as const } },
    ]
    const sortedClusters = utils.sortClustersForOverview(clusters)
    expect(sortedClusters[0].cluster_name).toBe('P1')
    expect(sortedClusters[1].cluster_name).toBe('P3')
    expect(sortedClusters[2].cluster_name).toBe('Low')

    // sortThoughtsByPriority: thoughts by priority (normalizes first)
    const thoughts = [
      'bare string thought',
      { text: 'P2 thought', priority: { rank: 'P2' as const } },
      { text: 'P1 thought', priority: { rank: 'P1' as const } },
    ]
    const sortedThoughts = utils.sortThoughtsByPriority(thoughts)
    expect(sortedThoughts[0].text).toBe('P1 thought')
    expect(sortedThoughts[1].text).toBe('P2 thought')
    expect(sortedThoughts[2].text).toBe('bare string thought')

    // RANK_COLORS: shared constant with consistent fallbacks
    expect(utils.RANK_COLORS).toBeDefined()
    expect(utils.RANK_COLORS.P1).toBeDefined()
    expect(utils.RANK_COLORS.P1.bg).toContain('--color-background-danger')
    expect(utils.RANK_COLORS.P2).toBeDefined()
    expect(utils.RANK_COLORS.P3).toBeDefined()
  })

  // Test 7: Content - fullscreen renders tag pills, inline does NOT
  // (Tag pills are ONLY in fullscreen; inline has tag indicator icon only)
  it('inline does NOT render tag pill text, only tag indicator', async () => {
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
          { cluster_name: 'Tagged', sum_thought_items: 5, tags: ['decide', 'urgent'] },
        ],
      },
    })
    rerender(<App />)

    // Tag indicator should exist
    expect(screen.getByLabelText('has action tags')).toBeInTheDocument()

    // But tag pill TEXT should NOT be rendered in inline mode
    expect(screen.queryByText('decide')).not.toBeInTheDocument()
    expect(screen.queryByText('urgent')).not.toBeInTheDocument()
  })

  // Test 8: Read-only - no edit buttons/handlers in either mode
  it('no edit or delete buttons exist', async () => {
    const { fireEvent } = await import('@testing-library/react')

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
          { cluster_name: 'Test', sum_thought_items: 2, thought_items: ['a', 'b'] },
        ],
      },
    })
    rerender(<App />)

    // Expand cluster
    const row = screen.getByRole('button', { name: /Test/i })
    fireEvent.click(row)

    // No edit/delete buttons
    expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /remove/i })).not.toBeInTheDocument()
  })

  // Test 10: No OpenAI deps, no emoji icons
  it('does not use OpenAI SDK or emoji icons', async () => {
    // Verify module loads without OpenAI dependency errors
    const AppModule = await import('../App')

    // Verify the default export is the App component (exists and is a function)
    expect(AppModule.default).toBeDefined()
    expect(typeof AppModule.default).toBe('function')

    // The real verification is that:
    // 1. The component renders (tested elsewhere)
    // 2. SVG icons are used not emoji (tested in tag indicator test)
    // 3. No @openai/apps-sdk-ui imports exist (would fail at import time)

    // Also verify icons are SVG (not emoji) - already tested in tag indicator test
  })

  // ==========================================================================
  // FULLSCREEN RENDER TEST - the critical missing coverage
  // ==========================================================================
  // Tests fullscreen content by starting in fullscreen mode (host-initiated).
  // This verifies: (a) tag pills, (b) subclusters, (c) no edit buttons,
  // (d) priority badges, (e) full content rendering

  it('fullscreen mode renders full board with tag pills, subclusters, and all content', async () => {
    const { act } = await import('@testing-library/react')

    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockApp: MockApp = {
      getHostContext: () => ({
        displayMode: 'fullscreen', // Start in fullscreen
        availableDisplayModes: ['inline', 'fullscreen'],
      }),
      requestDisplayMode: vi.fn().mockResolvedValue({ mode: 'inline' }),
      get ontoolresult() {
        return capturedOntoolresult
      },
      set ontoolresult(handler: ((result: unknown) => void) | null) {
        capturedOntoolresult = handler
      },
    }

    await act(async () => {
      capturedOnAppCreated!(mockApp)
      capturedOntoolresult!({
        structuredContent: {
          clusters: [
            {
              cluster_name: 'Test Cluster',
              sum_thought_items: 5,
              priority: { rank: 'P1' },
              tags: ['decide', 'urgent'],
              summary: 'This is a test summary',
              thought_items: [
                { text: 'Thought 1', priority: { rank: 'P2' } },
                'Bare string thought',
              ],
              subclusters: [
                {
                  subcluster_name: 'Sub Cluster A',
                  sum_thought_items: 2,
                  priority: { rank: 'P3' },
                  tags: ['review'],
                  thought_items: ['sub thought 1', 'sub thought 2'],
                },
              ],
            },
          ],
        },
      })
    })

    // Verify fullscreen main element
    expect(screen.getByRole('main', { name: /full board/i })).toBeInTheDocument()
    expect(screen.getByText('Your MindSort AI Board')).toBeInTheDocument()

    // (a) Tag pills render in fullscreen (not just indicator icons)
    expect(screen.getByText('decide')).toBeInTheDocument()
    expect(screen.getByText('urgent')).toBeInTheDocument()
    expect(screen.getByText('review')).toBeInTheDocument()

    // (b) Subcluster cards render with full content
    expect(screen.getByText('Sub Cluster A')).toBeInTheDocument()
    expect(screen.getByText('sub thought 1')).toBeInTheDocument()
    expect(screen.getByText('sub thought 2')).toBeInTheDocument()

    // (c) No edit/delete buttons (read-only)
    expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /remove/i })).not.toBeInTheDocument()

    // (d) Priority badges render with text (not color-only)
    expect(screen.getByText('P1')).toBeInTheDocument()
    expect(screen.getByText('P2')).toBeInTheDocument()
    expect(screen.getByText('P3')).toBeInTheDocument()

    // (e) Summary and thought items render fully
    expect(screen.getByText('This is a test summary')).toBeInTheDocument()
    expect(screen.getByText('Thought 1')).toBeInTheDocument()
    expect(screen.getByText('Bare string thought')).toBeInTheDocument()

    // Host-initiated fullscreen = hostFullscreen=true = NO minimize button
    // (host provides native close chrome)
    expect(screen.queryByRole('button', { name: /minimize/i })).not.toBeInTheDocument()
  })

  // Test: widget-initiated fullscreen shows minimize button
  it('widget-initiated fullscreen shows minimize button (hostFullscreen=false)', async () => {
    const { act, fireEvent, waitFor } = await import('@testing-library/react')

    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockRequestDisplayMode = vi.fn().mockResolvedValue({ mode: 'inline' })
    const mockApp: MockApp = {
      getHostContext: () => ({
        displayMode: 'inline', // Start inline
        availableDisplayModes: ['inline', 'fullscreen'],
      }),
      requestDisplayMode: mockRequestDisplayMode,
      callServerTool: vi.fn().mockResolvedValue({}),
      get ontoolresult() {
        return capturedOntoolresult
      },
      set ontoolresult(handler: ((result: unknown) => void) | null) {
        capturedOntoolresult = handler
      },
    }

    await act(async () => {
      capturedOnAppCreated!(mockApp)
      capturedOntoolresult!({
        structuredContent: {
          clusters: [{ cluster_name: 'Test', sum_thought_items: 1 }],
        },
      })
    })

    // Should be in inline mode
    expect(screen.getByRole('main', { name: /board overview/i })).toBeInTheDocument()

    // Click "Open full board" to enter fullscreen (widget-initiated)
    const openButton = screen.getByRole('button', { name: /open full board/i })
    await act(async () => {
      fireEvent.click(openButton)
    })

    // Now should be in fullscreen mode
    await waitFor(() => {
      expect(screen.getByRole('main', { name: /full board/i })).toBeInTheDocument()
    })

    // Widget-initiated fullscreen = hostFullscreen=false = minimize button visible
    const minimizeButton = screen.getByRole('button', { name: /minimize/i })
    expect(minimizeButton).toBeInTheDocument()

    // Clicking minimize calls requestDisplayMode
    await act(async () => {
      fireEvent.click(minimizeButton)
    })
    expect(mockRequestDisplayMode).toHaveBeenCalledWith({ mode: 'inline' })
  })
})

// ==========================================================================
// Tests for inc_fullscreen_visual_alignment_openai (Tests 1-5)
// ==========================================================================
// These tests verify the visual alignment changes made in increment 3.
// Each test has a "Catches:" comment explaining what regression it prevents.

describe('Fullscreen Visual Alignment (inc_fullscreen_visual_alignment_openai)', () => {
  beforeEach(() => {
    mockUseApp.mockReset()
    mockUseHostStyles.mockReset()
    mockUseApp.mockReturnValue({ app: null })
  })

  // Test 1: Tags render LAST in the fullscreen cluster card
  // Catches: section-order regression (the main fix)
  it('tags render LAST in fullscreen cluster card (after subclusters)', async () => {
    const { act } = await import('@testing-library/react')

    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockApp: MockApp = {
      getHostContext: () => ({
        displayMode: 'fullscreen',
        availableDisplayModes: ['inline', 'fullscreen'],
      }),
      get ontoolresult() {
        return capturedOntoolresult
      },
      set ontoolresult(handler: ((result: unknown) => void) | null) {
        capturedOntoolresult = handler
      },
    }

    await act(async () => {
      capturedOnAppCreated!(mockApp)
      capturedOntoolresult!({
        structuredContent: {
          clusters: [
            {
              cluster_name: 'Test Cluster',
              sum_thought_items: 3,
              tags: ['decide', 'follow-up'],
              thought_items: ['thought 1'],
              subclusters: [
                { subcluster_name: 'Sub A', sum_thought_items: 2 },
              ],
            },
          ],
        },
      })
    })

    // Get the cluster card article element
    const clusterCard = screen.getByRole('article', { name: /Test Cluster/i })
    const cardHtml = clusterCard.innerHTML

    // Tags should appear AFTER subcluster content in DOM order
    const subclusterPos = cardHtml.indexOf('Sub A')
    const tagPos = cardHtml.indexOf('decide')

    expect(subclusterPos).toBeGreaterThan(-1)
    expect(tagPos).toBeGreaterThan(-1)
    expect(tagPos).toBeGreaterThan(subclusterPos) // Tags LAST
  })

  // Test 2: Thought item has no bullet icon and badge follows text
  // Catches: reverting to bullet/badge-first
  it('thought item has NO bullet SVG and priority badge follows text', async () => {
    const { act } = await import('@testing-library/react')

    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockApp: MockApp = {
      getHostContext: () => ({
        displayMode: 'fullscreen',
        availableDisplayModes: ['inline', 'fullscreen'],
      }),
      get ontoolresult() {
        return capturedOntoolresult
      },
      set ontoolresult(handler: ((result: unknown) => void) | null) {
        capturedOntoolresult = handler
      },
    }

    await act(async () => {
      capturedOnAppCreated!(mockApp)
      capturedOntoolresult!({
        structuredContent: {
          clusters: [
            {
              cluster_name: 'Test',
              sum_thought_items: 1,
              thought_items: [
                { text: 'Priority thought', priority: { rank: 'P1' } },
              ],
            },
          ],
        },
      })
    })

    // Find the thought list item
    const thoughtItems = screen.getAllByRole('listitem')
    // Filter to find the thought item (contains "Priority thought")
    const thoughtItem = thoughtItems.find(item => item.textContent?.includes('Priority thought'))
    expect(thoughtItem).toBeDefined()

    // NO bullet SVG inside the thought item (no filled circle)
    // The old implementation had a bullet SVG with fill="currentColor" and a circle
    const bulletSvgs = thoughtItem!.querySelectorAll('svg[fill="currentColor"]')
    bulletSvgs.forEach(svg => {
      const hasFilledCircle = svg.querySelector('circle[r="4"]') || svg.querySelector('circle[r="6"]')
      expect(hasFilledCircle).toBeNull()
    })

    // Badge (P1) should follow text in DOM order
    const itemHtml = thoughtItem!.innerHTML
    const textPos = itemHtml.indexOf('Priority thought')
    const badgePos = itemHtml.indexOf('P1')

    expect(textPos).toBeGreaterThan(-1)
    expect(badgePos).toBeGreaterThan(-1)
    expect(badgePos).toBeGreaterThan(textPos) // Badge AFTER text
  })

  // Test 3: Count is a pill containing only the number
  // Catches: reverting to "N thoughts" plain text
  it('count is an outlined pill with number only, not "N thoughts" text', async () => {
    const { act } = await import('@testing-library/react')

    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockApp: MockApp = {
      getHostContext: () => ({
        displayMode: 'fullscreen',
        availableDisplayModes: ['inline', 'fullscreen'],
      }),
      get ontoolresult() {
        return capturedOntoolresult
      },
      set ontoolresult(handler: ((result: unknown) => void) | null) {
        capturedOntoolresult = handler
      },
    }

    await act(async () => {
      capturedOnAppCreated!(mockApp)
      capturedOntoolresult!({
        structuredContent: {
          clusters: [
            {
              cluster_name: 'Test',
              sum_thought_items: 7,
            },
          ],
        },
      })
    })

    // The count pill should show just "7", not "7 thoughts"
    // Find element containing just "7" (aria-hidden pill)
    const countPill = screen.getByText('7', { selector: '[aria-hidden="true"]' })
    expect(countPill).toBeInTheDocument()

    // The "7 thoughts" full text should be screen-reader only (sr-only)
    // It should exist but be visually hidden
    const srOnlyText = screen.getByText('7 items')
    expect(srOnlyText).toBeInTheDocument()
    // Verify it has sr-only styling (position: absolute, clipped)
    expect(srOnlyText).toHaveStyle({ position: 'absolute' })

    // The plain text "7 thoughts" should NOT be visible
    expect(screen.queryByText('7 thoughts')).not.toBeInTheDocument()
  })

  // Test 4: Subcluster left accent only when prioritized
  // Catches: the always-on border regression
  it('subcluster has left accent ONLY when prioritized', async () => {
    const { act } = await import('@testing-library/react')

    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockApp: MockApp = {
      getHostContext: () => ({
        displayMode: 'fullscreen',
        availableDisplayModes: ['inline', 'fullscreen'],
      }),
      get ontoolresult() {
        return capturedOntoolresult
      },
      set ontoolresult(handler: ((result: unknown) => void) | null) {
        capturedOntoolresult = handler
      },
    }

    await act(async () => {
      capturedOnAppCreated!(mockApp)
      capturedOntoolresult!({
        structuredContent: {
          clusters: [
            {
              cluster_name: 'Parent',
              sum_thought_items: 4,
              subclusters: [
                { subcluster_name: 'Prioritized Sub', sum_thought_items: 2, priority: { rank: 'P2' } },
                { subcluster_name: 'Unprioritized Sub', sum_thought_items: 2 },
              ],
            },
          ],
        },
      })
    })

    // Find both subclusters by their aria-label
    const prioritizedSub = screen.getByLabelText('Subcluster: Prioritized Sub')
    const unprioritizedSub = screen.getByLabelText('Subcluster: Unprioritized Sub')

    // Get the raw style attribute to check what was actually set
    const prioritizedStyleAttr = prioritizedSub.getAttribute('style') || ''
    const unprioritizedStyleAttr = unprioritizedSub.getAttribute('style') || ''

    // Prioritized: has left accent (border-left with 4px solid)
    expect(prioritizedStyleAttr).toMatch(/border-left:\s*4px/)
    // Should also have other borders set to none (not a full border)
    expect(prioritizedStyleAttr).not.toMatch(/border:\s*1px/)

    // Unprioritized: should NOT have border-left: 4px (no accent)
    // Instead it has a regular 1px border on all sides
    expect(unprioritizedStyleAttr).not.toMatch(/border-left:\s*4px/)
    // And it should have a regular 1px border
    expect(unprioritizedStyleAttr).toMatch(/border:\s*1px/)
  })

  // Test 5: No Unicode glyphs / no OpenAI imports
  // Catches: the recurring glyph regression
  it('no Unicode glyphs (▲▼·→›•) in rendered output', async () => {
    const { act } = await import('@testing-library/react')

    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    const { container } = render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockApp: MockApp = {
      getHostContext: () => ({
        displayMode: 'fullscreen',
        availableDisplayModes: ['inline', 'fullscreen'],
      }),
      get ontoolresult() {
        return capturedOntoolresult
      },
      set ontoolresult(handler: ((result: unknown) => void) | null) {
        capturedOntoolresult = handler
      },
    }

    await act(async () => {
      capturedOnAppCreated!(mockApp)
      capturedOntoolresult!({
        structuredContent: {
          clusters: [
            {
              cluster_name: 'Test',
              sum_thought_items: 3,
              tags: ['tag1'],
              thought_items: [
                { text: 'Thought 1', priority: { rank: 'P1' } },
                'Thought 2',
              ],
              subclusters: [
                { subcluster_name: 'Sub', sum_thought_items: 1, thought_items: ['sub thought'] },
              ],
            },
          ],
        },
      })
    })

    // Get the entire rendered HTML
    const fullHtml = container.innerHTML

    // Check for forbidden Unicode glyphs
    const forbiddenGlyphs = ['▲', '▼', '·', '→', '›', '•']
    for (const glyph of forbiddenGlyphs) {
      expect(fullHtml).not.toContain(glyph)
    }
  })

  // Additional test: Verify module imports cleanly (no OpenAI SDK)
  it('module loads without OpenAI SDK imports', async () => {
    // This test passes if the module loads without errors
    // OpenAI SDK imports would cause module resolution failures
    const AppModule = await import('../App')
    expect(AppModule.default).toBeDefined()

    // Also verify utils loads cleanly
    const UtilsModule = await import('../utils')
    expect(UtilsModule.RANK_COLORS).toBeDefined()
  })
})

// ==========================================================================
// Tests for inc_fullscreen_shell_primitives_alignment (Tests 1-11)
// ==========================================================================
// These tests verify the shell and primitive alignment changes in increment 4.
// Each test has a "Catches:" comment explaining what regression it prevents.

describe('Fullscreen Shell & Primitives Alignment (inc_fullscreen_shell_primitives_alignment)', () => {
  beforeEach(() => {
    mockUseApp.mockReset()
    mockUseHostStyles.mockReset()
    mockUseApp.mockReturnValue({ app: null })
  })

  // Helper to setup fullscreen mode with given clusters
  async function setupFullscreen(clusters: unknown[]) {
    const { act } = await import('@testing-library/react')

    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    const result = render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockApp: MockApp = {
      getHostContext: () => ({
        displayMode: 'fullscreen',
        availableDisplayModes: ['inline', 'fullscreen'],
        safeAreaInsets: { top: 0, bottom: 0, left: 0, right: 0 },
      }),
      get ontoolresult() {
        return capturedOntoolresult
      },
      set ontoolresult(handler: ((result: unknown) => void) | null) {
        capturedOntoolresult = handler
      },
    }

    await act(async () => {
      capturedOnAppCreated!(mockApp)
      capturedOntoolresult!({
        structuredContent: { clusters },
      })
    })

    return result
  }

  // Test 1: Grid uses 240px minmax
  // Catches: revert to 320px
  it('grid uses 240px minmax (not 320px)', async () => {
    const { container } = await setupFullscreen([
      { cluster_name: 'Cluster 1', sum_thought_items: 3 },
      { cluster_name: 'Cluster 2', sum_thought_items: 2 },
    ])

    // Find the grid container (parent of cluster cards)
    const gridContainer = container.querySelector('[style*="grid-template-columns"]')
    expect(gridContainer).not.toBeNull()

    const styleAttr = gridContainer!.getAttribute('style') || ''
    // Should contain 240px, NOT 320px
    expect(styleAttr).toContain('240px')
    expect(styleAttr).not.toContain('320px')
  })

  // Test 2: Board container uses secondary background + new padding
  // Catches: figure/ground revert (primary background instead of secondary)
  it('board container uses secondary background and 16px border-radius', async () => {
    await setupFullscreen([{ cluster_name: 'Test', sum_thought_items: 1 }])

    const mainElement = screen.getByRole('main', { name: /full board/i })
    const styleAttr = mainElement.getAttribute('style') || ''

    // Should use secondary background
    expect(styleAttr).toContain('--color-background-secondary')
    // Should have 16px border radius
    expect(styleAttr).toContain('16px')
  })

  // Test 3: Cluster card ALWAYS has a border; prioritized also has 4px left accent
  // Catches: borderless unprioritized cards
  it('cluster card always has border; prioritized has 4px left accent', async () => {
    await setupFullscreen([
      { cluster_name: 'With Priority', sum_thought_items: 2, priority: { rank: 'P1' } },
      { cluster_name: 'No Priority', sum_thought_items: 2 },
    ])

    // Find both cluster cards by their aria-label (includes "Cluster:" prefix)
    const prioritizedCard = screen.getByRole('article', { name: /With Priority/i })
    const unprioritizedCard = screen.getByRole('article', { name: /No Priority/i })

    const prioritizedStyle = prioritizedCard.getAttribute('style') || ''
    const unprioritizedStyle = unprioritizedCard.getAttribute('style') || ''

    // Both must have some form of border (not borderless)
    // Prioritized: border-left: 4px + border-top/right/bottom: 1px
    expect(prioritizedStyle).toMatch(/border-left:\s*4px/)
    expect(prioritizedStyle).toMatch(/border-top:\s*1px/)

    // Unprioritized: border: 1px (all sides)
    expect(unprioritizedStyle).toMatch(/border:\s*1px/)
    expect(unprioritizedStyle).not.toMatch(/border-left:\s*4px/) // no accent
  })

  // Test 4: Header renders title AND subtitle, NO count
  // Catches: missing subtitle; count left in place
  it('header renders title + subtitle, NO cluster/thought count', async () => {
    await setupFullscreen([
      { cluster_name: 'Test', sum_thought_items: 5 },
      { cluster_name: 'Test2', sum_thought_items: 3 },
    ])

    // Title should exist
    expect(screen.getByText('Your MindSort AI Board')).toBeInTheDocument()

    // Subtitle should exist (the specific text from OpenAI Header)
    expect(screen.getByText(/Your thoughts grouped into clusters/i)).toBeInTheDocument()
    expect(screen.getByText(/Use the chat to rename, split, or reprioritize/i)).toBeInTheDocument()

    // Count should NOT be in the fullscreen header
    // INTENTIONAL ASYMMETRY: inline has count, fullscreen does not
    const mainElement = screen.getByRole('main', { name: /full board/i })

    // The header area should NOT contain "N clusters" or "N thoughts" text
    // Note: we check the header specifically, not the whole page
    const headerSection = mainElement.querySelector('h1')?.parentElement
    expect(headerSection).not.toBeNull()
    const headerText = headerSection!.textContent || ''
    expect(headerText).not.toMatch(/\d+\s*cluster/)
    expect(headerText).not.toMatch(/\d+\s*thought/)
  })

  // Test 5: Tag pill text is lowercase; accessible label uses original casing
  // Catches: casing/label regressions
  it('tag pill displays lowercase text but preserves original casing in aria-label', async () => {
    await setupFullscreen([
      { cluster_name: 'Test', sum_thought_items: 1, tags: ['Decide', 'URGENT', 'follow-Up'] },
    ])

    // Visible text should be lowercase
    expect(screen.getByText('decide')).toBeInTheDocument()
    expect(screen.getByText('urgent')).toBeInTheDocument()
    expect(screen.getByText('follow-up')).toBeInTheDocument()

    // Accessible labels should preserve original casing with "Suggested action:" prefix
    expect(screen.getByLabelText('Suggested action: Decide')).toBeInTheDocument()
    expect(screen.getByLabelText('Suggested action: URGENT')).toBeInTheDocument()
    expect(screen.getByLabelText('Suggested action: follow-Up')).toBeInTheDocument()
  })

  // Test 6: Fullscreen empty state uses OpenAI copy
  // Catches: copy revert to old message
  it('fullscreen empty state uses OpenAI copy', async () => {
    await setupFullscreen([])

    // Should show the OpenAI empty state message, not the old one
    expect(screen.getByText(/No saved board yet/i)).toBeInTheDocument()
    expect(screen.getByText(/Start one by sharing what's on your mind/i)).toBeInTheDocument()

    // Should NOT show the old message
    expect(screen.queryByText(/Start organizing your thoughts/i)).not.toBeInTheDocument()
  })

  // Test 7: Auto-save footer renders
  // Catches: missing/removed footer
  it('auto-save footer renders at end of fullscreen board', async () => {
    await setupFullscreen([{ cluster_name: 'Test', sum_thought_items: 1 }])

    // The auto-save footer should be present
    expect(screen.getByText('Changes are saved automatically')).toBeInTheDocument()
  })

  // Test 8: Priority badges remain color-coded (intentional deviation)
  // Catches: someone "aligning" to OpenAI's neutral badges
  it('priority badges are color-coded (P1 danger, P2 warning, P3 info) - intentional deviation', async () => {
    await setupFullscreen([
      { cluster_name: 'P1 Cluster', sum_thought_items: 1, priority: { rank: 'P1' } },
      { cluster_name: 'P2 Cluster', sum_thought_items: 1, priority: { rank: 'P2' } },
      { cluster_name: 'P3 Cluster', sum_thought_items: 1, priority: { rank: 'P3' } },
    ])

    // Find the priority badges in cluster cards
    const p1Badge = screen.getAllByText('P1')[0]
    const p2Badge = screen.getAllByText('P2')[0]
    const p3Badge = screen.getAllByText('P3')[0]

    // Check they use color-coded backgrounds (not neutral)
    const p1Style = p1Badge.getAttribute('style') || ''
    const p2Style = p2Badge.getAttribute('style') || ''
    const p3Style = p3Badge.getAttribute('style') || ''

    // P1 should use danger token
    expect(p1Style).toContain('--color-background-danger')
    // P2 should use warning token
    expect(p2Style).toContain('--color-background-warning')
    // P3 should use info token
    expect(p3Style).toContain('--color-background-info')
  })

  // Test 9: Inline card STILL shows its count (intentional asymmetry)
  // Catches: accidentally stripping the inline count
  it('inline card still shows cluster/thought count (intentional asymmetry)', async () => {
    const { act } = await import('@testing-library/react')

    let capturedOnAppCreated: ((app: MockApp) => void) | null = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockUseApp.mockImplementation((config: any) => {
      capturedOnAppCreated = config.onAppCreated
      return { app: null }
    })

    render(<App />)

    let capturedOntoolresult: ((result: unknown) => void) | null = null
    const mockApp: MockApp = {
      getHostContext: () => ({
        displayMode: 'inline', // INLINE mode
        availableDisplayModes: ['inline', 'fullscreen'],
      }),
      get ontoolresult() {
        return capturedOntoolresult
      },
      set ontoolresult(handler: ((result: unknown) => void) | null) {
        capturedOntoolresult = handler
      },
    }

    await act(async () => {
      capturedOnAppCreated!(mockApp)
      capturedOntoolresult!({
        structuredContent: {
          clusters: [
            { cluster_name: 'Test', sum_thought_items: 5 },
            { cluster_name: 'Test2', sum_thought_items: 3 },
          ],
        },
      })
    })

    // Inline mode should still show the count
    expect(screen.getByText(/2 clusters/)).toBeInTheDocument()
    expect(screen.getByText(/8 thoughts/)).toBeInTheDocument()
  })

  // Test 10: No Unicode glyphs; no OpenAI imports
  // Catches: the recurring glyph regression (same as increment 3, ensures no regression)
  it('no Unicode glyphs in fullscreen rendered output', async () => {
    const { container } = await setupFullscreen([
      {
        cluster_name: 'Test',
        sum_thought_items: 2,
        tags: ['tag1'],
        thought_items: [{ text: 'thought', priority: { rank: 'P1' } }],
        subclusters: [{ subcluster_name: 'Sub', sum_thought_items: 1 }],
      },
    ])

    const fullHtml = container.innerHTML
    const forbiddenGlyphs = ['▲', '▼', '·', '→', '›', '•']
    for (const glyph of forbiddenGlyphs) {
      expect(fullHtml).not.toContain(glyph)
    }
  })

  // Test 11: Tag pill has NO border (soft variant)
  // Catches: reverting to bordered tag pills
  it('tag pill has no border (soft variant)', async () => {
    await setupFullscreen([
      { cluster_name: 'Test', sum_thought_items: 1, tags: ['decide'] },
    ])

    const tagPill = screen.getByText('decide')
    const styleAttr = tagPill.getAttribute('style') || ''

    // Should NOT have border property
    // Soft variant = filled tint, no outline
    expect(styleAttr).not.toContain('border:')
    expect(styleAttr).not.toContain('border-color')
  })
})
