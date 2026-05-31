import { useState, useRef, useEffect } from 'react'
import type { Goal } from '../types'
import { GoalItem } from './GoalItem'
import { ChevronIcon } from './ChevronIcon'
import { getRawLocale } from '../i18n'
import { t } from '../i18n'

interface GoalSectionProps {
  goals: Goal[]
  checkpointDate?: string
  defaultExpanded?: boolean
  isInline?: boolean  // When true, display-only (no CRUD actions)
  disabled?: boolean  // When true, disable all CRUD interactions
  onToggleGoal?: (goalId: string, achieved: boolean) => Promise<void>
  onRenameGoal?: (goalId: string, text: string) => Promise<void>
  onDeleteGoal?: (goalId: string) => Promise<void>
  onAddGoal?: (text: string) => Promise<void>
  maxGoals?: number
}

export function GoalSection({
  goals,
  checkpointDate,
  defaultExpanded = false,
  isInline = false,
  disabled = false,
  onToggleGoal,
  onRenameGoal,
  onDeleteGoal,
  onAddGoal,
  maxGoals = 3,
}: GoalSectionProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const [newGoalText, setNewGoalText] = useState('')
  const [isAdding, setIsAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isHoveredAddButton, setIsHoveredAddButton] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Collapsible if there are any goals
  const isCollapsible = goals.length > 0

  // Sync expanded state when display mode changes
  useEffect(() => {
    setExpanded(defaultExpanded)
  }, [defaultExpanded])

  const canAddMore = goals.length < maxGoals

  // Clear timeout on unmount
  useEffect(() => {
    return () => {
      if (errorTimeoutRef.current) {
        clearTimeout(errorTimeoutRef.current)
      }
    }
  }, [])

  const handleAddGoal = async () => {
    if (!onAddGoal) return
    const trimmed = newGoalText.trim()
    if (!trimmed) {
      setIsAdding(false)
      return
    }

    setError(null)
    try {
      await onAddGoal(trimmed)
      setNewGoalText('')
      setIsAdding(false)
    } catch (e) {
      console.error('Add goal error:', e)
      setError(e instanceof Error ? e.message : t('failedToAddGoal'))
      errorTimeoutRef.current = setTimeout(() => setError(null), 3000)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleAddGoal()
    } else if (e.key === 'Escape') {
      setNewGoalText('')
      setIsAdding(false)
    }
  }

  // Format checkpoint date
  const formatDate = (dateStr: string) => {
    const locale = getRawLocale()
    const date = new Date(dateStr + 'T00:00:00')
    return date.toLocaleDateString(locale, { month: 'short', day: 'numeric' })
  }

  const achievedCount = goals.filter(g => g.achieved).length

  // Inline mode - display only (using inline styles for Claude widget)
  if (isInline) {
    return (
      <div style={{ borderTop: '1px solid var(--color-border-subtle, #f0f0f0)', paddingTop: '8px' }}>
        {/* Header */}
        <button
          type="button"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginBottom: '8px',
            width: '100%',
            textAlign: 'left',
            background: 'none',
            border: 'none',
            padding: 0,
            cursor: isCollapsible ? 'pointer' : 'default',
            color: 'var(--color-text-tertiary, #73726C)',
          }}
          onClick={() => isCollapsible && setExpanded(!expanded)}
          aria-expanded={expanded}
          aria-label={goals.length === 1 ? t('oneMonthGoal') : t('oneMonthGoals')}
        >
          {isCollapsible && (
            <ChevronIcon expanded={expanded} />
          )}
          <span
            style={{
              fontSize: '10px',
              fontWeight: 500,
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
            }}
          >
            {goals.length === 1 ? t('oneMonthGoal') : t('oneMonthGoals')}
          </span>
          {checkpointDate && (
            <span style={{ fontSize: '10px' }}>
              {t('by')} {formatDate(checkpointDate)}
            </span>
          )}
          {goals.length > 0 && (
            <span style={{ fontSize: '10px', color: 'var(--color-text-secondary, #3D3D3A)', marginLeft: 'auto' }}>
              {achievedCount}/{goals.length}
            </span>
          )}
        </button>

        {/* Goals list */}
        {(expanded || !isCollapsible) && (
          <>
            {goals.length > 0 ? (
              <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '8px' }} aria-label={t('goalsList')}>
                {goals.map((goal) => (
                  <GoalItem key={goal.id} goal={goal} isInline />
                ))}
              </ul>
            ) : (
              <p style={{ fontSize: '11px', color: 'var(--color-text-tertiary, #73726C)', marginBottom: '8px' }}>{t('noGoalsYet')}</p>
            )}
          </>
        )}
      </div>
    )
  }

  // Fullscreen mode - interactive with CRUD
  return (
    <div style={{ borderTop: '1px solid var(--color-border-subtle, #f0f0f0)', paddingTop: '12px' }}>
      {/* Header */}
      <button
        type="button"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          marginBottom: '8px',
          width: '100%',
          textAlign: 'left',
          background: 'none',
          border: 'none',
          padding: 0,
          cursor: isCollapsible ? 'pointer' : 'default',
        }}
        onClick={() => isCollapsible && setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-label={goals.length === 1 ? t('oneMonthGoal') : t('oneMonthGoals')}
      >
        {isCollapsible && (
          <ChevronIcon expanded={expanded} />
        )}
        <span
          style={{
            fontSize: '12px',
            fontWeight: 500,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            color: 'var(--color-text-tertiary, #73726C)',
          }}
        >
          {goals.length === 1 ? t('oneMonthGoal') : t('oneMonthGoals')}
        </span>
        {checkpointDate && (
          <span style={{ fontSize: '12px', color: 'var(--color-text-tertiary, #73726C)' }}>
            {t('by')} {formatDate(checkpointDate)}
          </span>
        )}
        {goals.length > 0 && (
          <span style={{ fontSize: '12px', color: 'var(--color-text-secondary, #3D3D3A)', marginLeft: 'auto' }}>
            {achievedCount}/{goals.length}
          </span>
        )}
      </button>

      {/* Goals list */}
      {(expanded || !isCollapsible) && (
        <>
          {goals.length > 0 ? (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '8px' }} aria-label={t('goalsList')}>
              {goals.map((goal) => (
                <GoalItem
                  key={goal.id}
                  goal={goal}
                  onToggle={onToggleGoal}
                  onRename={onRenameGoal}
                  onDelete={onDeleteGoal}
                  disabled={disabled}
                />
              ))}
            </ul>
          ) : (
            <p style={{ fontSize: '12px', color: 'var(--color-text-tertiary, #73726C)', marginBottom: '8px' }}>{t('noGoalsYet')}</p>
          )}

          {/* Add goal input */}
          {canAddMore && onAddGoal && !disabled && (
            isAdding ? (
              <div>
                <input
                  ref={inputRef}
                  type="text"
                  value={newGoalText}
                  onChange={(e) => setNewGoalText(e.target.value)}
                  onBlur={handleAddGoal}
                  onKeyDown={handleKeyDown}
                  maxLength={200}
                  placeholder={t('goalPlaceholder')}
                  autoFocus
                  style={{
                    width: '100%',
                    fontSize: '14px',
                    color: 'var(--color-text-primary, #0d0d0d)',
                    background: 'var(--color-background-primary, #fff)',
                    border: '1px solid var(--color-border, #e5e5e5)',
                    borderRadius: '6px',
                    padding: '4px 8px',
                    outline: 'none',
                  }}
                  aria-label={t('newGoalText')}
                />
                {error && (
                  <p style={{ fontSize: '12px', color: 'var(--color-text-danger, #dc2626)', marginTop: '4px' }} role="alert">
                    {error}
                  </p>
                )}
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setIsAdding(true)}
                onMouseEnter={() => setIsHoveredAddButton(true)}
                onMouseLeave={() => setIsHoveredAddButton(false)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  fontSize: '12px',
                  color: isHoveredAddButton ? 'var(--color-text-primary, #0d0d0d)' : 'var(--color-text-secondary, #737373)',
                  background: 'none',
                  border: 'none',
                  padding: 0,
                  cursor: 'pointer',
                }}
              >
                <svg style={{ width: '12px', height: '12px' }} viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                  <path d="M8 3a.5.5 0 01.5.5v4h4a.5.5 0 010 1h-4v4a.5.5 0 01-1 0v-4h-4a.5.5 0 010-1h4v-4A.5.5 0 018 3z" />
                </svg>
                {t('addGoal')}
              </button>
            )
          )}
        </>
      )}
    </div>
  )
}
