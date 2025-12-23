import type { ThoughtItem as ThoughtItemType } from '../types'
import { PriorityBadge } from './PriorityBadge'

interface ThoughtItemProps {
  item: ThoughtItemType
  size?: 'normal' | 'small'
}

export function ThoughtItem({ item, size = 'normal' }: ThoughtItemProps) {
  const hasPriority = item.priority?.rank
  const textClass = size === 'small' ? 'text-xs' : 'text-sm'
  const paddingClass = size === 'small' ? 'pl-2 py-0.5' : 'pl-3 py-1'

  // Priority bar: border-l-4 border-l-strong when prioritized, border-l-2 border-default otherwise
  const borderClass = hasPriority ? 'border-l-4 border-l-strong' : 'border-l-2 border-default'

  return (
    <li aria-label={item.text} className={`${borderClass} ${paddingClass} flex items-center gap-2`}>
      <span className={`${textClass} text-default`}>{item.text}</span>
      {hasPriority && <PriorityBadge rank={hasPriority} size="sm" />}
    </li>
  )
}
