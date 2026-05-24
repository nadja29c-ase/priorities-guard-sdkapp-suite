import { useState, useEffect, useRef } from 'react'
import { Button } from './Button'
import type { Priority, CalendarKeyword } from '../types'
import { BADGE_COLORS } from '../constants'
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
  // Tooltip hover states
  const [hoveredKeyword, setHoveredKeyword] = useState<CalendarKeyword | null>(null)

  const modalRef = useRef<HTMLDivElement>(null)
  const cancelButtonRef = useRef<HTMLDivElement>(null)

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

  // Auto-focus cancel button on open (safe default)
  useEffect(() => {
    if (pendingKeyword === null) return
    cancelButtonRef.current?.querySelector('button')?.focus()
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
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ fontSize: '12px', color: 'var(--color-text-secondary, #737373)' }}>{t('badgeLabel')}</span>
        <div style={{ display: 'flex', gap: '6px' }}>
          {ALL_KEYWORDS.map((kw) => {
            const isSelected = kw === currentKeyword
            const holderName = keywordHolders.get(kw)
            const isHeldByOther = holderName && !isSelected
            const badgeColor = BADGE_COLORS[kw] ?? BADGE_COLORS.P1

            const isDisabled = disabled || isLoading

            return (
              <div
                key={kw}
                style={{ position: 'relative' }}
                onMouseEnter={() => setHoveredKeyword(kw)}
                onMouseLeave={() => setHoveredKeyword(null)}
              >
                <button
                  type="button"
                  onClick={() => handleClick(kw)}
                  disabled={isDisabled}
                  aria-pressed={isSelected}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '24px',
                    height: '24px',
                    borderRadius: '50%',
                    fontSize: '10px',
                    fontWeight: 700,
                    flexShrink: 0,
                    background: badgeColor.bg,
                    color: badgeColor.text,
                    transition: 'all 0.15s',
                    cursor: isDisabled ? 'not-allowed' : 'pointer',
                    opacity: isSelected ? 1 : 0.6,
                    outline: isSelected ? '2px solid currentColor' : 'none',
                    outlineOffset: '2px',
                    border: 'none',
                  }}
                  aria-label={`${isSelected ? t('currentKeyword') : t('switchTo')} ${kw}${isHeldByOther ? ` (${t('willSwapWith', { name: holderName! })})` : ''}`}
                >
                  {kw}
                </button>
                {/* Tooltip on hover for swap hint */}
                {isHeldByOther && hoveredKeyword === kw && (
                  <div
                    style={{
                      position: 'absolute',
                      bottom: '100%',
                      left: '50%',
                      transform: 'translateX(-50%)',
                      marginBottom: '4px',
                      padding: '4px 8px',
                      fontSize: '12px',
                      background: 'var(--color-background-tertiary, #ebebeb)',
                      color: 'var(--color-text-secondary, #737373)',
                      borderRadius: '4px',
                      whiteSpace: 'nowrap',
                      pointerEvents: 'none',
                      zIndex: 10,
                    }}
                  >
                    {t('swapWith', { name: holderName })}
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
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 50,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(0, 0, 0, 0.5)',
          }}
          onClick={handleBackdropClick}
          role="dialog"
          aria-modal="true"
          aria-labelledby="keyword-change-dialog-title"
        >
          <div
            ref={modalRef}
            style={{
              background: 'var(--color-background-primary, #fff)',
              borderRadius: '16px',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
              padding: '24px',
              maxWidth: '384px',
              width: '100%',
              margin: '0 16px',
            }}
          >
            <h2
              id="keyword-change-dialog-title"
              style={{
                fontSize: '18px',
                fontWeight: 600,
                color: 'var(--color-text-primary, #0d0d0d)',
                marginBottom: '12px',
              }}
            >
              {t('keywordChangeTitle')}
            </h2>

            {/* Body paragraph */}
            <p style={{ fontSize: '14px', color: 'var(--color-text-secondary, #737373)', marginBottom: '12px' }}>
              {t('keywordChangeBody', { oldKeyword: currentKeyword })}
            </p>

            {/* Best time line */}
            <p style={{ fontSize: '14px', color: 'var(--color-text-secondary, #737373)', marginBottom: '12px' }}>
              {t('keywordChangeBestTime')}
            </p>

            {/* How-to line (actionable, slightly more prominent) */}
            <p style={{ fontSize: '14px', color: 'var(--color-text-primary, #0d0d0d)', marginBottom: '24px' }}>
              {t('keywordChangeHowTo', { keyword: pendingKeyword })}
            </p>

            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <div ref={cancelButtonRef}>
                <Button
                  color="secondary"
                  variant="ghost"
                  size="sm"
                  onClick={handleCancel}
                  disabled={isLoading}
                >
                  {t('keywordChangeCancel')}
                </Button>
              </div>
              <Button
                color="primary"
                variant="solid"
                size="sm"
                onClick={handleConfirm}
                disabled={isLoading}
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
