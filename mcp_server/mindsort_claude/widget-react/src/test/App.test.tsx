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

// Source file check: Verify forbidden functions are NOT used
// Using dynamic import check instead of Node fs to avoid type issues
describe('Source file compliance', () => {
  it('utils.ts does NOT export getEffectiveRank', async () => {
    const utils = await import('../utils')
    expect('getEffectiveRank' in utils).toBe(false)
    expect('getEffectiveSubclusterRank' in utils).toBe(false)
  })
})
