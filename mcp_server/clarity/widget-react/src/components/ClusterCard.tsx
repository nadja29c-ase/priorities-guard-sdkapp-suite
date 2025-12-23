import { Badge } from '@openai/apps-sdk-ui/components/Badge'
import type { Cluster } from '../types'
import { truncateText, sortSubclustersByPriority, normalizeThoughtItem, sortThoughtItemsByPriority } from '../utils'
import { PriorityBadge } from './PriorityBadge'
import { TagPill } from './TagPill'
import { ThoughtItem } from './ThoughtItem'
import { SubclusterCard } from './SubclusterCard'

interface ClusterCardProps {
  cluster: Cluster
}

export function ClusterCard({ cluster }: ClusterCardProps) {
  const headingId = `cluster-heading-${cluster.cluster_name.replace(/\s+/g, '-')}`
  const hasPriority = cluster.priority?.rank
  const rawItems = cluster.thought_items ?? []
  const subclusters = cluster.subclusters ?? []
  const tags = cluster.tags ?? []

  // Normalize and sort thought items by priority
  const normalizedItems = rawItems.map(normalizeThoughtItem)
  const sortedItems = sortThoughtItemsByPriority(normalizedItems)

  // Sort subclusters by priority
  const sortedSubclusters = sortSubclustersByPriority(subclusters)

  return (
    <article
      tabIndex={0}
      data-testid="cluster-card"
      aria-labelledby={headingId}
      className={`rounded-2xl border bg-surface-secondary transition-shadow duration-200 p-5 flex flex-col min-h-[120px] shadow-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-ring)] ${
        hasPriority ? 'border-l-4 border-l-strong pl-6' : 'border-default'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <h3 id={headingId} className="text-sm font-semibold text-default m-0">
            {truncateText(cluster.cluster_name, 40) || 'Untitled cluster'}
          </h3>
          {hasPriority && <PriorityBadge rank={hasPriority} />}
        </div>
        <span aria-label={`${cluster.sum_thought_items} items in this cluster`}>
          <Badge color="secondary" variant="outline" size="sm" aria-hidden="true">
            {cluster.sum_thought_items}
          </Badge>
          <span className="sr-only">{cluster.sum_thought_items} items</span>
        </span>
      </div>

      {/* Summary (if present) */}
      {cluster.summary && (
        <p className="text-sm text-secondary mb-3">
          {truncateText(cluster.summary, 100)}
        </p>
      )}

      {/* Direct thought items */}
      {sortedItems.length > 0 && (
        <ul role="list" className="space-y-2 list-none m-0 p-0">
          {sortedItems.map((item, i) => (
            <ThoughtItem key={`${cluster.cluster_name}-item-${i}-${item.text.slice(0,20)}`} item={item} />
          ))}
        </ul>
      )}

      {/* Subclusters */}
      {sortedSubclusters.length > 0 && (
        <div className="flex flex-col gap-3 mt-3">
          {sortedSubclusters.map((sub) => (
            <SubclusterCard key={sub.subcluster_name} subcluster={sub} />
          ))}
        </div>
      )}

      {/* Tags */}
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-auto pt-4">
          {tags.map((tag) => (
            <TagPill key={tag} tag={tag} />
          ))}
        </div>
      )}
    </article>
  )
}
