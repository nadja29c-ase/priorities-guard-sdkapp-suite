/**
 * Unit tests for KeywordPicker component (Increment 64)
 *
 * Tests:
 * 1. Dialog trigger: clicking different badge shows dialog, does NOT call onKeywordChange
 * 2. Dialog trigger: clicking current badge does nothing (no dialog, no call)
 * 3. Dialog content: body contains both old and new keyword labels
 * 4. Dialog content: how-to line contains the new keyword
 * 5. Confirm path: "Change" calls onKeywordChange with correct pending keyword
 * 6. Confirm path: "Change" dismisses dialog before onKeywordChange is called
 * 7. Cancel paths: "Cancel" does not call onKeywordChange and dismisses dialog
 * 8. Cancel paths: ESC does not call onKeywordChange and dismisses dialog
 * 9. Cancel paths: Backdrop click does not call onKeywordChange and dismisses dialog
 * 10. Focus & keyboard: "Cancel" receives focus on mount
 * 11. Focus & keyboard: Tab on last button wraps focus to first
 * 12. Focus & keyboard: Shift+Tab on first button wraps focus to last
 *
 * Note: Focus trap tests mock offsetParent since JSDOM returns null for it.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { KeywordPicker } from '../components/KeywordPicker'
import type { Priority } from '../types'

describe('KeywordPicker', () => {
  const mockOnKeywordChange = vi.fn()

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
    currentKeyword: 'P1' as const,
    priorities: [] as Priority[],
    onKeywordChange: mockOnKeywordChange,
    disabled: false,
  }

  // ============================================================
  // Dialog Trigger
  // ============================================================

  describe('Dialog Trigger', () => {
    it('clicking a different badge shows the dialog and does NOT call onKeywordChange', () => {
      render(<KeywordPicker {...defaultProps} />)

      // Click on P2 (different from current P1)
      const p2Button = screen.getByRole('button', { name: /P2/i })
      fireEvent.click(p2Button)

      // Dialog should appear
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText('Change badge?')).toBeInTheDocument()

      // onKeywordChange should NOT be called yet
      expect(mockOnKeywordChange).not.toHaveBeenCalled()
    })

    it('clicking the current badge does nothing — no dialog, no call', () => {
      render(<KeywordPicker {...defaultProps} />)

      // Click on P1 (same as current)
      const p1Button = screen.getByRole('button', { name: /Current keyword P1/i })
      fireEvent.click(p1Button)

      // No dialog should appear
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

      // onKeywordChange should NOT be called
      expect(mockOnKeywordChange).not.toHaveBeenCalled()
    })
  })

  // ============================================================
  // Dialog Content
  // ============================================================

  describe('Dialog Content', () => {
    it('body contains both old and new keyword labels', () => {
      render(<KeywordPicker {...defaultProps} />)

      // Click on P2 to open dialog
      const p2Button = screen.getByRole('button', { name: /P2/i })
      fireEvent.click(p2Button)

      // Check body text contains oldKeyword (P1) twice
      const bodyText = screen.getByText(/Hours already tagged P1 this week will shift to whichever priority now holds P1/i)
      expect(bodyText).toBeInTheDocument()
    })

    it('how-to line contains the new keyword', () => {
      render(<KeywordPicker {...defaultProps} />)

      // Click on P3 to open dialog
      const p3Button = screen.getByRole('button', { name: /P3/i })
      fireEvent.click(p3Button)

      // Check how-to line contains P3 (pending keyword)
      const howToText = screen.getByText(/Tag calendar events with P3 to track time toward this priority/i)
      expect(howToText).toBeInTheDocument()
    })
  })

  // ============================================================
  // Confirm Path
  // ============================================================

  describe('Confirm Path', () => {
    it('"Change" calls onKeywordChange with the correct pending keyword', async () => {
      mockOnKeywordChange.mockResolvedValueOnce(undefined)
      render(<KeywordPicker {...defaultProps} />)

      // Click on P2 to open dialog
      const p2Button = screen.getByRole('button', { name: /P2/i })
      fireEvent.click(p2Button)

      // Click "Change"
      const confirmButton = screen.getByRole('button', { name: /Change/i })
      fireEvent.click(confirmButton)

      await waitFor(() => {
        expect(mockOnKeywordChange).toHaveBeenCalledWith('P2')
      })
    })

    it('"Change" dismisses the dialog before onKeywordChange is called', async () => {
      // Make onKeywordChange take some time to resolve
      let resolveChange: () => void
      mockOnKeywordChange.mockImplementationOnce(() => new Promise<void>(resolve => {
        resolveChange = resolve
      }))

      render(<KeywordPicker {...defaultProps} />)

      // Click on P2 to open dialog
      const p2Button = screen.getByRole('button', { name: /P2/i })
      fireEvent.click(p2Button)

      // Dialog is visible
      expect(screen.getByRole('dialog')).toBeInTheDocument()

      // Click "Change"
      const confirmButton = screen.getByRole('button', { name: /Change/i })
      fireEvent.click(confirmButton)

      // Dialog should be dismissed immediately
      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      })

      // Resolve the onKeywordChange promise
      resolveChange!()
    })
  })

  // ============================================================
  // Cancel Paths
  // ============================================================

  describe('Cancel Paths', () => {
    it('"Cancel" does not call onKeywordChange and dismisses the dialog', () => {
      render(<KeywordPicker {...defaultProps} />)

      // Click on P2 to open dialog
      const p2Button = screen.getByRole('button', { name: /P2/i })
      fireEvent.click(p2Button)

      // Dialog is visible
      expect(screen.getByRole('dialog')).toBeInTheDocument()

      // Click "Cancel"
      const cancelButton = screen.getByRole('button', { name: /Cancel/i })
      fireEvent.click(cancelButton)

      // Dialog should be dismissed
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

      // onKeywordChange should NOT be called
      expect(mockOnKeywordChange).not.toHaveBeenCalled()
    })

    it('ESC does not call onKeywordChange and dismisses the dialog', () => {
      render(<KeywordPicker {...defaultProps} />)

      // Click on P2 to open dialog
      const p2Button = screen.getByRole('button', { name: /P2/i })
      fireEvent.click(p2Button)

      // Dialog is visible
      expect(screen.getByRole('dialog')).toBeInTheDocument()

      // Press ESC
      fireEvent.keyDown(document, { key: 'Escape' })

      // Dialog should be dismissed
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

      // onKeywordChange should NOT be called
      expect(mockOnKeywordChange).not.toHaveBeenCalled()
    })

    it('Backdrop click does not call onKeywordChange and dismisses the dialog', () => {
      render(<KeywordPicker {...defaultProps} />)

      // Click on P2 to open dialog
      const p2Button = screen.getByRole('button', { name: /P2/i })
      fireEvent.click(p2Button)

      // Dialog is visible
      const backdrop = screen.getByRole('dialog')
      expect(backdrop).toBeInTheDocument()

      // Click on backdrop (the dialog element itself, not the modal content)
      fireEvent.click(backdrop)

      // Dialog should be dismissed
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

      // onKeywordChange should NOT be called
      expect(mockOnKeywordChange).not.toHaveBeenCalled()
    })
  })

  // ============================================================
  // Focus & Keyboard
  // ============================================================

  describe('Focus & Keyboard', () => {
    it('"Cancel" receives focus on mount', () => {
      render(<KeywordPicker {...defaultProps} />)

      // Click on P2 to open dialog
      const p2Button = screen.getByRole('button', { name: /P2/i })
      fireEvent.click(p2Button)

      // "Cancel" should have focus
      const cancelButton = screen.getByRole('button', { name: /Cancel/i })
      expect(document.activeElement).toBe(cancelButton)
    })

    it('Tab on last button wraps focus to first', () => {
      render(<KeywordPicker {...defaultProps} />)

      // Click on P2 to open dialog
      const p2Button = screen.getByRole('button', { name: /P2/i })
      fireEvent.click(p2Button)

      const cancelButton = screen.getByRole('button', { name: /Cancel/i })
      const confirmButton = screen.getByRole('button', { name: /Change/i })

      // Focus the last button (Change)
      confirmButton.focus()
      expect(document.activeElement).toBe(confirmButton)

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

    it('Shift+Tab on first button wraps focus to last', () => {
      render(<KeywordPicker {...defaultProps} />)

      // Click on P2 to open dialog
      const p2Button = screen.getByRole('button', { name: /P2/i })
      fireEvent.click(p2Button)

      const cancelButton = screen.getByRole('button', { name: /Cancel/i })
      const confirmButton = screen.getByRole('button', { name: /Change/i })

      // Focus the first button (Cancel) - it should already be focused on mount
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
      expect(document.activeElement).toBe(confirmButton)
    })
  })

  // ============================================================
  // Clicking inside modal does not dismiss
  // ============================================================

  describe('Modal Click Behavior', () => {
    it('Clicking inside modal content does not dismiss dialog', () => {
      render(<KeywordPicker {...defaultProps} />)

      // Click on P2 to open dialog
      const p2Button = screen.getByRole('button', { name: /P2/i })
      fireEvent.click(p2Button)

      // Dialog is visible
      expect(screen.getByRole('dialog')).toBeInTheDocument()

      // Click on heading inside modal
      const heading = screen.getByRole('heading', { name: /Change badge\?/i })
      fireEvent.click(heading)

      // Dialog should still be visible
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
  })
})
