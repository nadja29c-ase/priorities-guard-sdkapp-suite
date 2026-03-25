import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ClusterCard } from '../components/ClusterCard'
import type { Cluster } from '../types'

describe('Accessibility', () => {
  describe('ClusterCard semantics', () => {
    it('renders cluster title as h3', () => {
      const cluster: Cluster = {
        cluster_name: 'Work Tasks',
        sum_thought_items: 2,
      }

      render(<ClusterCard cluster={cluster} />)
      const heading = screen.getByRole('heading', { level: 3 })
      expect(heading).toHaveTextContent('Work Tasks')
    })

    it('has data-testid="cluster-card"', () => {
      const cluster: Cluster = {
        cluster_name: 'Test',
        sum_thought_items: 1,
      }

      render(<ClusterCard cluster={cluster} />)
      expect(screen.getByTestId('cluster-card')).toBeInTheDocument()
    })

    it('has tabIndex={0} for keyboard navigation', () => {
      const cluster: Cluster = {
        cluster_name: 'Test',
        sum_thought_items: 1,
      }

      render(<ClusterCard cluster={cluster} />)
      const card = screen.getByTestId('cluster-card')
      expect(card).toHaveAttribute('tabIndex', '0')
    })

    it('renders thought items in a list', () => {
      const cluster: Cluster = {
        cluster_name: 'Tasks',
        sum_thought_items: 2,
        thought_items: ['Task one', 'Task two'],
      }

      render(<ClusterCard cluster={cluster} />)
      const list = screen.getByRole('list')
      const items = screen.getAllByRole('listitem')
      expect(list).toBeInTheDocument()
      expect(items).toHaveLength(2)
    })
  })

  describe('Tab navigation', () => {
    it('tab stops equal cluster count only', async () => {
      const clusters: Cluster[] = [
        { cluster_name: 'Cluster 1', sum_thought_items: 2 },
        { cluster_name: 'Cluster 2', sum_thought_items: 1 },
        { cluster_name: 'Cluster 3', sum_thought_items: 3 },
      ]

      render(
        <div>
          {clusters.map((c) => (
            <ClusterCard key={c.cluster_name} cluster={c} />
          ))}
        </div>
      )

      const user = userEvent.setup()
      const clusterCards = screen.getAllByTestId('cluster-card')
      expect(clusterCards).toHaveLength(3)

      await user.tab()
      expect(clusterCards[0]).toHaveFocus()

      await user.tab()
      expect(clusterCards[1]).toHaveFocus()

      await user.tab()
      expect(clusterCards[2]).toHaveFocus()

      await user.tab()
      // Focus should have left the clusters (moved to body or beyond)
      expect(clusterCards.some((c) => c === document.activeElement)).toBe(false)
    })
  })

})
