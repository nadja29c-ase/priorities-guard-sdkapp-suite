import { useState, useRef, useEffect } from 'react'
import type { Goal } from '../types'
import { GoalItem } from './GoalItem'
import { ChevronIcon } from './ChevronIcon'
import { normalizeLocale } from '../utils'
import { t } from '../i18n'

interface GoalSectionProps {
  goals: Goal[]
  checkpointDate?: string
  defaultExpanded?: boolean
  onToggleGoal: (goalId: string, achieved: boolean) => Promise<void>
  onRenameGoal: (goalId: string, text: string) => Promise<void>
  onDeleteGoal: (goalId: string) => Promise<void>
  onAddGoal: (text: string) => Promise<void>
  maxGoals?: number
}

export function GoalSection({
  goals,
  checkpointDate,
  defaultExpanded = false,
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
  const inputRef = useRef<HTMLInputElement>(null)
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Collapsible if multiple goals OR currently collapsed (allows re-expand)
  const isCollapsible = goals.length > 1 || !expanded

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

  // Format checkpoint date using SDK locale
  const formatDate = (dateStr: string) => {
    const locale = normalizeLocale(window.openai?.locale || 'en-US')
    const date = new Date(dateStr + 'T00:00:00')
    return date.toLocaleDateString(locale, { month: 'short', day: 'numeric' })
  }

  const achievedCount = goals.filter(g => g.achieved).length

  return (
    <div className="border-t border-subtle pt-2">
      {/* Header */}
      <button
        type="button"
        className={`flex items-center gap-2 ${expanded ? 'mb-1' : ''} w-full text-left ${isCollapsible ? 'cursor-pointer' : ''}`}
        onClick={() => isCollapsible && setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-label={goals.length === 1 ? t('oneMonthGoal') : t('oneMonthGoals')}
      >
        {isCollapsible && (
          <ChevronIcon expanded={expanded} className="text-tertiary" />
        )}
        <span className="text-xs font-medium text-tertiary uppercase tracking-wide">
          {goals.length === 1 ? t('oneMonthGoal') : t('oneMonthGoals')}
        </span>
        {checkpointDate && (
          <span className="text-xs text-tertiary">
            {t('by')} {formatDate(checkpointDate)}
          </span>
        )}
        {goals.length > 0 && (
          <span className="text-xs text-secondary ml-auto">
            {achievedCount}/{goals.length}
          </span>
        )}
      </button>

      {/* Goals list */}
      {(expanded || !isCollapsible) && (
        <>
          {goals.length > 0 ? (
            <ul className="space-y-1.5 mb-2" aria-label="Goals list">
              {goals.map((goal) => (
                <GoalItem
                  key={goal.id}
                  goal={goal}
                  onToggle={onToggleGoal}
                  onRename={onRenameGoal}
                  onDelete={onDeleteGoal}
                />
              ))}
            </ul>
          ) : (
            <p className="text-xs text-tertiary mb-2">{t('noGoalsYet')}</p>
          )}

          {/* Add goal input */}
          {canAddMore && (
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
                  className="w-full text-sm text-default bg-surface border border-default rounded px-2 py-1 focus:outline-none focus:border-tertiary"
                  aria-label="New goal text"
                />
                {error && (
                  <p className="text-xs text-danger mt-1" role="alert">{error}</p>
                )}
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setIsAdding(true)}
                className="text-xs text-secondary hover:text-default flex items-center gap-1"
              >
                <svg className="w-3 h-3" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
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
