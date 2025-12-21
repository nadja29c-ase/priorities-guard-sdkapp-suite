import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ClusterCard } from '../components/ClusterCard'
import type { Cluster } from '../types'

describe('ClusterCard', () => {
  it('renders cluster name', () => {
    const cluster: Cluster = {
      cluster_name: 'Work Tasks',
      sum_thought_items: 3,
    }

    render(<ClusterCard cluster={cluster} />)
    expect(screen.getByText('Work Tasks')).toBeInTheDocument()
  })

  it('shows item count badge', () => {
    const cluster: Cluster = {
      cluster_name: 'Test',
      sum_thought_items: 5,
    }

    render(<ClusterCard cluster={cluster} />)
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('displays priority badge when present', () => {
    const cluster: Cluster = {
      cluster_name: 'Priority Task',
      sum_thought_items: 2,
      priority: { rank: 'P1' },
    }

    render(<ClusterCard cluster={cluster} />)
    expect(screen.getByText('P1')).toBeInTheDocument()
  })

  it('renders thought items list', () => {
    const cluster: Cluster = {
      cluster_name: 'Tasks',
      sum_thought_items: 2,
      thought_items: ['First task', 'Second task'],
    }

    render(<ClusterCard cluster={cluster} />)
    expect(screen.getByText('First task')).toBeInTheDocument()
    expect(screen.getByText('Second task')).toBeInTheDocument()
  })

  it('handles undefined thought_items gracefully', () => {
    const cluster: Cluster = {
      cluster_name: 'Empty',
      sum_thought_items: 0,
      thought_items: undefined,
    }

    render(<ClusterCard cluster={cluster} />)
    expect(screen.getByText('Empty')).toBeInTheDocument()
  })

  it('renders subclusters when present', () => {
    const cluster: Cluster = {
      cluster_name: 'Parent',
      sum_thought_items: 3,
      subclusters: [
        {
          subcluster_name: 'Child Cluster',
          sum_thought_items: 2,
          thought_items: ['Sub item 1'],
        },
      ],
    }

    render(<ClusterCard cluster={cluster} />)
    expect(screen.getByText('Child Cluster')).toBeInTheDocument()
    expect(screen.getByText('Sub item 1')).toBeInTheDocument()
  })

  it('handles undefined subclusters gracefully', () => {
    const cluster: Cluster = {
      cluster_name: 'No Subclusters',
      sum_thought_items: 1,
      subclusters: undefined,
    }

    render(<ClusterCard cluster={cluster} />)
    expect(screen.getByText('No Subclusters')).toBeInTheDocument()
  })

  it('shows tags when present', () => {
    const cluster: Cluster = {
      cluster_name: 'Tagged',
      sum_thought_items: 1,
      tags: ['decide', 'urgent'],
    }

    render(<ClusterCard cluster={cluster} />)
    expect(screen.getByText('decide')).toBeInTheDocument()
    expect(screen.getByText('urgent')).toBeInTheDocument()
  })

  it('handles undefined tags gracefully', () => {
    const cluster: Cluster = {
      cluster_name: 'No Tags',
      sum_thought_items: 1,
      tags: undefined,
    }

    render(<ClusterCard cluster={cluster} />)
    expect(screen.getByText('No Tags')).toBeInTheDocument()
  })
})
