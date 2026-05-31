import { t } from '../i18n'

interface CalendarConnectionMinimalProps {
  connected: boolean
}

export function CalendarConnectionMinimal({ connected }: CalendarConnectionMinimalProps) {
  // Only show when connected, minimal indicator
  if (!connected) {
    return null
  }

  return (
    <div
      style={{
        marginTop: '8px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        paddingLeft: '4px',
        paddingRight: '4px',
      }}
    >
      <span
        style={{
          width: '6px',
          height: '6px',
          borderRadius: '9999px',
          background: 'var(--color-background-success-solid, #16a34a)',
        }}
        aria-hidden="true"
      />
      <span
        style={{
          fontSize: '12px',
          color: 'var(--color-text-tertiary, #73726C)',
        }}
      >
        {t('calendarConnected')}
      </span>
    </div>
  )
}
