import { Badge } from '@openai/apps-sdk-ui/components/Badge'

interface TagPillProps {
  tag: string
  size?: 'sm' | 'md'
}

export function TagPill({ tag, size = 'sm' }: TagPillProps) {
  return (
    <Badge color="secondary" variant="soft" size={size}>
      {tag.toLowerCase()}
    </Badge>
  )
}
