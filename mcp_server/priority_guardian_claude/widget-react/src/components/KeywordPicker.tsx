import { useState, useEffect, useRef } from 'react'
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
 *
 * Confirmation is inline (no modal/popover) per MCP Apps guidelines.
 */
export function KeywordPicker({
  currentKeyword,
  priorities,
  onKeywordChange,
  disabled = false,
}: KeywordPickerProps) {
  // Prevent concurrent swaps from rapid taps
  const [loadingKeyword, setLoadingKeyword] = useState<CalendarKeyword | null>(null)
  // Pending keyword for inline confirmation
  const [pendingKeyword, setPendingKeyword] = useState<CalendarKeyword | null>(null)
  // Tooltip hover states
  const [hoveredKeyword, setHoveredKeyword] = useState<CalendarKeyword | null>(null)
  // Hover states for inline confirmation buttons
  const [isHoveredConfirm, setIsHoveredConfirm] = useState(false)
  const [isHoveredCancel, setIsHoveredCancel] = useState(false)

  const cancelButtonRef = useRef<HTMLButtonElement>(null)

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
    // Set pending keyword and show inline confirmation
    setPendingKeyword(kw)
  }

  const handleConfirm = async () => {
    if (!pendingKeyword) return
    const kwToChange = pendingKeyword
    // Dismiss confirmation immediately
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

  // Auto-focus cancel button when confirmation appears (safe default)
  useEffect(() => {
    if (pendingKeyword !== null) {
      cancelButtonRef.current?.focus()
    }
  }, [pendingKeyword])

  // ESC key dismisses inline confirmation
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

  const isLoading = loadingKeyword !== null
  const pendingBadgeColor = pendingKeyword ? (BADGE_COLORS[pendingKeyword] ?? BADGE_COLORS.P1) : null

  return (
    <div>
      {/* Keyword badges row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ fontSize: '12px', color: 'var(--color-text-secondary, #73726C)' }}>{t('badgeLabel')}</span>
        <div style={{ display: 'flex', gap: '6px' }}>
          {ALL_KEYWORDS.map((kw) => {
            const isSelected = kw === currentKeyword
            const isPending = kw === pendingKeyword
            const holderName = keywordHolders.get(kw)
            const isHeldByOther = holderName && !isSelected
            const badgeColor = BADGE_COLORS[kw] ?? BADGE_COLORS.P1

            const isDisabled = disabled || isLoading || pendingKeyword !== null

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
                    minWidth: '44px',
                    minHeight: '44px',
                    padding: '10px',
                    margin: '-10px',
                    boxSizing: 'content-box',
                    background: 'none',
                    border: 'none',
                    cursor: isDisabled ? 'not-allowed' : 'pointer',
                    touchAction: 'manipulation',
                    WebkitTapHighlightColor: 'transparent',
                  }}
                  aria-label={`${isSelected ? t('currentKeyword') : t('switchTo')} ${kw}${isHeldByOther ? ` (${t('willSwapWith', { name: holderName! })})` : ''}`}
                >
                  <span
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
                      opacity: isSelected || isPending ? 1 : 0.6,
                      outline: isSelected ? '2px solid currentColor' : isPending ? '2px dashed currentColor' : 'none',
                      outlineOffset: '2px',
                    }}
                  >
                    {kw}
                  </span>
                </button>
                {/* Tooltip on hover for swap hint */}
                {isHeldByOther && hoveredKeyword === kw && !pendingKeyword && (
                  <div
                    style={{
                      position: 'absolute',
                      bottom: '100%',
                      left: '50%',
                      transform: 'translateX(-50%)',
                      marginBottom: '4px',
                      padding: '4px 8px',
                      fontSize: '12px',
                      background: 'var(--color-background-tertiary, #FAF9F5)',
                      color: 'var(--color-text-secondary, #73726C)',
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

      {/* Inline confirmation row (no modal/popover) */}
      {pendingKeyword !== null && (
        <div
          style={{
            marginTop: '12px',
            padding: '12px',
            background: 'var(--color-background-secondary, #F5F4ED)',
            borderRadius: '8px',
          }}
          role="region"
          aria-live="polite"
          aria-label={t('keywordChangeTitle')}
        >
          {/* Confirmation message */}
          <p style={{ fontSize: '12px', color: 'var(--color-text-primary, #141413)', marginBottom: '8px' }}>
            {t('keywordChangeInline', { oldKeyword: currentKeyword, newKeyword: pendingKeyword })}
          </p>

          {/* Swap hint if applicable */}
          {keywordHolders.get(pendingKeyword) && (
            <p style={{ fontSize: '12px', color: 'var(--color-text-secondary, #73726C)', marginBottom: '8px' }}>
              {t('willSwapWith', { name: keywordHolders.get(pendingKeyword)! })}
            </p>
          )}

          {/* Action buttons */}
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={isLoading}
              onMouseEnter={() => setIsHoveredConfirm(true)}
              onMouseLeave={() => setIsHoveredConfirm(false)}
              style={{
                padding: '8px 16px',
                minHeight: '44px',
                fontSize: '12px',
                fontWeight: 500,
                borderRadius: '8px',
                background: pendingBadgeColor?.bg ?? 'var(--color-background-info-solid, #0285ff)',
                color: pendingBadgeColor?.text ?? '#fff',
                border: 'none',
                cursor: isLoading ? 'not-allowed' : 'pointer',
                opacity: isLoading ? 0.5 : isHoveredConfirm ? 0.9 : 1,
                transition: 'opacity 0.15s',
                touchAction: 'manipulation',
                WebkitTapHighlightColor: 'transparent',
              }}
              aria-label={t('keywordChangeConfirm')}
            >
              {t('keywordChangeConfirm')}
            </button>
            <button
              ref={cancelButtonRef}
              type="button"
              onClick={handleCancel}
              disabled={isLoading}
              onMouseEnter={() => setIsHoveredCancel(true)}
              onMouseLeave={() => setIsHoveredCancel(false)}
              style={{
                padding: '8px 16px',
                minHeight: '44px',
                fontSize: '12px',
                fontWeight: 500,
                borderRadius: '8px',
                background: 'transparent',
                color: isHoveredCancel ? 'var(--color-text-primary, #141413)' : 'var(--color-text-secondary, #73726C)',
                border: 'none',
                cursor: isLoading ? 'not-allowed' : 'pointer',
                transition: 'color 0.15s',
                touchAction: 'manipulation',
                WebkitTapHighlightColor: 'transparent',
              }}
              aria-label={t('keywordChangeCancel')}
            >
              {t('keywordChangeCancel')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
