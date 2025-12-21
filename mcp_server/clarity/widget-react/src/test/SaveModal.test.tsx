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

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument()
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

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
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

    fireEvent.click(screen.getByRole('button', { name: /save/i }))
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('shows Saving... text and disables buttons when saving', () => {
    render(
      <SaveModal
        isOpen={true}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        isSaving={true}
      />
    )

    expect(screen.getByRole('button', { name: /saving/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeDisabled()
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

    fireEvent.click(screen.getByRole('dialog'))
    expect(onCancel).toHaveBeenCalledOnce()
  })
})
