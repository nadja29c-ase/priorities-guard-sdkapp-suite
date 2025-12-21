import { Badge } from '@openai/apps-sdk-ui/components/Badge'
import type { Subcluster } from '../types'
import { truncateText } from '../utils'
import { PriorityBadge } from './PriorityBadge'
import { TagPill } from './TagPill'
import { ThoughtItem } from './ThoughtItem'

interface SubclusterCardProps {
  subcluster: Subcluster
}

export function SubclusterCard({ subcluster }: SubclusterCardProps) {
  const hasPriority = subcluster.priority?.rank
  const items = subcluster.thought_items ?? []
  const tags = subcluster.tags ?? []

  return (
    <div
      className={`rounded-lg border bg-surface p-3 flex flex-col ${
        hasPriority ? 'border-2 border-success-outline' : 'border-subtle'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-default">
            {truncateText(subcluster.subcluster_name, 30) || 'Untitled'}
          </span>
          {hasPriority && <PriorityBadge rank={hasPriority} size="sm" />}
        </div>
        <Badge color="secondary" variant="outline" size="sm">
          {subcluster.sum_thought_items || items.length}
        </Badge>
      </div>

      {/* Items */}
      {items.length > 0 && (
        <ul className="list-none m-0 p-0 space-y-1">
          {items.map((item, i) => (
            <ThoughtItem key={i} text={item} size="small" />
          ))}
        </ul>
      )}

      {/* Tags */}
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-auto pt-2">
          {tags.map((tag, i) => (
            <TagPill key={i} tag={tag} size="sm" />
          ))}
        </div>
      )}
    </div>
  )
}
