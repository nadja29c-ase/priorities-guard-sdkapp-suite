import { useState } from 'react'
import { t } from '../i18n'

interface FullscreenHeaderProps {
  onMinimize: () => void
}

export function FullscreenHeader({ onMinimize }: FullscreenHeaderProps) {
  const [isHovered, setIsHovered] = useState(false)

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 16px',
        marginBottom: '16px',
        borderRadius: '12px',
        background: 'var(--color-background-primary, #fff)',
        border: '1px solid var(--color-border, #e5e5e5)',
      }}
    >
      <span
        style={{
          fontSize: '14px',
          fontWeight: 600,
          color: 'var(--color-text-primary, #0d0d0d)',
        }}
      >
        {t('myPriorities')}
      </span>
      <button
        type="button"
        onClick={onMinimize}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        style={{
          fontSize: '12px',
          padding: '4px 10px',
          borderRadius: '8px',
          transition: 'background 0.15s',
          background: isHovered ? 'var(--color-background-secondary, rgba(0,0,0,0.05))' : 'transparent',
          color: 'var(--color-text-secondary, #737373)',
          border: 'none',
          cursor: 'pointer',
        }}
        title={t('minimizeToInline')}
        aria-label={t('minimizeDashboard')}
      >
        {t('minimize')}
      </button>
    </div>
  )
}
