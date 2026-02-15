interface CalendarConnectionMinimalProps {
  connected: boolean
}

export function CalendarConnectionMinimal({ connected }: CalendarConnectionMinimalProps) {
  return (
    <div className="flex items-center gap-1.5 text-xs text-secondary">
      <span
        className={`w-2 h-2 rounded-full ${connected ? 'bg-success' : 'bg-warning'}`}
        aria-hidden="true"
      />
      <span>
        {connected ? 'Calendar connected' : 'Calendar not connected'}
      </span>
    </div>
  )
}
