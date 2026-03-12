/**
 * Unit tests for DeleteConfirmation component (Increment 60)
 *
 * Tests:
 * 1. Tab on last focusable element wraps focus to first and calls preventDefault
 * 2. Shift+Tab on first focusable element wraps focus to last and calls preventDefault
 * 3. Tab on a middle element does not call preventDefault
 * 4. When isDeleting=true (both buttons disabled): no focusable elements matched, no error thrown
 * 5. ESC still calls onCancel (existing behaviour unchanged)
 * 6. Cancel button receives focus on mount (existing behaviour unchanged)
 *
 * Note: Focus trap tests mock offsetParent since JSDOM returns null for it.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DeleteConfirmation } from '../components/DeleteConfirmation'

describe('DeleteConfirmation', () => {
  const mockOnConfirm = vi.fn()
  const mockOnCancel = vi.fn()

  // Mock offsetParent for JSDOM (always returns null by default)
  const originalOffsetParent = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetParent')

  beforeEach(() => {
    vi.clearAllMocks()
    // Make offsetParent return the element's parentElement (simulates visible element)
    Object.defineProperty(HTMLElement.prototype, 'offsetParent', {
      configurable: true,
      get() {
        // Return null for disabled buttons (simulates hidden), parent otherwise
        if (this.disabled) return null
        return this.parentElement
      },
    })
  })

  afterEach(() => {
    // Restore original offsetParent
    if (originalOffsetParent) {
      Object.defineProperty(HTMLElement.prototype, 'offsetParent', originalOffsetParent)
    }
  })

  const defaultProps = {
    itemName: 'Test Item',
    itemType: 'priority' as const,
    onConfirm: mockOnConfirm,
    onCancel: mockOnCancel,
    isDeleting: false,
  }

  // ============================================================
  // Focus on Mount
  // ============================================================

  describe('Focus on Mount', () => {
    it('Cancel button receives focus on mount', () => {
      render(<DeleteConfirmation {...defaultProps} />)

      const cancelButton = screen.getByRole('button', { name: /cancel/i })
      expect(document.activeElement).toBe(cancelButton)
    })
  })

  // ============================================================
  // ESC Key Handling
  // ============================================================

  describe('ESC Key Handling', () => {
    it('ESC calls onCancel', () => {
      render(<DeleteConfirmation {...defaultProps} />)

      fireEvent.keyDown(document, { key: 'Escape' })

      expect(mockOnCancel).toHaveBeenCalledTimes(1)
    })

    it('ESC does not call onCancel when isDeleting', () => {
      render(<DeleteConfirmation {...defaultProps} isDeleting={true} />)

      fireEvent.keyDown(document, { key: 'Escape' })

      expect(mockOnCancel).not.toHaveBeenCalled()
    })
  })

  // ============================================================
  // Focus Trap
  // ============================================================

  describe('Focus Trap', () => {
    it('Tab on last focusable element wraps focus to first and calls preventDefault', () => {
      render(<DeleteConfirmation {...defaultProps} />)

      const buttons = screen.getAllByRole('button')
      const cancelButton = buttons.find(b => b.textContent?.toLowerCase().includes('cancel'))!
      const deleteButton = buttons.find(b => b.textContent?.toLowerCase().includes('delete'))!

      // Focus the last button (Delete)
      deleteButton.focus()
      expect(document.activeElement).toBe(deleteButton)

      // Create and dispatch Tab event
      const tabEvent = new KeyboardEvent('keydown', {
        key: 'Tab',
        shiftKey: false,
        bubbles: true,
        cancelable: true,
      })
      const preventDefaultSpy = vi.spyOn(tabEvent, 'preventDefault')

      document.dispatchEvent(tabEvent)

      expect(preventDefaultSpy).toHaveBeenCalled()
      expect(document.activeElement).toBe(cancelButton)
    })

    it('Shift+Tab on first focusable element wraps focus to last and calls preventDefault', () => {
      render(<DeleteConfirmation {...defaultProps} />)

      const buttons = screen.getAllByRole('button')
      const cancelButton = buttons.find(b => b.textContent?.toLowerCase().includes('cancel'))!
      const deleteButton = buttons.find(b => b.textContent?.toLowerCase().includes('delete'))!

      // Focus the first button (Cancel)
      cancelButton.focus()
      expect(document.activeElement).toBe(cancelButton)

      // Create and dispatch Shift+Tab event
      const shiftTabEvent = new KeyboardEvent('keydown', {
        key: 'Tab',
        shiftKey: true,
        bubbles: true,
        cancelable: true,
      })
      const preventDefaultSpy = vi.spyOn(shiftTabEvent, 'preventDefault')

      document.dispatchEvent(shiftTabEvent)

      expect(preventDefaultSpy).toHaveBeenCalled()
      expect(document.activeElement).toBe(deleteButton)
    })

    it('Tab on a middle element does not call preventDefault', () => {
      // With only 2 buttons (Cancel and Delete), there's no "middle" element.
      // This test verifies that Tab from first (not last) doesn't preventDefault.
      render(<DeleteConfirmation {...defaultProps} />)

      const buttons = screen.getAllByRole('button')
      const cancelButton = buttons.find(b => b.textContent?.toLowerCase().includes('cancel'))!

      // Focus Cancel (first button)
      cancelButton.focus()

      // Tab without Shift - Cancel is first, not last, so shouldn't preventDefault
      const tabEvent = new KeyboardEvent('keydown', {
        key: 'Tab',
        shiftKey: false,
        bubbles: true,
        cancelable: true,
      })
      const preventDefaultSpy = vi.spyOn(tabEvent, 'preventDefault')

      document.dispatchEvent(tabEvent)

      // Since Cancel is not the last element, preventDefault should NOT be called
      expect(preventDefaultSpy).not.toHaveBeenCalled()
    })

    it('When isDeleting=true (both buttons disabled): no focusable elements, no error thrown', () => {
      // This should not throw even when no focusable elements exist
      expect(() => {
        render(<DeleteConfirmation {...defaultProps} isDeleting={true} />)

        // Try to Tab - should not throw
        const tabEvent = new KeyboardEvent('keydown', {
          key: 'Tab',
          shiftKey: false,
          bubbles: true,
          cancelable: true,
        })
        document.dispatchEvent(tabEvent)
      }).not.toThrow()
    })
  })

  // ============================================================
  // Button Actions
  // ============================================================

  describe('Button Actions', () => {
    it('Cancel button calls onCancel', () => {
      render(<DeleteConfirmation {...defaultProps} />)

      fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

      expect(mockOnCancel).toHaveBeenCalledTimes(1)
    })

    it('Delete button calls onConfirm', () => {
      render(<DeleteConfirmation {...defaultProps} />)

      const deleteButton = screen.getAllByRole('button').find(b =>
        b.textContent?.toLowerCase().includes('delete')
      )!
      fireEvent.click(deleteButton)

      expect(mockOnConfirm).toHaveBeenCalledTimes(1)
    })

    it('Buttons are disabled when isDeleting', () => {
      render(<DeleteConfirmation {...defaultProps} isDeleting={true} />)

      const buttons = screen.getAllByRole('button')
      buttons.forEach(button => {
        expect(button).toBeDisabled()
      })
    })
  })

  // ============================================================
  // Backdrop Click
  // ============================================================

  describe('Backdrop Click', () => {
    it('Clicking backdrop calls onCancel', () => {
      render(<DeleteConfirmation {...defaultProps} />)

      const backdrop = screen.getByRole('dialog')
      fireEvent.click(backdrop)

      expect(mockOnCancel).toHaveBeenCalledTimes(1)
    })

    it('Clicking inside modal does not call onCancel', () => {
      render(<DeleteConfirmation {...defaultProps} />)

      // Find the modal content div (inside the backdrop)
      const heading = screen.getByRole('heading')
      fireEvent.click(heading)

      expect(mockOnCancel).not.toHaveBeenCalled()
    })
  })
})
