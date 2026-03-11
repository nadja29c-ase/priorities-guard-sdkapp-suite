/**
 * Unit tests for DeliverableItem component (Increment 49)
 *
 * Tests:
 * 1. Renders deliverable text and checkbox — baseline
 * 2. Renders done state with strikethrough
 * 3. Optimistic toggle — checkbox updates immediately before onToggle resolves
 * 4. onToggle called with correct new value
 * 5. Double-tap while request in flight is ignored
 * 6. On error: checkbox reverts to pre-tap value, error message shown
 * 7. disabled prop blocks toggle
 * 8. Rename loading state preserved
 * 9. Delete confirmation flow
 * 10. Delete cancel
 * 11. Edit mode — double-click, save on blur, save on Enter, cancel on Escape, empty reverts
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { DeliverableItem } from '../components/DeliverableItem'
import type { Deliverable } from '../types'

const baseDeliverable: Deliverable = {
  id: 'del-1',
  name: 'Write unit tests',
  done: false,
}

const doneDeliverable: Deliverable = {
  id: 'del-2',
  name: 'Setup CI/CD',
  done: true,
}

describe('DeliverableItem', () => {
  const mockOnToggle = vi.fn().mockResolvedValue(undefined)
  const mockOnRename = vi.fn().mockResolvedValue(undefined)
  const mockOnDelete = vi.fn().mockResolvedValue(undefined)

  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ============================================================
  // Rendering
  // ============================================================

  describe('Rendering', () => {
    it('renders deliverable name and checkbox', () => {
      render(
        <DeliverableItem
          deliverable={baseDeliverable}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
        />
      )
      expect(screen.getByText('Write unit tests')).toBeInTheDocument()
      expect(screen.getByRole('checkbox')).toBeInTheDocument()
      expect(screen.getByRole('checkbox')).toHaveAttribute('aria-checked', 'false')
    })

    it('renders done state with strikethrough and aria-checked true', () => {
      render(
        <DeliverableItem
          deliverable={doneDeliverable}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
        />
      )
      expect(screen.getByRole('checkbox')).toHaveAttribute('aria-checked', 'true')
      expect(screen.getByText('Setup CI/CD')).toHaveClass('line-through')
    })
  })

  // ============================================================
  // Optimistic Toggle
  // ============================================================

  describe('Optimistic Toggle', () => {
    it('updates aria-checked immediately before onToggle resolves', async () => {
      let resolveToggle!: () => void
      const slowToggle = vi.fn().mockImplementation(
        () => new Promise<void>(resolve => { resolveToggle = resolve })
      )

      render(
        <DeliverableItem
          deliverable={baseDeliverable}
          onToggle={slowToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
        />
      )

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toHaveAttribute('aria-checked', 'false')

      fireEvent.click(checkbox)

      // Immediately after click — before server responds — checkbox should already show true
      expect(checkbox).toHaveAttribute('aria-checked', 'true')

      // Resolve and clean up
      act(() => resolveToggle())
      await waitFor(() => expect(slowToggle).toHaveBeenCalledTimes(1))
    })

    it('calls onToggle with the correct new value', async () => {
      render(
        <DeliverableItem
          deliverable={baseDeliverable}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
        />
      )

      fireEvent.click(screen.getByRole('checkbox'))

      await waitFor(() => {
        expect(mockOnToggle).toHaveBeenCalledWith('del-1', true)
      })
    })

    it('calls onToggle with false when toggling a done deliverable', async () => {
      render(
        <DeliverableItem
          deliverable={doneDeliverable}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
        />
      )

      fireEvent.click(screen.getByRole('checkbox'))

      await waitFor(() => {
        expect(mockOnToggle).toHaveBeenCalledWith('del-2', false)
      })
    })

    it('ignores double-tap while request is in flight', async () => {
      let resolveToggle!: () => void
      const slowToggle = vi.fn().mockImplementation(
        () => new Promise<void>(resolve => { resolveToggle = resolve })
      )

      render(
        <DeliverableItem
          deliverable={baseDeliverable}
          onToggle={slowToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
        />
      )

      const checkbox = screen.getByRole('checkbox')
      fireEvent.click(checkbox)
      fireEvent.click(checkbox) // second tap while in flight

      expect(slowToggle).toHaveBeenCalledTimes(1)

      act(() => resolveToggle())
      await waitFor(() => expect(slowToggle).toHaveBeenCalledTimes(1))
    })

    it('checkbox is not visually disabled (no opacity class) during toggle', async () => {
      let resolveToggle!: () => void
      const slowToggle = vi.fn().mockImplementation(
        () => new Promise<void>(resolve => { resolveToggle = resolve })
      )

      render(
        <DeliverableItem
          deliverable={baseDeliverable}
          onToggle={slowToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
        />
      )

      const checkbox = screen.getByRole('checkbox')
      fireEvent.click(checkbox)

      // Checkbox should NOT have opacity-50 during toggle
      expect(checkbox).not.toHaveClass('opacity-50')

      act(() => resolveToggle())
    })
  })

  // ============================================================
  // Error Handling
  // ============================================================

  describe('Error Handling', () => {
    it('reverts checkbox to pre-tap value on toggle error', async () => {
      const failingToggle = vi.fn().mockRejectedValue(new Error('Network error'))

      render(
        <DeliverableItem
          deliverable={baseDeliverable}
          onToggle={failingToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
        />
      )

      const checkbox = screen.getByRole('checkbox')
      fireEvent.click(checkbox)

      // Optimistic: immediately true
      expect(checkbox).toHaveAttribute('aria-checked', 'true')

      // After error resolves: reverted to false
      await waitFor(() => {
        expect(checkbox).toHaveAttribute('aria-checked', 'false')
      })
    })

    it('shows error message on toggle failure', async () => {
      const failingToggle = vi.fn().mockRejectedValue(new Error('Network error'))

      render(
        <DeliverableItem
          deliverable={baseDeliverable}
          onToggle={failingToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
        />
      )

      fireEvent.click(screen.getByRole('checkbox'))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('Network error')
      })
    })

    it('allows toggle again after a failed request', async () => {
      let callCount = 0
      const toggleWithFirstFail = vi.fn().mockImplementation(() => {
        callCount++
        if (callCount === 1) return Promise.reject(new Error('Network error'))
        return Promise.resolve()
      })

      render(
        <DeliverableItem
          deliverable={baseDeliverable}
          onToggle={toggleWithFirstFail}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
        />
      )

      const checkbox = screen.getByRole('checkbox')
      fireEvent.click(checkbox)

      // Wait for error and revert
      await waitFor(() => {
        expect(checkbox).toHaveAttribute('aria-checked', 'false')
      })

      // Should be able to toggle again
      fireEvent.click(checkbox)

      await waitFor(() => {
        expect(toggleWithFirstFail).toHaveBeenCalledTimes(2)
      })
    })
  })

  // ============================================================
  // Disabled State
  // ============================================================

  describe('Disabled State', () => {
    it('does not call onToggle when disabled', () => {
      render(
        <DeliverableItem
          deliverable={baseDeliverable}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
          disabled={true}
        />
      )

      fireEvent.click(screen.getByRole('checkbox'))
      expect(mockOnToggle).not.toHaveBeenCalled()
    })

    it('does not show edit/delete buttons when disabled', () => {
      render(
        <DeliverableItem
          deliverable={baseDeliverable}
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

  // ============================================================
  // Edit Mode
  // ============================================================

  describe('Edit Mode', () => {
    it('enters edit mode on double-click', () => {
      render(
        <DeliverableItem
          deliverable={baseDeliverable}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
        />
      )

      fireEvent.doubleClick(screen.getByText('Write unit tests'))
      expect(screen.getByRole('textbox')).toBeInTheDocument()
      expect(screen.getByRole('textbox')).toHaveValue('Write unit tests')
    })

    it('saves rename on blur when text changed', async () => {
      render(
        <DeliverableItem
          deliverable={baseDeliverable}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
        />
      )

      fireEvent.doubleClick(screen.getByText('Write unit tests'))
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'Write integration tests' } })
      fireEvent.blur(input)

      await waitFor(() => {
        expect(mockOnRename).toHaveBeenCalledWith('del-1', 'Write integration tests')
      })
    })

    it('saves rename on Enter key', async () => {
      render(
        <DeliverableItem
          deliverable={baseDeliverable}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
        />
      )

      fireEvent.doubleClick(screen.getByText('Write unit tests'))
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'Write integration tests' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      await waitFor(() => {
        expect(mockOnRename).toHaveBeenCalledWith('del-1', 'Write integration tests')
      })
    })

    it('cancels edit on Escape and reverts text', () => {
      render(
        <DeliverableItem
          deliverable={baseDeliverable}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
        />
      )

      fireEvent.doubleClick(screen.getByText('Write unit tests'))
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'Changed' } })
      fireEvent.keyDown(input, { key: 'Escape' })

      expect(mockOnRename).not.toHaveBeenCalled()
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
      expect(screen.getByText('Write unit tests')).toBeInTheDocument()
    })

    it('reverts to original when empty text submitted', () => {
      render(
        <DeliverableItem
          deliverable={baseDeliverable}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
        />
      )

      fireEvent.doubleClick(screen.getByText('Write unit tests'))
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: '' } })
      fireEvent.blur(input)

      expect(mockOnRename).not.toHaveBeenCalled()
      expect(screen.getByText('Write unit tests')).toBeInTheDocument()
    })
  })

  // ============================================================
  // Delete Flow
  // ============================================================

  describe('Delete Flow', () => {
    it('shows confirmation and calls onDelete on confirm', async () => {
      render(
        <DeliverableItem
          deliverable={baseDeliverable}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
        />
      )

      fireEvent.click(screen.getByRole('button', { name: /delete/i }))
      expect(screen.getByRole('button', { name: /confirm remove/i })).toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: /confirm remove/i }))

      await waitFor(() => {
        expect(mockOnDelete).toHaveBeenCalledWith('del-1')
      })
    })

    it('cancels delete on No click', () => {
      render(
        <DeliverableItem
          deliverable={baseDeliverable}
          onToggle={mockOnToggle}
          onRename={mockOnRename}
          onDelete={mockOnDelete}
        />
      )

      fireEvent.click(screen.getByRole('button', { name: /delete/i }))
      fireEvent.click(screen.getByRole('button', { name: /no/i }))

      expect(mockOnDelete).not.toHaveBeenCalled()
      expect(screen.getByText('Write unit tests')).toBeInTheDocument()
    })
  })
})
