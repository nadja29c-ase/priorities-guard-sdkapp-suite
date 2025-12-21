interface ThoughtItemProps {
  text: string
  size?: 'normal' | 'small'
}

export function ThoughtItem({ text, size = 'normal' }: ThoughtItemProps) {
  const textClass = size === 'small' ? 'text-xs' : 'text-sm'

  return (
    <li className="flex items-start gap-2">
      <span className={`text-tertiary ${textClass} leading-relaxed shrink-0`}>•</span>
      <span className={`text-default ${textClass} leading-relaxed break-words`}>{text}</span>
    </li>
  )
}
