import { Badge } from '@openai/apps-sdk-ui/components/Badge'

interface TagPillProps {
  tag: string
  size?: 'sm' | 'md'
}

export function TagPill({ tag, size = 'sm' }: TagPillProps) {
  return (
    <span role="listitem" aria-label={`Tag: ${tag}`}>
      <Badge color="secondary" variant="soft" size={size} aria-hidden="true">
        {tag.toLowerCase()}
      </Badge>
    </span>
  )
}
