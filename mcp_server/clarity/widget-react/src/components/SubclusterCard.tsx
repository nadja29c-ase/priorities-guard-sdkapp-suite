import { useState, useEffect, useRef } from 'react'
import { Badge } from '@openai/apps-sdk-ui/components/Badge'
import type { Subcluster } from '../types'
import { normalizeThoughtItem, sortThoughtItemsByPriority } from '../utils'
import { PriorityBadge } from './PriorityBadge'
import { TagPill } from './TagPill'
import { ThoughtItem } from './ThoughtItem'

interface SubclusterCardProps {
  subcluster: Subcluster
  defaultCollapsed?: boolean
  isCollapsible?: boolean
  onToggle?: () => void
}

export function SubclusterCard({ subcluster, defaultCollapsed, isCollapsible, onToggle }: SubclusterCardProps) {
  const idRef = useRef(`subcluster-${Math.random().toString(36).slice(2)}`)
  const headingId = idRef.current
  const contentId = `${headingId}-content`

  const [isExpanded, setIsExpanded] = useState(!defaultCollapsed)

  const prevDefaultCollapsedRef = useRef(defaultCollapsed)
  useEffect(() => {
    if (prevDefaultCollapsedRef.current !== defaultCollapsed) {
      setIsExpanded(!defaultCollapsed)
      prevDefaultCollapsedRef.current = defaultCollapsed
    }
  }, [defaultCollapsed])
  const hasPriority = subcluster.priority?.rank
  const rawItems = subcluster.thought_items ?? []
  const tags = subcluster.tags ?? []

  // Normalize and sort thought items by priority
  const normalizedItems = rawItems.map(normalizeThoughtItem)
  const sortedItems = sortThoughtItemsByPriority(normalizedItems)

  return (
    <div
      className={`rounded-lg border bg-surface p-3 flex flex-col ${
        hasPriority ? 'border-l-4 border-l-strong' : 'border-subtle'
      }`}
    >
      {/* Header */}
      {(() => {
        const headerContent = (
          <>
            <div className="flex items-center gap-2">
              <h4 id={headingId} className="text-sm font-medium text-default m-0">
                {subcluster.subcluster_name || 'Untitled'}
              </h4>
              {hasPriority && <PriorityBadge rank={hasPriority} size="sm" />}
            </div>
            <div className="flex items-center gap-2">
              <span role="text" aria-label={`${subcluster.sum_thought_items || rawItems.length} items in this subcluster`}>
                <Badge color="secondary" variant="outline" size="sm" aria-hidden="true">
                  {subcluster.sum_thought_items || rawItems.length}
                </Badge>
                <span className="sr-only">{subcluster.sum_thought_items || rawItems.length} items</span>
              </span>
              {isCollapsible && (
                <span className="text-xs text-secondary ml-1" aria-hidden="true">{isExpanded ? '▲' : '▼'}</span>
              )}
            </div>
          </>
        )

        return isCollapsible ? (
          <button
            onClick={() => {
              setIsExpanded(e => !e)
              onToggle?.()
            }}
            className="flex items-start justify-between gap-2 mb-2 w-full text-left bg-transparent border-none p-0 cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-ring)]"
            aria-label={`${isExpanded ? 'Collapse' : 'Expand'} subcluster: ${subcluster.subcluster_name}`}
            aria-expanded={isExpanded}
            aria-controls={contentId}
          >
            {headerContent}
          </button>
        ) : (
          <div className="flex items-start justify-between gap-2 mb-2">
            {headerContent}
          </div>
        )
      })()}

      <div id={contentId} role="region" aria-labelledby={headingId}>
        {/* Thought items:
            - Expanded: all items
            - Collapsed: only items with a priority rank assigned */}
        {sortedItems.length > 0 && (
          <ul role="list" className="space-y-1 list-none m-0 p-0">
            {(isExpanded ? sortedItems : sortedItems.filter(item => item.priority?.rank)).map((item, i) => (
              <ThoughtItem key={`${subcluster.subcluster_name}-item-${i}-${item.text.slice(0,20)}`} item={item} size="small" />
            ))}
          </ul>
        )}

        {/* Tags — only when expanded */}
        {isExpanded && tags.length > 0 && (
          <div role="list" aria-label="Suggested actions" className="flex flex-wrap gap-1.5 mt-auto pt-2">
            {tags.map((tag) => (
              <TagPill key={tag} tag={tag} size="sm" />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
