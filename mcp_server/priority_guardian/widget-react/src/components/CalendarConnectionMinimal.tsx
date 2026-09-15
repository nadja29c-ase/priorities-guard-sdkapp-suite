import { t } from '../i18n'

interface CalendarConnectionMinimalProps {
  connected: boolean
}

export function CalendarConnectionMinimal({ connected }: CalendarConnectionMinimalProps) {
  // V7: Only show when connected, minimal indicator
  if (!connected) {
    return null
  }

  return (
    <div className="mt-2 flex items-center gap-2 px-1">
      <span
        className="w-1.5 h-1.5 rounded-full bg-success-solid"
        aria-hidden="true"
      />
      <span className="text-xs text-tertiary">
        {t('calendarConnected')}
      </span>
    </div>
  )
}
