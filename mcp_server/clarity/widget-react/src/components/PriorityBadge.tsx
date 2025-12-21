import { Badge } from '@openai/apps-sdk-ui/components/Badge'

interface PriorityBadgeProps {
  rank: 'P1' | 'P2' | 'P3'
  size?: 'sm' | 'md'
}

export function PriorityBadge({ rank, size = 'sm' }: PriorityBadgeProps) {
  return (
    <Badge color="secondary" variant="solid" size={size} aria-label={`Priority ${rank}`}>
      {rank}
    </Badge>
  )
}
