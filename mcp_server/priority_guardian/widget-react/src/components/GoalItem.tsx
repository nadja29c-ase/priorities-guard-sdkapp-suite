import { useState, useRef, useEffect, useCallback } from 'react'
import type { Goal } from '../types'

interface GoalItemProps {
  goal: Goal
  onToggle: (goalId: string, achieved: boolean) => Promise<void>
  onRename?: (goalId: string, text: string) => Promise<void>
  onDelete?: (goalId: string) => Promise<void>
  disabled?: boolean
}

/**
 * GoalItem - V7 style
 * - 18px circular checkbox (green when achieved)
 * - Text with strikethrough when achieved
 * - No hover edit/delete actions (per V7 spec)
 */
export function GoalItem({
  goal,
  onToggle,
  disabled = false,
}: GoalItemProps) {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Clear timeout on unmount
  useEffect(() => {
    return () => {
      if (errorTimeoutRef.current) {
        clearTimeout(errorTimeoutRef.current)
      }
    }
  }, [])

  const handleToggle = useCallback(async () => {
    if (disabled || isLoading) return
    setIsLoading(true)
    setError(null)
    try {
      await onToggle(goal.id, !goal.achieved)
    } catch (e) {
      console.error('Toggle goal error:', e)
      setError(e instanceof Error ? e.message : 'Failed to update')
      errorTimeoutRef.current = setTimeout(() => setError(null), 3000)
    } finally {
      setIsLoading(false)
    }
  }, [disabled, isLoading, onToggle, goal.id, goal.achieved])

  return (
    <li className="flex items-start gap-2.5">
      {/* Circular checkbox - V7: 18px diameter */}
      <button
        type="button"
        onClick={handleToggle}
        disabled={disabled || isLoading}
        className="mt-0.5 flex-shrink-0 transition-all"
        title={goal.achieved ? 'Mark as not yet achieved' : 'Mark as achieved'}
        aria-label={goal.achieved ? 'Mark as not achieved' : 'Mark as achieved'}
      >
        <span
          className={`rounded-full flex items-center justify-center ${goal.achieved ? 'bg-success-solid' : ''}`}
          style={{
            width: '18px',
            height: '18px',
            border: goal.achieved ? 'none' : '1.5px solid var(--color-border-strong)',
            transition: 'all 150ms ease-out',
            opacity: (disabled || isLoading) ? 0.5 : 1,
            cursor: (disabled || isLoading) ? 'not-allowed' : 'pointer',
          }}
        >
          {goal.achieved && (
            <svg className="w-2.5 h-2.5" viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth="2">
              <path d="M2 6l3 3 5-5" />
            </svg>
          )}
        </span>
      </button>

      {/* Goal text */}
      <div className="flex-1 min-w-0">
        <p
          className={`text-sm flex-1 transition-colors ${goal.achieved ? 'line-through text-tertiary' : 'text-default'}`}
        >
          {goal.text}
        </p>
        {error && (
          <p className="text-xs text-danger mt-0.5" role="alert">{error}</p>
        )}
      </div>
    </li>
  )
}
