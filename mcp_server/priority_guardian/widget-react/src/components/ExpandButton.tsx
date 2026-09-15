import { t } from '../i18n'

interface ExpandButtonProps {
  onClick: () => void
}

export function ExpandButton({ onClick }: ExpandButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full mt-2 py-2.5 rounded-xl text-xs font-medium flex items-center justify-center gap-1.5 transition-colors hover:opacity-80 text-inverse bg-primary-solid"
      aria-label={t('openFullDashboard')}
    >
      {t('openFullDashboard')}
      <svg
        className="w-3 h-3"
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
