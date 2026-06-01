import { useState } from 'react'
import { t } from '../i18n'

interface ExpandButtonProps {
  onClick: () => void
}

export function ExpandButton({ onClick }: ExpandButtonProps) {
  const [isHovered, setIsHovered] = useState(false)

  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        width: '100%',
        marginTop: '8px',
        padding: '10px 0',
        borderRadius: '8px',
        fontSize: '12px',
        fontWeight: 500,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '6px',
        transition: 'opacity 0.15s',
        opacity: isHovered ? 0.8 : 1,
        color: 'var(--color-text-inverse, #fff)',
        background: 'var(--color-background-inverse, #1f1e1d)',
        border: 'none',
        cursor: 'pointer',
      }}
      aria-label={t('openFullDashboard')}
    >
      {t('openFullDashboard')}
      <svg
        style={{ width: '12px', height: '12px' }}
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        aria-hidden="true"
      >
        <path d="M6 4l4 4-4 4" />
      </svg>
    </button>
  )
}
