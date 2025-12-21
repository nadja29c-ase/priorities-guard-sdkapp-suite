import { Badge } from '@openai/apps-sdk-ui/components/Badge'
import type { Cluster } from '../types'
import { truncateText, sortSubclustersByPriority } from '../utils'
import { PriorityBadge } from './PriorityBadge'
import { TagPill } from './TagPill'
import { ThoughtItem } from './ThoughtItem'
import { SubclusterCard } from './SubclusterCard'

interface ClusterCardProps {
  cluster: Cluster
}

export function ClusterCard({ cluster }: ClusterCardProps) {
  const hasPriority = cluster.priority?.rank
  const items = cluster.thought_items ?? []
  const subclusters = cluster.subclusters ?? []
  const tags = cluster.tags ?? []

  // Sort subclusters by priority
  const sortedSubclusters = sortSubclustersByPriority(subclusters)

  return (
    <div
      className={`rounded-2xl border bg-surface-secondary transition-shadow duration-200 p-5 flex flex-col min-h-[120px] shadow-lg ${
        hasPriority ? 'border-l-4 border-l-[var(--green-400)] pl-6' : 'border-default'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-default">
            {truncateText(cluster.cluster_name, 40) || 'Untitled cluster'}
          </span>
          {hasPriority && <PriorityBadge rank={hasPriority} />}
        </div>
        <Badge color="secondary" variant="outline" size="sm">
          {cluster.sum_thought_items}
        </Badge>
      </div>

      {/* Summary (if present) */}
      {cluster.summary && (
        <p className="text-sm text-secondary mb-3">
          {truncateText(cluster.summary, 100)}
        </p>
      )}

      {/* Direct thought items */}
      {items.length > 0 && (
        <div className="space-y-2">
          {items.map((item, i) => (
            <ThoughtItem key={i} text={item} />
          ))}
        </div>
      )}

      {/* Subclusters */}
      {sortedSubclusters.length > 0 && (
        <div className="flex flex-col gap-3 mt-3">
          {sortedSubclusters.map((sub, i) => (
            <SubclusterCard key={i} subcluster={sub} />
          ))}
        </div>
      )}

      {/* Tags */}
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-auto pt-4">
          {tags.map((tag, i) => (
            <TagPill key={i} tag={tag} />
          ))}
        </div>
      )}
    </div>
  )
}
