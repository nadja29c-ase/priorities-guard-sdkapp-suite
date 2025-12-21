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
      className={`rounded-2xl border bg-surface transition-shadow duration-200 p-4 flex flex-col min-h-[120px] ${
        hasPriority ? 'border-2 border-success-outline' : 'border-default'
      }`}
      style={{
        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15), 0 2px 4px rgba(0, 0, 0, 0.1)',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-2">
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
        <p className="text-sm text-secondary mb-2.5">
          {truncateText(cluster.summary, 100)}
        </p>
      )}

      {/* Direct thought items */}
      {items.length > 0 && (
        <ul className="list-none m-0 p-0 space-y-1.5 flex-grow">
          {items.map((item, i) => (
            <ThoughtItem key={i} text={item} />
          ))}
        </ul>
      )}

      {/* Subclusters */}
      {sortedSubclusters.length > 0 && (
        <div className="flex flex-col gap-2.5 mt-2">
          {sortedSubclusters.map((sub, i) => (
            <SubclusterCard key={i} subcluster={sub} />
          ))}
        </div>
      )}

      {/* Tags */}
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2.5">
          {tags.map((tag, i) => (
            <TagPill key={i} tag={tag} />
          ))}
        </div>
      )}
    </div>
  )
}
