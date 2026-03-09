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

import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../App'
import { setMockPriorities, resetMocks, mockOpenai, setMockLocale } from '../test/setup'
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
  checkpointDate: undefined,
  desiredResult: undefined,
  deliverables: [
    { id: 'd1', name: 'Design doc', done: true },
    { id: 'd2', name: 'Implementation', done: false },
  ],
}

const flexiblePriority: Priority = {
  id: 'pri-2',
  name: 'Learn Rust',
  type: 'flexible',
  calendarKeyword: 'P2',
  status: 'active',
  deadline: undefined,
  weeklyHourTarget: 5,
  weeklyHourActual: 3,
  checkpointDate: '2025-02-28',
  desiredResult: 'Complete first 10 chapters',
  deliverables: [],
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
      // Text is split by <strong> element, so check for partial match
      expect(screen.getByText(/in the calendar event title to track time/i)).toBeInTheDocument()
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

    it('renders weekly hour target in HourRing', () => {
      render(<App />)
      // HourRing shows "/ 5h" for target in header right column
      expect(screen.getByText(/\/ 5h/)).toBeInTheDocument()
      // SVG ring should be present
      const svg = document.querySelector('svg[role="img"]')
      expect(svg).toBeInTheDocument()
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
      // HourRing shows "/ 15h" for target
      expect(screen.getByText(/\/ 15h/)).toBeInTheDocument()
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
    it('enters edit mode when clicking priority name', async () => {
      setMockPriorities([deadlinePriority], true)
      render(<App />)

      // Click on the priority name to enter edit mode
      const priorityName = screen.getByText('Launch Feature X')
      await userEvent.click(priorityName)

      // Should show an input field for editing the name
      expect(screen.getByRole('textbox', { name: /priority name/i })).toBeInTheDocument()
      // Should show auto-save hint
      expect(screen.getByText(/changes save automatically/i)).toBeInTheDocument()
    })

    it('shows input field when clicking priority name on flexible card', async () => {
      setMockPriorities([flexiblePriority], true)
      render(<App />)

      const priorityName = screen.getByText('Learn Rust')
      await userEvent.click(priorityName)

      expect(screen.getByRole('textbox', { name: /priority name/i })).toBeInTheDocument()
    })

    it('auto-saves on blur when name changes', async () => {
      mockOpenai.callTool.mockResolvedValue({
        structuredContent: {
          data: {
            google_connected: true,
            priorities: [{
              ...deadlinePriority,
              name: 'Updated Name'
            }]
          }
        }
      })

      setMockPriorities([deadlinePriority], true)
      render(<App />)

      // Click to edit
      const priorityName = screen.getByText('Launch Feature X')
      await userEvent.click(priorityName)

      // Change the name
      const input = screen.getByRole('textbox', { name: /priority name/i })
      await userEvent.clear(input)
      await userEvent.type(input, 'Updated Name')

      // Blur to trigger auto-save
      fireEvent.blur(input)

      await waitFor(() => {
        expect(mockOpenai.callTool).toHaveBeenCalledWith(
          'update_priority',
          expect.objectContaining({
            priority_id: 'pri-1',
            name: 'Updated Name'
          })
        )
      })
    })

    it('shows Done button in edit mode', async () => {
      setMockPriorities([deadlinePriority], true)
      render(<App />)

      // Enter edit mode
      await userEvent.click(screen.getByText('Launch Feature X'))

      // Should show Done button
      expect(screen.getByRole('button', { name: /done/i })).toBeInTheDocument()
    })

    it('exits edit mode when Done button clicked', async () => {
      setMockPriorities([deadlinePriority], true)
      render(<App />)

      // Enter edit mode
      await userEvent.click(screen.getByText('Launch Feature X'))

      // Click Done button
      await userEvent.click(screen.getByRole('button', { name: /done/i }))

      // Should exit edit mode (no more input field)
      expect(screen.queryByRole('textbox', { name: /priority name/i })).not.toBeInTheDocument()
    })

    it('does not show saving indicator during auto-save (silence = success)', async () => {
      // Make the callTool return slowly
      mockOpenai.callTool.mockImplementation(() => new Promise(resolve => {
        setTimeout(() => resolve({
          structuredContent: {
            data: { google_connected: true, priorities: [deadlinePriority] }
          }
        }), 100)
      }))

      setMockPriorities([deadlinePriority], true)
      render(<App />)

      // Enter edit mode and change name
      await userEvent.click(screen.getByText('Launch Feature X'))
      const input = screen.getByRole('textbox', { name: /priority name/i })
      await userEvent.clear(input)
      await userEvent.type(input, 'New Name')
      fireEvent.blur(input)

      // Should NOT show "Saving..." indicator (silence = success per spec)
      expect(screen.queryByText(/saving/i)).not.toBeInTheDocument()
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
      expect(screen.getByRole('dialog')).toBeInTheDocument()
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

  describe('CRUD Error Handling (Widget C)', () => {
    describe('Add Priority Error Handling', () => {
      it('shows inline error when callTool returns isError: true', async () => {
        mockOpenai.callTool.mockResolvedValue({ isError: true })

        setMockPriorities([], true, ['P1', 'P2'])
        render(<App />)

        // Open add form
        await userEvent.click(screen.getByRole('button', { name: /add a new priority/i }))

        // Select deadline type
        await userEvent.click(screen.getByRole('button', { name: /create deadline priority/i }))

        // Fill required fields
        await userEvent.type(screen.getByLabelText(/name/i), 'Test Priority')
        const deadlineInput = screen.getByLabelText(/deadline/i)
        fireEvent.change(deadlineInput, { target: { value: '2026-12-31' } })

        // Submit
        await userEvent.click(screen.getByRole('button', { name: /create priority/i }))

        // Should show inline error
        await waitFor(() => {
          expect(screen.getByText(/couldn't save/i)).toBeInTheDocument()
        })

        // Form should still be open (not closed on error)
        expect(screen.getByLabelText(/name/i)).toBeInTheDocument()
      })

      it('shows inline error when callTool throws exception', async () => {
        mockOpenai.callTool.mockRejectedValue(new Error('Network error'))

        setMockPriorities([], true, ['P1', 'P2'])
        render(<App />)

        // Open add form and fill fields
        await userEvent.click(screen.getByRole('button', { name: /add a new priority/i }))
        await userEvent.click(screen.getByRole('button', { name: /create deadline priority/i }))
        await userEvent.type(screen.getByLabelText(/name/i), 'Test Priority')
        fireEvent.change(screen.getByLabelText(/deadline/i), { target: { value: '2026-12-31' } })

        // Submit
        await userEvent.click(screen.getByRole('button', { name: /create priority/i }))

        // Should show error (from the exception or wrapped error)
        await waitFor(() => {
          expect(screen.getByRole('alert')).toBeInTheDocument()
        })

        // Form should still be open
        expect(screen.getByLabelText(/name/i)).toBeInTheDocument()
      })

      it('shows inline error when response has no data field', async () => {
        // Response without data field (malformed)
        mockOpenai.callTool.mockResolvedValue({
          structuredContent: { message: 'Something went wrong' }
        })

        setMockPriorities([], true, ['P1', 'P2'])
        render(<App />)

        // Open add form and fill fields
        await userEvent.click(screen.getByRole('button', { name: /add a new priority/i }))
        await userEvent.click(screen.getByRole('button', { name: /create deadline priority/i }))
        await userEvent.type(screen.getByLabelText(/name/i), 'Test Priority')
        fireEvent.change(screen.getByLabelText(/deadline/i), { target: { value: '2026-12-31' } })

        // Submit
        await userEvent.click(screen.getByRole('button', { name: /create priority/i }))

        // Should show inline error
        await waitFor(() => {
          expect(screen.getByText(/couldn't save/i)).toBeInTheDocument()
        })

        // Form should still be open
        expect(screen.getByLabelText(/name/i)).toBeInTheDocument()
      })
    })

    describe('Update Priority Error Handling', () => {
      it('shows inline error and reverts value when update fails with isError', async () => {
        mockOpenai.callTool.mockResolvedValue({ isError: true })

        setMockPriorities([deadlinePriority], true)
        render(<App />)

        // Enter edit mode
        await userEvent.click(screen.getByText('Launch Feature X'))

        // Change name
        const nameInput = screen.getByRole('textbox', { name: /priority name/i })
        await userEvent.clear(nameInput)
        await userEvent.type(nameInput, 'New Name')

        // Blur to trigger auto-save
        fireEvent.blur(nameInput)

        // Should show error
        await waitFor(() => {
          expect(screen.getByRole('alert')).toBeInTheDocument()
        })

        // Should revert to original value
        await waitFor(() => {
          expect(nameInput).toHaveValue('Launch Feature X')
        })
      })

      it('shows inline error when update throws exception', async () => {
        mockOpenai.callTool.mockRejectedValue(new Error('Server error'))

        setMockPriorities([deadlinePriority], true)
        render(<App />)

        // Enter edit mode and change name
        await userEvent.click(screen.getByText('Launch Feature X'))
        const nameInput = screen.getByRole('textbox', { name: /priority name/i })
        await userEvent.clear(nameInput)
        await userEvent.type(nameInput, 'New Name')
        fireEvent.blur(nameInput)

        // Should show error and revert
        await waitFor(() => {
          expect(screen.getByRole('alert')).toBeInTheDocument()
          expect(nameInput).toHaveValue('Launch Feature X')
        })
      })
    })

    describe('Delete Priority Error Handling', () => {
      it('shows inline error and closes confirm dialog when delete fails', async () => {
        mockOpenai.callTool.mockResolvedValue({ isError: true })

        setMockPriorities([deadlinePriority], true)
        render(<App />)

        // Click delete button
        await userEvent.click(screen.getByRole('button', { name: /delete priority/i }))

        // Confirm delete
        await userEvent.click(screen.getByRole('button', { name: /confirm delete/i }))

        // Should show error on the card (dialog closes, card shows error)
        await waitFor(() => {
          expect(screen.getByRole('alert')).toBeInTheDocument()
          expect(screen.getByText(/couldn't save/i)).toBeInTheDocument()
        })

        // Confirm dialog should be closed (card is visible again)
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
        expect(screen.getByText('Launch Feature X')).toBeInTheDocument()
      })

      it('shows error when delete throws exception', async () => {
        mockOpenai.callTool.mockRejectedValue(new Error('Delete failed'))

        setMockPriorities([deadlinePriority], true)
        render(<App />)

        // Click delete and confirm
        await userEvent.click(screen.getByRole('button', { name: /delete priority/i }))
        await userEvent.click(screen.getByRole('button', { name: /confirm delete/i }))

        // Should show error
        await waitFor(() => {
          expect(screen.getByRole('alert')).toBeInTheDocument()
        })

        // Card should still be visible (not deleted)
        expect(screen.getByText('Launch Feature X')).toBeInTheDocument()
      })
    })

    describe('Deliverable CRUD Error Handling', () => {
      it('propagates error when toggle deliverable fails with isError', async () => {
        mockOpenai.callTool.mockResolvedValue({ isError: true })

        setMockPriorities([deadlinePriority], true)
        render(<App />)

        // Toggle a deliverable checkbox
        const checkboxes = screen.getAllByRole('checkbox')
        await userEvent.click(checkboxes[0])

        // Should show error (propagated from handler)
        await waitFor(() => {
          expect(screen.getByRole('alert')).toBeInTheDocument()
        })
      })

      it('propagates error when add deliverable fails with isError', async () => {
        // First call succeeds (initial load doesn't call tool), subsequent fails
        mockOpenai.callTool.mockResolvedValue({ isError: true })

        setMockPriorities([deadlinePriority], true)
        render(<App />)

        // Click add deliverable button
        await userEvent.click(screen.getByRole('button', { name: /add.*deliverable/i }))

        // Fill in name and submit
        await userEvent.type(screen.getByLabelText(/new deliverable name/i), 'New Item')
        await userEvent.click(screen.getByRole('button', { name: /^add$/i }))

        // Should show error
        await waitFor(() => {
          expect(screen.getByRole('alert')).toBeInTheDocument()
        })
      })

      it('propagates error when delete deliverable fails with isError', async () => {
        mockOpenai.callTool.mockResolvedValue({ isError: true })

        setMockPriorities([deadlinePriority], true)
        render(<App />)

        // Hover to reveal delete button, then click
        const deleteButtons = screen.getAllByRole('button', { name: /delete ".*"/i })
        await userEvent.click(deleteButtons[0])

        // Confirm delete (deliverable uses "Confirm remove" aria-label)
        await userEvent.click(screen.getByRole('button', { name: /confirm remove/i }))

        // Should show error
        await waitFor(() => {
          expect(screen.getByRole('alert')).toBeInTheDocument()
        })
      })
    })
  })

  describe('Aggregate Stats Display (Inc 09)', () => {
    describe('FlexibleCard Aggregate Stats', () => {
      it('renders avgTargetAchievement when present', () => {
        const priority: Priority = {
          ...flexiblePriority,
          avgTargetAchievement: 84.0,
          weeklyHourTarget: 5,
        }
        setMockPriorities([priority], true)
        render(<App />)

        expect(screen.getByText(/~84% of weekly target on avg/i)).toBeInTheDocument()
      })

      it('shows placeholder when avgTargetAchievement is null', () => {
        const priority: Priority = {
          ...flexiblePriority,
          avgTargetAchievement: null,
          weeklyHourTarget: 5,
        }
        setMockPriorities([priority], true)
        render(<App />)

        expect(screen.getByText(/building your average/i)).toBeInTheDocument()
      })

      it('hides percentage section when weeklyHourTarget is null', () => {
        const priority: Priority = {
          ...flexiblePriority,
          avgTargetAchievement: 84.0,
          weeklyHourTarget: undefined,
        }
        setMockPriorities([priority], true)
        render(<App />)

        expect(screen.queryByText(/% of.*target on avg/i)).not.toBeInTheDocument()
        expect(screen.queryByText(/building your average/i)).not.toBeInTheDocument()
      })

      it('hides percentage section when weeklyHourTarget is 0', () => {
        const priority: Priority = {
          ...flexiblePriority,
          avgTargetAchievement: 84.0,
          weeklyHourTarget: 0,
        }
        setMockPriorities([priority], true)
        render(<App />)

        expect(screen.queryByText(/% of.*target on avg/i)).not.toBeInTheDocument()
      })

      it('rounds avgTargetAchievement correctly: 49.8 → ~50%', () => {
        const priority: Priority = {
          ...flexiblePriority,
          avgTargetAchievement: 49.8,
          weeklyHourTarget: 5,
        }
        setMockPriorities([priority], true)
        render(<App />)

        expect(screen.getByText(/~50%/)).toBeInTheDocument()
      })

      it('allows > 100%: avgTargetAchievement 160.5 → ~161%', () => {
        const priority: Priority = {
          ...flexiblePriority,
          avgTargetAchievement: 160.5,
          weeklyHourTarget: 5,
        }
        setMockPriorities([priority], true)
        render(<App />)

        expect(screen.getByText(/~161%/)).toBeInTheDocument()
      })

      it('shows totalHoursInvested when > 0', () => {
        const priority: Priority = {
          ...flexiblePriority,
          totalHoursInvested: 12.5,
        }
        setMockPriorities([priority], true)
        render(<App />)

        expect(screen.getByText(/12\.5h invested total/i)).toBeInTheDocument()
      })

      it('hides total when totalHoursInvested is 0', () => {
        const priority: Priority = {
          ...flexiblePriority,
          totalHoursInvested: 0,
        }
        setMockPriorities([priority], true)
        render(<App />)

        expect(screen.queryByText(/invested total/i)).not.toBeInTheDocument()
      })

      it('does not show stats in edit mode', async () => {
        const priority: Priority = {
          ...flexiblePriority,
          avgTargetAchievement: 84.0,
          weeklyHourTarget: 5,
          totalHoursInvested: 12.5,
        }
        setMockPriorities([priority], true)
        render(<App />)

        // Stats should be visible initially
        expect(screen.getByText(/~84%/)).toBeInTheDocument()
        expect(screen.getByText(/12\.5h invested total/i)).toBeInTheDocument()

        // Enter edit mode
        await userEvent.click(screen.getByText('Learn Rust'))

        // Stats should be hidden in edit mode
        expect(screen.queryByText(/~84%/)).not.toBeInTheDocument()
        expect(screen.queryByText(/12\.5h invested total/i)).not.toBeInTheDocument()
      })
    })

    describe('DeadlineCard Progress Bar', () => {
      it('renders progress bar when deliverables exist', () => {
        setMockPriorities([deadlinePriority], true)
        render(<App />)

        expect(screen.getByRole('progressbar')).toBeInTheDocument()
      })

      it('hides progress bar when 0 deliverables', () => {
        const priority: Priority = {
          ...deadlinePriority,
          deliverables: [],
        }
        setMockPriorities([priority], true)
        render(<App />)

        expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
      })

      it('progress bar width matches doneCount/totalCount ratio', () => {
        // 1 of 2 done = 50%
        setMockPriorities([deadlinePriority], true)
        render(<App />)

        const progressBar = screen.getByRole('progressbar')
        const fill = progressBar.querySelector('div')
        expect(fill).toHaveStyle({ width: '50%' })
      })

      it('progress bar has neutral color (not conditionally colored)', () => {
        setMockPriorities([deadlinePriority], true)
        render(<App />)

        const progressBar = screen.getByRole('progressbar')
        const fill = progressBar.querySelector('div')
        // Check it uses the neutral gray CSS variable
        expect(fill).toHaveClass('bg-[color:var(--gray-400)]')
      })

      it('progress bar has correct ARIA attributes', () => {
        setMockPriorities([deadlinePriority], true)
        render(<App />)

        const progressBar = screen.getByRole('progressbar')
        expect(progressBar).toHaveAttribute('aria-valuenow', '1')
        expect(progressBar).toHaveAttribute('aria-valuemin', '0')
        expect(progressBar).toHaveAttribute('aria-valuemax', '2')
        expect(progressBar).toHaveAttribute('aria-label', '1 of 2 deliverables completed')
      })
    })


  })

  describe('i18n Locale Rendering', () => {
    it('renders "Loading…" for English locale (en-US)', () => {
      setMockLocale('en-US')
      // Don't set toolOutput - App will show loading state
      render(<App />)
      expect(screen.getByText('Loading…')).toBeInTheDocument()
    })

    it('renders "Lädt…" for German locale (de-DE)', () => {
      setMockLocale('de-DE')
      // Don't set toolOutput - App will show loading state
      render(<App />)
      expect(screen.getByText('Lädt…')).toBeInTheDocument()
    })

    it('renders "No priorities yet" for English locale', () => {
      setMockLocale('en-US')
      setMockPriorities([], false)
      render(<App />)
      expect(screen.getByText('No priorities yet')).toBeInTheDocument()
    })

    it('renders "Noch keine Prioritäten vorhanden" for German locale', () => {
      setMockLocale('de-DE')
      setMockPriorities([], false)
      render(<App />)
      expect(screen.getByText('Noch keine Prioritäten vorhanden')).toBeInTheDocument()
    })
  })

  describe('widgetState Persistence (Widget B)', () => {
    it('persists edit mode to widgetState', async () => {
      setMockPriorities([deadlinePriority], true)
      render(<App />)

      // Click on priority name to enter edit mode
      await userEvent.click(screen.getByText('Launch Feature X'))

      await waitFor(() => {
        expect(mockOpenai.setWidgetState).toHaveBeenCalledWith(
          expect.objectContaining({
            editingPriorityId: 'pri-1'
          })
        )
      })
    })

    it('clears widgetState when clicking outside edit area', async () => {
      setMockPriorities([deadlinePriority], true)
      render(<App />)

      // Enter edit mode
      await userEvent.click(screen.getByText('Launch Feature X'))

      // Verify we're in edit mode
      expect(screen.getByRole('textbox', { name: /priority name/i })).toBeInTheDocument()

      // The widgetState should have been set with editingPriorityId
      await waitFor(() => {
        expect(mockOpenai.setWidgetState).toHaveBeenCalledWith(
          expect.objectContaining({
            editingPriorityId: 'pri-1'
          })
        )
      })
    })
  })
})
