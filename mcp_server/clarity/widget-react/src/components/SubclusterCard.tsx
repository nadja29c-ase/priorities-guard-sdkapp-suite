import { Badge } from '@openai/apps-sdk-ui/components/Badge'
import type { Subcluster } from '../types'
import { truncateText, normalizeThoughtItem, sortThoughtItemsByPriority } from '../utils'
import { PriorityBadge } from './PriorityBadge'
import { TagPill } from './TagPill'
import { ThoughtItem } from './ThoughtItem'

interface SubclusterCardProps {
  subcluster: Subcluster
}

export function SubclusterCard({ subcluster }: SubclusterCardProps) {
  const headingId = `subcluster-heading-${subcluster.subcluster_name.replace(/\s+/g, '-')}`
  const hasPriority = subcluster.priority?.rank
  const rawItems = subcluster.thought_items ?? []
  const tags = subcluster.tags ?? []

  // Normalize and sort thought items by priority
  const normalizedItems = rawItems.map(normalizeThoughtItem)
  const sortedItems = sortThoughtItemsByPriority(normalizedItems)

  return (
    <section
      aria-labelledby={headingId}
      className={`rounded-lg border bg-surface p-3 flex flex-col ${
        hasPriority ? 'border-l-4 border-l-strong' : 'border-subtle'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <h4 id={headingId} className="text-sm font-medium text-default m-0">
            {truncateText(subcluster.subcluster_name, 30) || 'Untitled'}
          </h4>
          {hasPriority && <PriorityBadge rank={hasPriority} size="sm" />}
        </div>
        <span aria-label={`${subcluster.sum_thought_items || rawItems.length} items in this subcluster`}>
          <Badge color="secondary" variant="outline" size="sm" aria-hidden="true">
            {subcluster.sum_thought_items || rawItems.length}
          </Badge>
          <span className="sr-only">{subcluster.sum_thought_items || rawItems.length} items</span>
        </span>
      </div>

      {/* Items */}
      {sortedItems.length > 0 && (
        <ul role="list" className="space-y-1 list-none m-0 p-0">
          {sortedItems.map((item, i) => (
            <ThoughtItem key={`${subcluster.subcluster_name}-item-${i}-${item.text.slice(0,20)}`} item={item} size="small" />
          ))}
        </ul>
      )}

      {/* Tags */}
      {tags.length > 0 && (
        <div role="list" aria-label="Suggested actions" className="flex flex-wrap gap-1.5 mt-auto pt-2">
          {tags.map((tag) => (
            <TagPill key={tag} tag={tag} size="sm" />
          ))}
        </div>
      )}
    </section>
  )
}
