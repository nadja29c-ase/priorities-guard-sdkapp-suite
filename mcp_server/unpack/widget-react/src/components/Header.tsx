interface HeaderProps {
  problemStatement: string
}

export function Header({ problemStatement }: HeaderProps) {
  return (
    <div className="mb-6">
      <p className="heading-sm text-default mb-2">Your Unpack Summary</p>
      <div className="p-4 bg-surface rounded-xl border border-default">
        <p className="text-sm text-secondary mb-1">Problem</p>
        <p className="text-sm text-default">{problemStatement}</p>
      </div>
    </div>
  )
}
