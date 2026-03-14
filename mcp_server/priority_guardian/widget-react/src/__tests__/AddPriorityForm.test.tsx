/**
 * AddPriorityForm Keyboard Tests (Increment 72)
 *
 * Tests Enter key behavior on form inputs:
 * 1. Enter on name input advances to type step
 * 2. Enter on deadline input submits (deadline priority)
 * 3. Enter on hours input submits (flexible priority)
 * 4. Enter on textarea does NOT submit
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AddPriorityForm } from '../components/AddPriorityForm'

describe('AddPriorityForm Keyboard Navigation', () => {
  const mockOnAdd = vi.fn().mockResolvedValue(undefined)
  const mockOnCancel = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('Enter on name input advances to type step', async () => {
    const user = userEvent.setup()
    render(
      <AddPriorityForm
        availableKeywords={['P1']}
        onAdd={mockOnAdd}
        onCancel={mockOnCancel}
      />
    )

    // Type name
    const nameInput = screen.getByLabelText(/what do you want to track/i)
    await user.type(nameInput, 'Test Priority')

    // Press Enter
    fireEvent.keyDown(nameInput, { key: 'Enter' })

    // Assert type selection heading appears
    expect(screen.getByText(/what kind of priority/i)).toBeInTheDocument()
  })

  it('Enter on deadline input submits', async () => {
    const user = userEvent.setup()
    render(
      <AddPriorityForm
        availableKeywords={['P1']}
        onAdd={mockOnAdd}
        onCancel={mockOnCancel}
      />
    )

    // Step 1: Type name and press Enter
    const nameInput = screen.getByLabelText(/what do you want to track/i)
    await user.type(nameInput, 'Ship Feature')
    fireEvent.keyDown(nameInput, { key: 'Enter' })

    // Step 2: Click Deadline type button
    const deadlineTypeBtn = screen.getByRole('button', { name: /deadline priority/i })
    await user.click(deadlineTypeBtn)

    // Step 3: Fill deadline input
    const deadlineInput = document.getElementById('priority-deadline') as HTMLInputElement
    fireEvent.change(deadlineInput, { target: { value: '2026-12-31' } })

    // Press Enter on deadline input
    fireEvent.keyDown(deadlineInput, { key: 'Enter' })

    // Assert onAdd called with correct data
    await waitFor(() => {
      expect(mockOnAdd).toHaveBeenCalledWith({
        name: 'Ship Feature',
        type: 'deadline',
        deadline: '2026-12-31',
      })
    })
  })

  it('Enter on hours input submits (flexible)', async () => {
    const user = userEvent.setup()
    render(
      <AddPriorityForm
        availableKeywords={['P1']}
        onAdd={mockOnAdd}
        onCancel={mockOnCancel}
      />
    )

    // Step 1: Type name and press Enter
    const nameInput = screen.getByLabelText(/what do you want to track/i)
    await user.type(nameInput, 'Learn TypeScript')
    fireEvent.keyDown(nameInput, { key: 'Enter' })

    // Step 2: Click Flexible type button
    const flexibleTypeBtn = screen.getByRole('button', { name: /flexible priority/i })
    await user.click(flexibleTypeBtn)

    // Step 3: Fill all required fields
    const hoursInput = document.getElementById('priority-hours') as HTMLInputElement
    const checkpointInput = document.getElementById('priority-checkpoint') as HTMLInputElement
    const goalTextarea = document.getElementById('priority-goal') as HTMLTextAreaElement

    fireEvent.change(hoursInput, { target: { value: '10' } })
    fireEvent.change(checkpointInput, { target: { value: '2026-04-15' } })
    fireEvent.change(goalTextarea, { target: { value: 'Complete course' } })

    // Focus hours input and press Enter
    hoursInput.focus()
    fireEvent.keyDown(hoursInput, { key: 'Enter' })

    // Assert onAdd called with correct data
    await waitFor(() => {
      expect(mockOnAdd).toHaveBeenCalledWith({
        name: 'Learn TypeScript',
        type: 'flexible',
        weekly_hour_target: 10,
        checkpoint_date: '2026-04-15',
        initial_goal_text: 'Complete course',
      })
    })
  })

  it('Enter on textarea does NOT submit', async () => {
    const user = userEvent.setup()
    render(
      <AddPriorityForm
        availableKeywords={['P1']}
        onAdd={mockOnAdd}
        onCancel={mockOnCancel}
      />
    )

    // Step 1: Type name and press Enter
    const nameInput = screen.getByLabelText(/what do you want to track/i)
    await user.type(nameInput, 'Learn Go')
    fireEvent.keyDown(nameInput, { key: 'Enter' })

    // Step 2: Click Flexible type button
    const flexibleTypeBtn = screen.getByRole('button', { name: /flexible priority/i })
    await user.click(flexibleTypeBtn)

    // Step 3: Fill all required fields
    const hoursInput = document.getElementById('priority-hours') as HTMLInputElement
    const checkpointInput = document.getElementById('priority-checkpoint') as HTMLInputElement
    const goalTextarea = document.getElementById('priority-goal') as HTMLTextAreaElement

    fireEvent.change(hoursInput, { target: { value: '8' } })
    fireEvent.change(checkpointInput, { target: { value: '2026-05-01' } })
    fireEvent.change(goalTextarea, { target: { value: 'Build CLI app' } })

    // Focus textarea and press Enter
    goalTextarea.focus()
    fireEvent.keyDown(goalTextarea, { key: 'Enter' })

    // Assert onAdd was NOT called
    expect(mockOnAdd).not.toHaveBeenCalled()
  })
})
