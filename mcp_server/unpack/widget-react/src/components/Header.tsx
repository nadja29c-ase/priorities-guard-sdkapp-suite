interface HeaderProps {
  problemStatement: string
}

export function Header({ problemStatement }: HeaderProps) {
  return (
    <div className="mb-6">
      <h1 className="heading-sm text-default mb-2">Your Question-First Brainstorming</h1>
      <section
        tabIndex={0}
        aria-labelledby="problem-label"
        className="p-4 bg-surface rounded-xl border border-default focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-ring)]"
      >
        <h3 id="problem-label" className="text-sm text-secondary mb-1">Problem</h3>
        <p aria-label={problemStatement} className="text-sm text-default">{problemStatement}</p>
      </section>
    </div>
  )
}
