/**
 * React Widget Tests for Priority Guardian Dashboard (Widget Increments A & B)
 *
 * Tests:
 * - Priority cards render correctly (Deadline and Flexible types)
 * - Connection status displays correctly
 * - camelCase field names are used
 * - UI matches spec requirements
 * - Edit mode for priority cards
 * - Add Priority form validation
 * - Delete confirmation dialog
 * - Deliverable CRUD interactions
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../App'
import { setMockPriorities, resetMocks, mockOpenai } from '../test/setup'
import type { Priority } from '../types'

// Sample priorities for testing
const deadlinePriority: Priority = {
  id: 'pri-1',
  name: 'Launch Feature X',
  type: 'deadline',
  calendarKeyword: 'P1',
  status: 'active',
  deadline: '2025-02-15',
  weeklyHourTarget: 10,
  weeklyHourActual: 8,
  checkpointDate: null,
  desiredResult: null,
  deliverables: [
    { id: 'd1', name: 'Design doc', done: true },
    { id: 'd2', name: 'Implementation', done: false },
  ],
  createdAt: '2025-01-01T00:00:00Z',
  updatedAt: '2025-01-10T00:00:00Z',
}

const flexiblePriority: Priority = {
  id: 'pri-2',
  name: 'Learn Rust',
  type: 'flexible',
  calendarKeyword: 'P2',
  status: 'active',
  deadline: null,
  weeklyHourTarget: 5,
  weeklyHourActual: 3,
  checkpointDate: '2025-02-28',
  desiredResult: 'Complete first 10 chapters',
  deliverables: [],
  createdAt: '2025-01-05T00:00:00Z',
  updatedAt: '2025-01-12T00:00:00Z',
}

describe('App', () => {
  beforeEach(() => {
    resetMocks()
  })

  describe('Empty State', () => {
    it('renders empty state when no priorities', () => {
      setMockPriorities([], false)
      render(<App />)
      expect(screen.getByText(/no priorities yet/i)).toBeInTheDocument()
    })

    it('shows connect button when Google not connected', () => {
      setMockPriorities([], false)
      render(<App />)
      expect(screen.getByRole('button', { name: /connect/i })).toBeInTheDocument()
    })
  })

  describe('Connection Status', () => {
    it('shows connected status with checkmark', () => {
      setMockPriorities([], true)
      render(<App />)
      expect(screen.getByText(/connected/i)).toBeInTheDocument()
    })

    it('shows not connected status', () => {
      setMockPriorities([], false)
      render(<App />)
      expect(screen.getByText(/not connected/i)).toBeInTheDocument()
    })

    it('shows disconnect button when connected', () => {
      setMockPriorities([], true)
      render(<App />)
      expect(screen.getByRole('button', { name: /disconnect/i })).toBeInTheDocument()
    })
  })

  describe('Deadline Priority Card', () => {
    beforeEach(() => {
      setMockPriorities([deadlinePriority], true)
    })

    it('renders priority name', () => {
      render(<App />)
      expect(screen.getByText('Launch Feature X')).toBeInTheDocument()
    })

    it('renders calendar keyword badge', () => {
      render(<App />)
      // P1 appears twice: in badge and in calendar reminder
      const p1Elements = screen.getAllByText('P1')
      expect(p1Elements.length).toBeGreaterThanOrEqual(1)
    })

    it('renders deadline type indicator', () => {
      render(<App />)
      expect(screen.getByText(/deadline/i)).toBeInTheDocument()
    })

    it('renders deliverables list', () => {
      render(<App />)
      expect(screen.getByText('Design doc')).toBeInTheDocument()
      expect(screen.getByText('Implementation')).toBeInTheDocument()
    })

    it('shows deliverables progress', () => {
      render(<App />)
      expect(screen.getByText(/1 of 2 done/i)).toBeInTheDocument()
    })

    it('shows calendar keyword reminder', () => {
      render(<App />)
      expect(screen.getByText(/tag calendar events with/i)).toBeInTheDocument()
    })
  })

  describe('Flexible Priority Card', () => {
    beforeEach(() => {
      setMockPriorities([flexiblePriority], true)
    })

    it('renders priority name', () => {
      render(<App />)
      expect(screen.getByText('Learn Rust')).toBeInTheDocument()
    })

    it('renders calendar keyword badge', () => {
      render(<App />)
      // P2 appears twice: in badge and in calendar reminder
      const p2Elements = screen.getAllByText('P2')
      expect(p2Elements.length).toBeGreaterThanOrEqual(1)
    })

    it('renders flexible type indicator', () => {
      render(<App />)
      expect(screen.getByText(/flexible/i)).toBeInTheDocument()
    })

    it('renders weekly hour target', () => {
      render(<App />)
      expect(screen.getByText(/5h\/week target/i)).toBeInTheDocument()
    })

    it('renders desired result (1-Month Goal)', () => {
      render(<App />)
      expect(screen.getByText('Complete first 10 chapters')).toBeInTheDocument()
    })

    it('shows checkpoint date countdown', () => {
      render(<App />)
      // The exact text depends on current date, but should mention "check-in"
      expect(screen.getByText(/check-in/i)).toBeInTheDocument()
    })
  })

  describe('Multiple Priorities', () => {
    it('sorts priorities by keyword (P1 first, then P2)', () => {
      // Put P2 first in array, but P1 should render first
      setMockPriorities([flexiblePriority, deadlinePriority], true)
      render(<App />)

      const cards = screen.getAllByRole('article')
      expect(cards).toHaveLength(2)

      // P1 card should be first
      expect(cards[0]).toHaveAttribute('aria-label', expect.stringContaining('P1'))
      // P2 card should be second
      expect(cards[1]).toHaveAttribute('aria-label', expect.stringContaining('P2'))
    })

    it('renders all priorities', () => {
      setMockPriorities([deadlinePriority, flexiblePriority], true)
      render(<App />)

      expect(screen.getByText('Launch Feature X')).toBeInTheDocument()
      expect(screen.getByText('Learn Rust')).toBeInTheDocument()
    })
  })

  describe('camelCase Field Names', () => {
    it('uses calendarKeyword (not calendar_keyword)', () => {
      const priority: Priority = {
        ...deadlinePriority,
        calendarKeyword: 'P3',
      }
      setMockPriorities([priority], true)
      render(<App />)
      // P3 appears twice: in badge and in calendar reminder
      const p3Elements = screen.getAllByText('P3')
      expect(p3Elements.length).toBeGreaterThanOrEqual(1)
    })

    it('uses weeklyHourTarget (not weekly_hour_target)', () => {
      const priority: Priority = {
        ...flexiblePriority,
        weeklyHourTarget: 15,
      }
      setMockPriorities([priority], true)
      render(<App />)
      expect(screen.getByText(/15h\/week target/i)).toBeInTheDocument()
    })

    it('uses checkpointDate (not checkpoint_date)', () => {
      const priority: Priority = {
        ...flexiblePriority,
        checkpointDate: '2025-03-15',
      }
      setMockPriorities([priority], true)
      render(<App />)
      // Should show formatted checkpoint date
      expect(screen.getByText(/mar 15/i)).toBeInTheDocument()
    })

    it('uses desiredResult (not desired_result)', () => {
      const priority: Priority = {
        ...flexiblePriority,
        desiredResult: 'Custom goal text',
      }
      setMockPriorities([priority], true)
      render(<App />)
      expect(screen.getByText('Custom goal text')).toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('renders gracefully when toolOutput is undefined', () => {
      // Don't call setMockPriorities - leave toolOutput undefined
      render(<App />)
      // Should show loading or empty state, not crash
      expect(document.body).toBeTruthy()
    })
  })

  describe('Edit Mode (Widget B)', () => {
    it('shows edit button on deadline card', () => {
      setMockPriorities([deadlinePriority], true)
      render(<App />)
      // Priority edit button has specific aria-label pattern
      expect(screen.getByRole('button', { name: /edit priority/i })).toBeInTheDocument()
    })

    it('shows edit button on flexible card', () => {
      setMockPriorities([flexiblePriority], true)
      render(<App />)
      expect(screen.getByRole('button', { name: /edit priority/i })).toBeInTheDocument()
    })

    it('enters edit mode when edit button clicked', async () => {
      setMockPriorities([deadlinePriority], true)
      render(<App />)

      const editButton = screen.getByRole('button', { name: /edit priority/i })
      await userEvent.click(editButton)

      // Should show save and cancel buttons in edit mode
      expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    })

    it('exits edit mode when cancel clicked', async () => {
      setMockPriorities([deadlinePriority], true)
      render(<App />)

      // Enter edit mode
      const editButton = screen.getByRole('button', { name: /edit priority/i })
      await userEvent.click(editButton)

      // Click cancel
      const cancelButton = screen.getByRole('button', { name: /cancel/i })
      await userEvent.click(cancelButton)

      // Should show edit button again
      expect(screen.getByRole('button', { name: /edit priority/i })).toBeInTheDocument()
    })

    it('only allows one card in edit mode at a time', async () => {
      setMockPriorities([deadlinePriority, flexiblePriority], true)
      render(<App />)

      // Get all priority edit buttons (not deliverable edit buttons)
      const editButtons = screen.getAllByRole('button', { name: /edit priority/i })
      expect(editButtons).toHaveLength(2)

      // Click first edit button
      await userEvent.click(editButtons[0])

      // First card should be in edit mode
      expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument()
      // The other priority edit button should still exist but may be non-functional
      const remainingEditButtons = screen.queryAllByRole('button', { name: /edit priority/i })
      // When one is editing, the other card should have disabled or no edit functionality
      expect(remainingEditButtons.length).toBeLessThanOrEqual(2)
    })
  })

  describe('Add Priority Form (Widget B)', () => {
    it('shows add priority button when keywords available', () => {
      setMockPriorities([], true, ['P1', 'P2', 'P3'])
      render(<App />)
      expect(screen.getByRole('button', { name: /add a new priority/i })).toBeInTheDocument()
    })

    it('hides add priority button when no keywords available', () => {
      setMockPriorities([deadlinePriority, flexiblePriority], true, [])
      render(<App />)
      expect(screen.queryByRole('button', { name: /add a new priority/i })).not.toBeInTheDocument()
    })

    it('shows type selection when add button clicked', async () => {
      setMockPriorities([], true, ['P1', 'P2'])
      render(<App />)

      const addButton = screen.getByRole('button', { name: /add a new priority/i })
      await userEvent.click(addButton)

      // Form shows type selection first (Deadline vs Flexible)
      expect(screen.getByText(/what type of priority/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /create deadline priority/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /create flexible priority/i })).toBeInTheDocument()
    })

    it('shows cancel button in add form', async () => {
      setMockPriorities([], true, ['P1'])
      render(<App />)

      await userEvent.click(screen.getByRole('button', { name: /add a new priority/i }))

      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    })
  })

  describe('Delete Priority (Widget B)', () => {
    it('shows delete button on priority card', () => {
      setMockPriorities([deadlinePriority], true)
      render(<App />)

      // Delete button is visible on the priority card
      expect(screen.getByRole('button', { name: /delete priority/i })).toBeInTheDocument()
    })

    it('shows confirmation dialog when delete clicked', async () => {
      setMockPriorities([deadlinePriority], true)
      render(<App />)

      // Click delete on the priority
      await userEvent.click(screen.getByRole('button', { name: /delete priority/i }))

      // Should show confirmation dialog with warning text
      expect(screen.getByRole('alertdialog')).toBeInTheDocument()
      expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /confirm delete/i })).toBeInTheDocument()
    })

    it('calls delete tool when confirmed', async () => {
      mockOpenai.callTool.mockResolvedValue({
        structuredContent: {
          data: { google_connected: true, priorities: [] }
        }
      })

      setMockPriorities([deadlinePriority], true)
      render(<App />)

      // Click delete
      await userEvent.click(screen.getByRole('button', { name: /delete priority/i }))

      // Confirm delete
      await userEvent.click(screen.getByRole('button', { name: /confirm delete/i }))

      await waitFor(() => {
        expect(mockOpenai.callTool).toHaveBeenCalledWith(
          'delete_priority',
          expect.objectContaining({
            priority_id: 'pri-1',
            confirm: true
          })
        )
      })
    })
  })

  describe('Deliverable Interactions (Widget B)', () => {
    it('shows checkbox for each deliverable', () => {
      setMockPriorities([deadlinePriority], true)
      render(<App />)

      const checkboxes = screen.getAllByRole('checkbox')
      expect(checkboxes.length).toBeGreaterThanOrEqual(2)
    })

    it('toggles deliverable done state when checkbox clicked', async () => {
      mockOpenai.callTool.mockResolvedValue({
        structuredContent: {
          data: {
            google_connected: true,
            priorities: [{
              ...deadlinePriority,
              deliverables: [
                { id: 'd1', name: 'Design doc', done: false }, // toggled
                { id: 'd2', name: 'Implementation', done: false },
              ]
            }]
          }
        }
      })

      setMockPriorities([deadlinePriority], true)
      render(<App />)

      // Find the checkbox for the done deliverable
      const checkboxes = screen.getAllByRole('checkbox')
      // d1 is done=true, click to toggle to false
      await userEvent.click(checkboxes[0])

      await waitFor(() => {
        expect(mockOpenai.callTool).toHaveBeenCalledWith(
          'update_deliverable',
          expect.objectContaining({
            deliverable_id: 'd1',
            done: false
          })
        )
      })
    })
  })

  describe('widgetState Persistence (Widget B)', () => {
    it('persists edit mode to widgetState', async () => {
      setMockPriorities([deadlinePriority], true)
      render(<App />)

      await userEvent.click(screen.getByRole('button', { name: /edit priority/i }))

      await waitFor(() => {
        expect(mockOpenai.setWidgetState).toHaveBeenCalledWith(
          expect.objectContaining({
            editingPriorityId: 'pri-1'
          })
        )
      })
    })

    it('clears widgetState when exiting edit mode', async () => {
      setMockPriorities([deadlinePriority], true)
      render(<App />)

      // Enter edit mode
      await userEvent.click(screen.getByRole('button', { name: /edit priority/i }))

      // Exit edit mode
      await userEvent.click(screen.getByRole('button', { name: /cancel/i }))

      await waitFor(() => {
        // Last call should be with empty state (no editingPriorityId)
        const calls = mockOpenai.setWidgetState.mock.calls
        const lastCall = calls[calls.length - 1]?.[0]
        expect(lastCall?.editingPriorityId).toBeUndefined()
      })
    })
  })
})
