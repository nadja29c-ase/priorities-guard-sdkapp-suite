interface ThoughtItemProps {
  text: string
  size?: 'normal' | 'small'
}

export function ThoughtItem({ text, size = 'normal' }: ThoughtItemProps) {
  const textClass = size === 'small' ? 'text-xs' : 'text-sm'
  const paddingClass = size === 'small' ? 'pl-2 py-0.5' : 'pl-3 py-1'

  return (
    <div className={`border-l-2 border-default ${paddingClass}`}>
      <span className={`${textClass} text-default`}>{text}</span>
    </div>
  )
}
