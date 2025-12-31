interface HeaderProps {
  problemStatement: string
}

export function Header({ problemStatement }: HeaderProps) {
  return (
    <div className="mb-6">
      <h1 className="heading-sm text-default mb-2">Your Question-First Brainstorming</h1>
      <section aria-labelledby="problem-label" className="p-4 bg-surface rounded-xl border border-default">
        <h3 id="problem-label" className="text-sm text-secondary mb-1">Problem</h3>
        <p aria-label={problemStatement} className="text-sm text-default">{problemStatement}</p>
      </section>
    </div>
  )
}
