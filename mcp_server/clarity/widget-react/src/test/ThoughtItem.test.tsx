import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ThoughtItem } from '../components/ThoughtItem'
import type { ThoughtItem as ThoughtItemType } from '../types'

describe('ThoughtItem', () => {
  it('renders text correctly', () => {
    const item: ThoughtItemType = { text: 'Test thought' }

    render(<ThoughtItem item={item} />)
    expect(screen.getByText('Test thought')).toBeInTheDocument()
  })

  it('renders object item without priority correctly', () => {
    const item: ThoughtItemType = { text: 'Unprioritized item' }

    render(<ThoughtItem item={item} />)
    expect(screen.getByText('Unprioritized item')).toBeInTheDocument()
    // Should not have a priority badge
    expect(screen.queryByLabelText(/Priority P/)).not.toBeInTheDocument()
  })

  it('renders object item with priority (bar + badge)', () => {
    const item: ThoughtItemType = { text: 'Important task', priority: { rank: 'P1' } }

    render(<ThoughtItem item={item} />)
    expect(screen.getByText('Important task')).toBeInTheDocument()
    expect(screen.getByLabelText('Priority P1')).toBeInTheDocument()
  })

  it('renders P2 priority badge correctly', () => {
    const item: ThoughtItemType = { text: 'Second priority', priority: { rank: 'P2' } }

    render(<ThoughtItem item={item} />)
    expect(screen.getByLabelText('Priority P2')).toBeInTheDocument()
  })

  it('renders P3 priority badge correctly', () => {
    const item: ThoughtItemType = { text: 'Third priority', priority: { rank: 'P3' } }

    render(<ThoughtItem item={item} />)
    expect(screen.getByLabelText('Priority P3')).toBeInTheDocument()
  })

  it('renders with small size', () => {
    const item: ThoughtItemType = { text: 'Small item' }

    render(<ThoughtItem item={item} size="small" />)
    expect(screen.getByText('Small item')).toBeInTheDocument()
  })

  it('renders with normal size by default', () => {
    const item: ThoughtItemType = { text: 'Normal item' }

    render(<ThoughtItem item={item} />)
    expect(screen.getByText('Normal item')).toBeInTheDocument()
  })

  it('handles item with undefined priority gracefully', () => {
    const item: ThoughtItemType = { text: 'No priority', priority: undefined }

    render(<ThoughtItem item={item} />)
    expect(screen.getByText('No priority')).toBeInTheDocument()
    expect(screen.queryByLabelText(/Priority P/)).not.toBeInTheDocument()
  })
})
