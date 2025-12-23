import { Badge } from '@openai/apps-sdk-ui/components/Badge'

interface PriorityBadgeProps {
  rank: 'P1' | 'P2' | 'P3'
  size?: 'sm' | 'md'
}

export function PriorityBadge({ rank, size = 'sm' }: PriorityBadgeProps) {
  const priorityNumber = rank.replace('P', '')

  return (
    <span aria-label={`Priority ${priorityNumber}`}>
      <Badge color="secondary" variant="solid" size={size} aria-hidden="true">
        {rank}
      </Badge>
    </span>
  )
}
