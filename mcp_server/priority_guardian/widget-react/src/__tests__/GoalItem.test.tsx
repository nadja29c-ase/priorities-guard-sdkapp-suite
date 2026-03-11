/**
 * Unit tests for GoalItem component (Increment 32, updated Inc 49)
 *
 * Tests:
 * 1. Renders goal text and toggle — baseline
 * 2. Double-click enters edit mode
 * 3. Edit save on blur
 * 4. Edit cancel on Escape
 * 5. Edit save on Enter
 * 6. Empty text reverts
 * 7. Delete confirmation flow
 * 8. Delete cancel
 * 9. Hover shows action buttons
 * 10. Optimistic toggle — checkbox updates immediately before onToggle resolves
 * 11. Double-tap while request in flight is ignored
 * 12. On error: checkbox reverts to pre-tap value
 * 13. Checkbox not visually disabled during toggle
 * 14. disabled prop blocks toggle
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { GoalItem } from '../components/GoalItem'
import type { Goal } from '../types'

const baseGoal: Goal = {
  id: 'goal-1',
  text: 'Complete project documentation',
  achieved: false,
}

const achievedGoal: Goal = {
  id: 'goal-2',
  text: 'Setup CI/CD pipeline',
  achieved: true,
}

describe('GoalItem', () => {
  const mockOnToggle = vi.fn().mockResolvedValue(undefined)
  const mockOnRename = vi.fn().mockResolvedValue(undefined)
  const mockOnDelete = vi.fn().mockResolvedValue(undefined)

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders goal text and toggle checkbox', () => {
      render(
        <GoalItem
          goal={baseGoal}
          onToggle={mockOnToggle}
        />
      )

      expect(screen.getByText('Complete project documentation')).toBeInTheDocument()
      expect(screen.getByRole('checkbox')).toBeInTheDocument()
      expect(screen.getByRole('checkbox')).toHaveAttribute('aria-checked', 'false')
    })

    it('renders achieved state with strikethrough', () => {
      render(
        <GoalItem
          goal={achievedGoal}
          onToggle={mockOnToggle}
        />
      )

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toHaveAttribute('aria-checked', 'true')

      const text = screen.getByText('Setup CI/CD pipeline')
      expect(text).toHaveClass('line-through')
    })

    it('toggles achieved state on checkbox click', async () => {
      render(
        <GoalItem
          goal={baseGoal}
          onToggle={mockOnToggle}
        />
      )

      const checkbox = screen.getByRole('checkbox')
      fireEvent.click(checkbox)

      await waitFor(() => {
        expect(mockOnToggle).toHaveBeenCalledWith('goal-1', true)
      })
    })
  })

  describe('Edit Mode', () => {
    it('enters edit mode on double-click', async () => {
      render(
        <GoalItem
          goal={baseGoal}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
        />
      )

      const text = screen.getByText('Complete project documentation')
      fireEvent.doubleClick(text)

      expect(screen.getByRole('textbox')).toBeInTheDocument()
      expect(screen.getByRole('textbox')).toHaveValue('Complete project documentation')
    })

    it('saves edit on blur when text changed', async () => {
      render(
        <GoalItem
          goal={baseGoal}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
        />
      )

      // Enter edit mode
      const text = screen.getByText('Complete project documentation')
      fireEvent.doubleClick(text)

      // Change text
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'Updated documentation' } })
      fireEvent.blur(input)

      await waitFor(() => {
        expect(mockOnRename).toHaveBeenCalledWith('goal-1', 'Updated documentation')
      })
    })

    it('cancels edit on Escape key and reverts text', async () => {
      render(
        <GoalItem
          goal={baseGoal}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
        />
      )

      // Enter edit mode
      const text = screen.getByText('Complete project documentation')
      fireEvent.doubleClick(text)

      // Change text
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'Changed text' } })

      // Press Escape
      fireEvent.keyDown(input, { key: 'Escape' })

      // Should NOT call onRename
      expect(mockOnRename).not.toHaveBeenCalled()

      // Should show original text (no longer in edit mode)
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
      expect(screen.getByText('Complete project documentation')).toBeInTheDocument()
    })

    it('saves edit on Enter key', async () => {
      render(
        <GoalItem
          goal={baseGoal}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
        />
      )

      // Enter edit mode
      const text = screen.getByText('Complete project documentation')
      fireEvent.doubleClick(text)

      // Change text and press Enter
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'New goal text' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      await waitFor(() => {
        expect(mockOnRename).toHaveBeenCalledWith('goal-1', 'New goal text')
      })
    })

    it('reverts to original when text is empty', async () => {
      render(
        <GoalItem
          goal={baseGoal}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
        />
      )

      // Enter edit mode
      const text = screen.getByText('Complete project documentation')
      fireEvent.doubleClick(text)

      // Clear text and blur
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: '' } })
      fireEvent.blur(input)

      // Should NOT call onRename with empty text
      expect(mockOnRename).not.toHaveBeenCalled()

      // Should show original text
      expect(screen.getByText('Complete project documentation')).toBeInTheDocument()
    })

    it('does not enter edit mode when disabled', () => {
      render(
        <GoalItem
          goal={baseGoal}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
          disabled={true}
        />
      )

      const text = screen.getByText('Complete project documentation')
      fireEvent.doubleClick(text)

      // Should NOT enter edit mode
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    })

    it('does not enter edit mode when onRename not provided', () => {
      render(
        <GoalItem
          goal={baseGoal}
          onToggle={mockOnToggle}
          // onRename not provided
        />
      )

      const text = screen.getByText('Complete project documentation')
      fireEvent.doubleClick(text)

      // Should NOT enter edit mode
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    })
  })

  describe('Delete Confirmation', () => {
    it('shows delete confirmation flow and calls onDelete', async () => {
      render(
        <GoalItem
          goal={baseGoal}
          onToggle={mockOnToggle}
          onDelete={mockOnDelete}
        />
      )

      // Find and click delete button
      const deleteButton = screen.getByRole('button', { name: /delete/i })
      fireEvent.click(deleteButton)

      // Should show confirmation
      expect(screen.getByText(/remove "complete project documentation"\?/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /confirm remove/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /cancel remove/i })).toBeInTheDocument()

      // Click Yes
      fireEvent.click(screen.getByRole('button', { name: /confirm remove/i }))

      await waitFor(() => {
        expect(mockOnDelete).toHaveBeenCalledWith('goal-1')
      })
    })

    it('cancels delete on No click', () => {
      render(
        <GoalItem
          goal={baseGoal}
          onToggle={mockOnToggle}
          onDelete={mockOnDelete}
        />
      )

      // Find and click delete button
      const deleteButton = screen.getByRole('button', { name: /delete/i })
      fireEvent.click(deleteButton)

      // Click No
      fireEvent.click(screen.getByRole('button', { name: /cancel remove/i }))

      // Should NOT call onDelete
      expect(mockOnDelete).not.toHaveBeenCalled()

      // Should return to normal view
      expect(screen.queryByText(/remove "complete project documentation"\?/i)).not.toBeInTheDocument()
      expect(screen.getByText('Complete project documentation')).toBeInTheDocument()
    })
  })

  describe('Action Buttons', () => {
    it('renders edit and delete buttons when handlers provided', () => {
      render(
        <GoalItem
          goal={baseGoal}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
        />
      )

      // Edit button
      expect(screen.getByRole('button', { name: /edit/i })).toBeInTheDocument()

      // Delete button
      expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument()
    })

    it('enters edit mode when edit button clicked', async () => {
      render(
        <GoalItem
          goal={baseGoal}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
        />
      )

      const editButton = screen.getByRole('button', { name: /edit/i })
      fireEvent.click(editButton)

      expect(screen.getByRole('textbox')).toBeInTheDocument()
    })

    it('does not render action buttons when disabled', () => {
      render(
        <GoalItem
          goal={baseGoal}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
          disabled={true}
        />
      )

      expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument()
    })
  })

  describe('Optimistic Toggle', () => {
    it('updates aria-checked immediately before onToggle resolves', async () => {
      let resolveToggle!: () => void
      const slowToggle = vi.fn().mockImplementation(
        () => new Promise<void>(resolve => { resolveToggle = resolve })
      )

      render(
        <GoalItem
          goal={baseGoal}
          onToggle={slowToggle}
        />
      )

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toHaveAttribute('aria-checked', 'false')

      fireEvent.click(checkbox)

      // Immediately — before server responds — should already show true
      expect(checkbox).toHaveAttribute('aria-checked', 'true')

      act(() => resolveToggle())
      await waitFor(() => expect(slowToggle).toHaveBeenCalledTimes(1))
    })

    it('ignores double-tap while request is in flight', async () => {
      let resolveToggle!: () => void
      const slowToggle = vi.fn().mockImplementation(
        () => new Promise<void>(resolve => { resolveToggle = resolve })
      )

      render(
        <GoalItem
          goal={baseGoal}
          onToggle={slowToggle}
        />
      )

      const checkbox = screen.getByRole('checkbox')
      fireEvent.click(checkbox)
      fireEvent.click(checkbox) // second tap while in flight

      expect(slowToggle).toHaveBeenCalledTimes(1)

      act(() => resolveToggle())
      await waitFor(() => expect(slowToggle).toHaveBeenCalledTimes(1))
    })

    it('reverts aria-checked to pre-tap value on toggle error', async () => {
      const failingToggle = vi.fn().mockRejectedValue(new Error('Network error'))

      render(
        <GoalItem
          goal={baseGoal}
          onToggle={failingToggle}
        />
      )

      const checkbox = screen.getByRole('checkbox')
      fireEvent.click(checkbox)

      // Optimistic: immediately true
      expect(checkbox).toHaveAttribute('aria-checked', 'true')

      // After error: reverted to false
      await waitFor(() => {
        expect(checkbox).toHaveAttribute('aria-checked', 'false')
      })
    })

    it('clears optimistic state when achieved prop changes', () => {
      const { rerender } = render(
        <GoalItem
          goal={baseGoal}
          onToggle={mockOnToggle}
        />
      )

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toHaveAttribute('aria-checked', 'false')

      // Simulate prop change from parent (server confirmed toggle)
      rerender(
        <GoalItem
          goal={{ ...baseGoal, achieved: true }}
          onToggle={mockOnToggle}
        />
      )

      // Should reflect the new prop value
      expect(checkbox).toHaveAttribute('aria-checked', 'true')
    })

    it('checkbox is not visually disabled during toggle', async () => {
      let resolveToggle!: () => void
      const slowToggle = vi.fn().mockImplementation(
        () => new Promise<void>(resolve => { resolveToggle = resolve })
      )

      render(
        <GoalItem
          goal={baseGoal}
          onToggle={slowToggle}
        />
      )

      fireEvent.click(screen.getByRole('checkbox'))

      // The inner span should not have opacity-50 during toggle
      const span = screen.getByRole('checkbox').querySelector('span')
      expect(span).not.toHaveClass('opacity-50')

      act(() => resolveToggle())
    })

    it('disables checkbox when disabled prop is true', () => {
      render(
        <GoalItem
          goal={baseGoal}
          onToggle={mockOnToggle}
          disabled={true}
        />
      )

      fireEvent.click(screen.getByRole('checkbox'))
      expect(mockOnToggle).not.toHaveBeenCalled()
    })
  })

  describe('Error Handling', () => {
    it('shows error message when toggle fails', async () => {
      const failingToggle = vi.fn().mockRejectedValue(new Error('Network error'))

      render(
        <GoalItem
          goal={baseGoal}
          onToggle={failingToggle}
        />
      )

      const checkbox = screen.getByRole('checkbox')
      fireEvent.click(checkbox)

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('Network error')
      })
    })

    it('shows error message when rename fails', async () => {
      const failingRename = vi.fn().mockRejectedValue(new Error('Save failed'))

      render(
        <GoalItem
          goal={baseGoal}
          onToggle={mockOnToggle}
          onRename={failingRename}
        />
      )

      // Enter edit mode
      fireEvent.doubleClick(screen.getByText('Complete project documentation'))

      // Change and save
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'New text' } })
      fireEvent.blur(input)

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('Save failed')
      })
    })

    it('reverts text on rename error', async () => {
      const failingRename = vi.fn().mockRejectedValue(new Error('Save failed'))

      render(
        <GoalItem
          goal={baseGoal}
          onToggle={mockOnToggle}
          onRename={failingRename}
        />
      )

      // Enter edit mode
      fireEvent.doubleClick(screen.getByText('Complete project documentation'))

      // Change and save
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'New text' } })
      fireEvent.blur(input)

      await waitFor(() => {
        // After error, input value should be reverted to original
        expect(screen.getByRole('textbox')).toHaveValue('Complete project documentation')
      })
    })
  })
})
