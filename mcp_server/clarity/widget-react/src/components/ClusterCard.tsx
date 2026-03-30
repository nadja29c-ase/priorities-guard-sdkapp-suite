import { useState, useEffect, useRef } from 'react'
import { Badge } from '@openai/apps-sdk-ui/components/Badge'
import type { Cluster } from '../types'
import { truncateText, sortSubclustersByPriority, normalizeThoughtItem, sortThoughtItemsByPriority } from '../utils'
import { PriorityBadge } from './PriorityBadge'
import { TagPill } from './TagPill'
import { ThoughtItem } from './ThoughtItem'
import { SubclusterCard } from './SubclusterCard'

interface ClusterCardProps {
  cluster: Cluster
  defaultCollapsed?: boolean
  isCollapsible?: boolean
  onToggle?: () => void
}

export function ClusterCard({ cluster, defaultCollapsed, isCollapsible, onToggle }: ClusterCardProps) {
  const idRef = useRef(`cluster-${Math.random().toString(36).slice(2)}`)
  const headingId = idRef.current
  const contentId = `${headingId}-content`

  const [isExpanded, setIsExpanded] = useState(!defaultCollapsed)

  // Only reset isExpanded when defaultCollapsed actually transitions between values.
  // A plain useEffect without this guard would reset user-expanded clusters on every
  // toolOutput update that doesn't change the collapsed mode.
  const prevDefaultCollapsedRef = useRef(defaultCollapsed)
  useEffect(() => {
    if (prevDefaultCollapsedRef.current !== defaultCollapsed) {
      setIsExpanded(!defaultCollapsed)
      prevDefaultCollapsedRef.current = defaultCollapsed
    }
  }, [defaultCollapsed])
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
      aria-label={`Cluster: ${cluster.cluster_name}${hasPriority ? `, Priority ${hasPriority.replace('P', '')}` : ''}, ${cluster.sum_thought_items} items`}
      className={`rounded-2xl border bg-surface-secondary transition-shadow duration-200 p-5 flex flex-col min-h-[120px] shadow-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-ring)] ${
        hasPriority ? 'border-l-4 border-l-strong pl-6' : 'border-default'
      }`}
    >
      {/* Header */}
      {(() => {
        const headerContent = (
          <>
            <div className="flex items-center gap-2 min-w-0">
              <h3 id={headingId} aria-label={`Cluster: ${cluster.cluster_name}`} className="text-sm font-semibold text-default m-0">
                {cluster.cluster_name || 'Untitled cluster'}
              </h3>
              {hasPriority && <PriorityBadge rank={hasPriority} />}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span role="text" aria-label={`${cluster.sum_thought_items} items in this cluster`}>
                <Badge color="secondary" variant="outline" size="sm" aria-hidden="true">
                  {cluster.sum_thought_items}
                </Badge>
                <span className="sr-only">{cluster.sum_thought_items} items</span>
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
            className="flex items-start justify-between gap-2 mb-3 w-full text-left bg-transparent border-none p-0 cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-ring)]"
            aria-label={`${isExpanded ? 'Collapse' : 'Expand'} cluster: ${cluster.cluster_name}`}
            aria-expanded={isExpanded}
            aria-controls={contentId}
          >
            {headerContent}
          </button>
        ) : (
          <div className="flex items-start justify-between gap-2 mb-3">
            {headerContent}
          </div>
        )
      })()}

      <div id={contentId} role="region" aria-labelledby={headingId}>
        {/* Summary — hidden when collapsed */}
        {isExpanded && cluster.summary && (
          <p className="text-sm text-secondary mb-3">
            {truncateText(cluster.summary, 100)}
          </p>
        )}

        {/* Direct thought items:
            - Expanded: all items
            - Collapsed: only items with a priority rank assigned */}
        {sortedItems.length > 0 && (
          <ul role="list" className="space-y-2 list-none m-0 p-0">
            {(isExpanded ? sortedItems : sortedItems.filter(item => item.priority?.rank)).map((item, i) => (
              <ThoughtItem key={`${cluster.cluster_name}-item-${i}-${item.text.slice(0,20)}`} item={item} />
            ))}
          </ul>
        )}

        {/* Subclusters:
            - When parent is collapsed: pass defaultCollapsed=true so subclusters also start collapsed
            - When parent is expanded: pass defaultCollapsed={defaultCollapsed} so subclusters start
              collapsed individually (two-level progressive disclosure on mobile) */}
        {sortedSubclusters.length > 0 && (
          <div className="flex flex-col gap-3 mt-3">
            {sortedSubclusters.map((sub) => (
              <SubclusterCard
                key={sub.subcluster_name}
                subcluster={sub}
                defaultCollapsed={!isExpanded ? true : defaultCollapsed}
                isCollapsible={isCollapsible}
                onToggle={onToggle}
              />
            ))}
          </div>
        )}

        {/* Tags — only when expanded */}
        {isExpanded && tags.length > 0 && (
          <div role="list" aria-label="Suggested actions" className="flex flex-wrap gap-2 mt-auto pt-4">
            {tags.map((tag) => (
              <TagPill key={tag} tag={tag} />
            ))}
          </div>
        )}
      </div>
    </article>
  )
}
