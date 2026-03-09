import { useState } from 'react'
import type { Priority, CalendarKeyword } from '../types'
import { BADGE_COLORS, BADGE_CIRCLE_CLASS } from '../constants'
import { t } from '../i18n'

interface KeywordPickerProps {
  currentKeyword: CalendarKeyword
  priorities: Priority[]  // All priorities to detect which holds each keyword
  onKeywordChange: (keyword: CalendarKeyword) => Promise<void>
  disabled?: boolean
}

const ALL_KEYWORDS: CalendarKeyword[] = ['P1', 'P2', 'P3']

/**
 * Inline keyword picker for edit mode.
 * Shows all 3 keywords, current is selected, others are tappable.
 * If another priority holds a keyword, shows "Will swap with [name]" hint.
 */
export function KeywordPicker({
  currentKeyword,
  priorities,
  onKeywordChange,
  disabled = false,
}: KeywordPickerProps) {
  // Prevent concurrent swaps from rapid taps
  const [loadingKeyword, setLoadingKeyword] = useState<CalendarKeyword | null>(null)

  // Build map of keyword -> priority name (only active priorities)
  const keywordHolders = new Map<string, string>()
  for (const p of priorities) {
    if (p.status === 'active' && p.calendarKeyword) {
      keywordHolders.set(p.calendarKeyword, p.name)
    }
  }

  const handleClick = async (kw: CalendarKeyword) => {
    if (disabled || loadingKeyword !== null || kw === currentKeyword) return
    setLoadingKeyword(kw)
    try {
      await onKeywordChange(kw)
    } finally {
      setLoadingKeyword(null)
    }
  }

  const isLoading = loadingKeyword !== null

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-secondary">{t('badgeLabel')}</span>
      <div className="flex gap-1.5">
        {ALL_KEYWORDS.map((kw) => {
          const isSelected = kw === currentKeyword
          const holderName = keywordHolders.get(kw)
          const isHeldByOther = holderName && !isSelected
          const badgeColor = BADGE_COLORS[kw] ?? BADGE_COLORS.P1

          const isDisabled = disabled || isLoading

          return (
            <div key={kw} className="relative group">
              <button
                type="button"
                onClick={() => handleClick(kw)}
                disabled={isDisabled}
                aria-pressed={isSelected}
                className={`
                  ${BADGE_CIRCLE_CLASS} ${badgeColor} text-2xs
                  transition-all cursor-pointer
                  ${isSelected
                    ? 'ring-2 ring-offset-1 ring-offset-surface'
                    : 'opacity-60 hover:opacity-100'
                  }
                  ${isDisabled ? 'cursor-not-allowed' : ''}
                `}
                aria-label={`${isSelected ? t('currentKeyword') : t('switchTo')} ${kw}${isHeldByOther ? ` (${t('willSwapWith').replace('{name}', holderName!)})` : ''}`}
              >
                {kw}
              </button>
              {/* Tooltip on hover for swap hint */}
              {isHeldByOther && (
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 text-xs bg-surface-tertiary text-secondary rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                  {t('swapWith').replace('{name}', holderName)}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
