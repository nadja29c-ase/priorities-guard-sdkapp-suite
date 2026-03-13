import { useState, useEffect, useRef } from 'react'
import { Button } from '@openai/apps-sdk-ui/components/Button'
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
  // Pending keyword for confirmation dialog
  const [pendingKeyword, setPendingKeyword] = useState<CalendarKeyword | null>(null)

  const modalRef = useRef<HTMLDivElement>(null)

  // Build map of keyword -> priority name (only active priorities)
  const keywordHolders = new Map<string, string>()
  for (const p of priorities) {
    if (p.status === 'active' && p.calendarKeyword) {
      keywordHolders.set(p.calendarKeyword, p.name)
    }
  }

  const handleClick = (kw: CalendarKeyword) => {
    // Guard: if same as current, do nothing
    if (kw === currentKeyword) return
    if (disabled || loadingKeyword !== null) return
    // Set pending keyword and show dialog
    setPendingKeyword(kw)
  }

  const handleConfirm = async () => {
    if (!pendingKeyword) return
    const kwToChange = pendingKeyword
    // Dismiss dialog immediately
    setPendingKeyword(null)
    // Then trigger the change
    setLoadingKeyword(kwToChange)
    try {
      await onKeywordChange(kwToChange)
    } finally {
      setLoadingKeyword(null)
    }
  }

  const handleCancel = () => {
    setPendingKeyword(null)
  }

  // Auto-focus "Keep current badge" button on open (safe default)
  useEffect(() => {
    if (pendingKeyword === null) return
    const cancelButton = modalRef.current?.querySelector<HTMLButtonElement>('[data-color="secondary"]')
    cancelButton?.focus()
  }, [pendingKeyword])

  // ESC key closes modal
  useEffect(() => {
    if (pendingKeyword === null) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && loadingKeyword === null) {
        setPendingKeyword(null)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [pendingKeyword, loadingKeyword])

  // Focus trap — Tab/Shift+Tab stay within modal
  useEffect(() => {
    if (pendingKeyword === null) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return
      if (!modalRef.current) return
      if (!modalRef.current.contains(document.activeElement)) return

      // Query all focusable elements
      const focusableSelector = 'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      const allFocusable = modalRef.current.querySelectorAll<HTMLElement>(focusableSelector)

      // Filter to visible elements only
      const focusable = Array.from(allFocusable).filter(el => el.offsetParent !== null)
      if (focusable.length === 0) return

      const first = focusable[0]
      const last = focusable[focusable.length - 1]

      if (e.shiftKey && document.activeElement === first) {
        // Shift+Tab on first → wrap to last
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        // Tab on last → wrap to first
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [pendingKeyword])

  // Handle backdrop click
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget && loadingKeyword === null) {
      handleCancel()
    }
  }

  const isLoading = loadingKeyword !== null

  return (
    <>
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

      {/* Keyword Change Confirmation Dialog */}
      {pendingKeyword !== null && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={handleBackdropClick}
          role="dialog"
          aria-modal="true"
          aria-labelledby="keyword-change-dialog-title"
        >
          <div ref={modalRef} className="bg-surface rounded-2xl shadow-xl p-6 max-w-sm w-full mx-4">
            <h2 id="keyword-change-dialog-title" className="text-lg font-semibold text-default mb-3">
              {t('keywordChangeTitle')}
            </h2>

            {/* Body paragraph */}
            <p className="text-sm text-secondary mb-3">
              {t('keywordChangeBody')
                .replace(/{oldKeyword}/g, currentKeyword)}
            </p>

            {/* Best time line */}
            <p className="text-sm text-secondary mb-3">
              {t('keywordChangeBestTime')}
            </p>

            {/* How-to line (actionable, slightly more prominent) */}
            <p className="text-sm text-default mb-6">
              {t('keywordChangeHowTo').replace('{keyword}', pendingKeyword)}
            </p>

            <div className="flex gap-3 justify-end">
              <Button
                color="secondary"
                variant="ghost"
                size="sm"
                onClick={handleCancel}
              >
                {t('keywordChangeCancel')}
              </Button>
              <Button
                color="primary"
                variant="solid"
                size="sm"
                onClick={handleConfirm}
              >
                {t('keywordChangeConfirm')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
