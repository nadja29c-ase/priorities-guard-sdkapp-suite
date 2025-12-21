import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SaveModal } from '../components/SaveModal'

describe('SaveModal', () => {
  it('renders nothing when not open', () => {
    render(
      <SaveModal
        isOpen={false}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        isSaving={false}
      />
    )

    expect(screen.queryByText('Save Board?')).not.toBeInTheDocument()
  })

  it('renders modal when open', () => {
    render(
      <SaveModal
        isOpen={true}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        isSaving={false}
      />
    )

    expect(screen.getByText('Save Board?')).toBeInTheDocument()
    expect(screen.getByText('Cancel')).toBeInTheDocument()
    expect(screen.getByText('Save')).toBeInTheDocument()
  })

  it('calls onCancel when Cancel clicked', () => {
    const onCancel = vi.fn()

    render(
      <SaveModal
        isOpen={true}
        onCancel={onCancel}
        onConfirm={vi.fn()}
        isSaving={false}
      />
    )

    fireEvent.click(screen.getByText('Cancel'))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('calls onConfirm when Save clicked', () => {
    const onConfirm = vi.fn()

    render(
      <SaveModal
        isOpen={true}
        onCancel={vi.fn()}
        onConfirm={onConfirm}
        isSaving={false}
      />
    )

    fireEvent.click(screen.getByText('Save'))
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('shows Saving... text when saving', () => {
    render(
      <SaveModal
        isOpen={true}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        isSaving={true}
      />
    )

    expect(screen.getByText('Saving...')).toBeInTheDocument()
  })

  it('closes when clicking overlay background', () => {
    const onCancel = vi.fn()

    render(
      <SaveModal
        isOpen={true}
        onCancel={onCancel}
        onConfirm={vi.fn()}
        isSaving={false}
      />
    )

    // Click the overlay (first div with fixed class)
    const overlay = screen.getByText('Save Board?').parentElement?.parentElement
    if (overlay) {
      fireEvent.click(overlay)
      expect(onCancel).toHaveBeenCalledOnce()
    }
  })
})
