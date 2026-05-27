import { useState } from 'react'
import { Button } from './Button'
import type { PriorityType } from '../types'
import { t } from '../i18n'

interface AddPriorityFormProps {
  availableKeywords: string[]
  onAdd: (data: {
    name: string
    type: PriorityType
    deadline?: string
    weekly_hour_target?: number
    checkpoint_date?: string
    initial_goal_text?: string
  }) => Promise<void>
  onCancel: () => void
}

type FormStep = 'name' | 'type' | 'fields'

export function AddPriorityForm({ availableKeywords, onAdd, onCancel }: AddPriorityFormProps) {
  const [step, setStep] = useState<FormStep>('name')
  const [priorityType, setPriorityType] = useState<PriorityType | null>(null)

  // Form fields
  const [name, setName] = useState('')
  const [deadline, setDeadline] = useState('')
  const [weeklyHourTarget, setWeeklyHourTarget] = useState('')
  const [checkpointDate, setCheckpointDate] = useState('')
  const [initialGoalText, setInitialGoalText] = useState('')

  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Hover states for interactive elements
  const [isHoveredBack, setIsHoveredBack] = useState(false)
  const [isHoveredDeadline, setIsHoveredDeadline] = useState(false)
  const [isHoveredFlexible, setIsHoveredFlexible] = useState(false)

  // Get tomorrow's date for min date constraint
  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  const minDate = tomorrow.toISOString().split('T')[0]

  // Detect touch-only device (covers iOS and Android)
  // navigator.userAgent is unreliable in sandboxed iframes — use touch detection instead
  const isTouchDevice = typeof window !== 'undefined' &&
    window.matchMedia('(hover: none) and (pointer: coarse)').matches

  // Use text input on touch devices to avoid native date picker overflow
  const dateInputType = isTouchDevice ? 'text' : 'date'
  const datePlaceholder = isTouchDevice ? 'YYYY-MM-DD' : undefined

  const handleNameNext = () => {
    if (name.trim()) {
      setError(null) // Clear stale error from previous steps
      setStep('type')
    }
  }

  const handleTypeSelect = (type: PriorityType) => {
    setError(null) // Clear stale error from previous steps
    setPriorityType(type)
    setStep('fields')
  }

  const handleBack = () => {
    if (step === 'fields') {
      setStep('type')
    } else if (step === 'type') {
      setStep('name')
    }
    setError(null)
  }

  const validateForm = (): boolean => {
    if (!name.trim()) {
      setError(t('nameRequired'))
      return false
    }
    if (priorityType === 'deadline' && !deadline) {
      setError(t('deadlineRequired'))
      return false
    }
    // On iOS with text input, validate date format
    if (priorityType === 'deadline' && isTouchDevice && deadline && !/^\d{4}-\d{2}-\d{2}$/.test(deadline)) {
      setError('Please use YYYY-MM-DD format')
      return false
    }
    if (priorityType === 'flexible') {
      if (!weeklyHourTarget) {
        setError(t('weeklyHoursRequired'))
        return false
      }
      if (parseFloat(weeklyHourTarget) <= 0) {
        setError(t('weeklyHoursPositive'))
        return false
      }
      if (!checkpointDate) {
        setError(t('checkpointRequired'))
        return false
      }
      // On iOS with text input, validate date format
      if (isTouchDevice && checkpointDate && !/^\d{4}-\d{2}-\d{2}$/.test(checkpointDate)) {
        setError('Please use YYYY-MM-DD format')
        return false
      }
      if (!initialGoalText.trim()) {
        setError(t('initialGoalRequired'))
        return false
      }
    }
    return true
  }

  const handleSubmit = async () => {
    if (isSubmitting) return
    if (!priorityType || !validateForm()) return

    setError(null)
    setIsSubmitting(true)

    try {
      const data: Parameters<typeof onAdd>[0] = {
        name: name.trim(),
        type: priorityType,
        // NO calendar_keyword — backend auto-assigns
      }

      if (priorityType === 'deadline') {
        data.deadline = deadline
      } else {
        data.weekly_hour_target = parseFloat(weeklyHourTarget)
        data.checkpoint_date = checkpointDate
        data.initial_goal_text = initialGoalText.trim()
      }

      await onAdd(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('failedToCreate'))
    } finally {
      setIsSubmitting(false)
    }
  }

  // No available keywords = max priorities reached
  if (availableKeywords.length === 0) {
    return null
  }

  // Common input style
  const inputStyle: React.CSSProperties = {
    width: '100%',
    boxSizing: 'border-box',          // Prevents iOS/Android width overflow
    WebkitAppearance: 'none',         // Prevents native date picker chrome
    fontSize: '14px',
    color: 'var(--color-text-primary, #0d0d0d)',
    background: 'var(--color-background-primary, #fff)',
    border: '1px solid var(--color-border, #e5e5e5)',
    borderRadius: '6px',
    padding: '8px 12px',
    outline: 'none',
  }

  // Label style
  const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: '12px',
    fontWeight: 500,
    color: 'var(--color-text-secondary, #737373)',
    marginBottom: '4px',
  }

  return (
    <div
      style={{
        background: 'var(--color-background-primary, #fff)',
        borderRadius: '12px',
        border: '1px solid var(--color-border, #e5e5e5)',
        padding: '16px',
      }}
    >
      {step === 'name' && (
        <div>
          <h3
            style={{
              fontSize: '16px',
              fontWeight: 600,
              color: 'var(--color-text-primary, #0d0d0d)',
              marginBottom: '12px',
            }}
          >
            {t('addPriorityTitle')}
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
              <label htmlFor="priority-name" style={labelStyle}>
                {t('whatToTrack')}
              </label>
              <input
                id="priority-name"
                type="text"
                value={name}
                onChange={(e) => {
                  setName(e.target.value)
                  if (error) setError(null)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && name.trim()) {
                    e.preventDefault()
                    handleNameNext()
                  }
                }}
                maxLength={100}
                placeholder={t('namePlaceholder')}
                style={inputStyle}
                autoFocus
              />
            </div>

            {/* Error display */}
            {error && (
              <p
                style={{
                  fontSize: '12px',
                  color: 'var(--color-text-danger, #dc2626)',
                }}
                role="alert"
              >
                {error}
              </p>
            )}

            {/* Actions */}
            <div style={{ display: 'flex', gap: '8px', paddingTop: '8px' }}>
              <Button
                color="primary"
                variant="solid"
                onClick={handleNameNext}
                disabled={!name.trim()}
              >
                {t('next')}
              </Button>
              <Button
                color="secondary"
                variant="ghost"
                onClick={onCancel}
              >
                {t('cancel')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {step === 'type' && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <button
              type="button"
              onClick={handleBack}
              onMouseEnter={() => setIsHoveredBack(true)}
              onMouseLeave={() => setIsHoveredBack(false)}
              style={{
                color: isHoveredBack ? 'var(--color-text-primary, #0d0d0d)' : 'var(--color-text-secondary, #737373)',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: 0,
              }}
              aria-label={t('goBack')}
            >
              <svg style={{ width: '20px', height: '20px' }} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clipRule="evenodd"/>
              </svg>
            </button>
            <h3
              style={{
                fontSize: '16px',
                fontWeight: 600,
                color: 'var(--color-text-primary, #0d0d0d)',
              }}
            >
              {t('whatKindOfPriority')}
            </h3>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <button
              type="button"
              onClick={() => handleTypeSelect('deadline')}
              onMouseEnter={() => setIsHoveredDeadline(true)}
              onMouseLeave={() => setIsHoveredDeadline(false)}
              style={{
                padding: '16px',
                border: `1px solid ${isHoveredDeadline ? 'var(--color-border-strong, #a3a3a3)' : 'var(--color-border, #e5e5e5)'}`,
                borderRadius: '8px',
                background: isHoveredDeadline ? 'var(--color-background-secondary, #f9f9f9)' : 'transparent',
                textAlign: 'left',
                cursor: 'pointer',
                transition: 'border-color 0.15s, background 0.15s',
              }}
              aria-label={t('deadlinePriority')}
            >
              <div style={{ fontSize: '18px', marginBottom: '4px' }}>{'\u23F1'}</div>
              <div style={{ fontWeight: 500, color: 'var(--color-text-primary, #0d0d0d)' }}>{t('deadlineType')}</div>
              <div style={{ fontSize: '12px', color: 'var(--color-text-secondary, #737373)' }}>{t('deadlineTypeHint')}</div>
            </button>

            <button
              type="button"
              onClick={() => handleTypeSelect('flexible')}
              onMouseEnter={() => setIsHoveredFlexible(true)}
              onMouseLeave={() => setIsHoveredFlexible(false)}
              style={{
                padding: '16px',
                border: `1px solid ${isHoveredFlexible ? 'var(--color-border-strong, #a3a3a3)' : 'var(--color-border, #e5e5e5)'}`,
                borderRadius: '8px',
                background: isHoveredFlexible ? 'var(--color-background-secondary, #f9f9f9)' : 'transparent',
                textAlign: 'left',
                cursor: 'pointer',
                transition: 'border-color 0.15s, background 0.15s',
              }}
              aria-label={t('flexiblePriority')}
            >
              <div style={{ fontSize: '18px', marginBottom: '4px' }}>{'\u21BB'}</div>
              <div style={{ fontWeight: 500, color: 'var(--color-text-primary, #0d0d0d)' }}>{t('flexibleType')}</div>
              <div style={{ fontSize: '12px', color: 'var(--color-text-secondary, #737373)' }}>{t('flexibleTypeHint')}</div>
            </button>
          </div>

          <div style={{ marginTop: '16px' }}>
            <Button
              color="secondary"
              variant="ghost"
              onClick={onCancel}
            >
              {t('cancel')}
            </Button>
          </div>
        </div>
      )}

      {step === 'fields' && priorityType && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <button
              type="button"
              onClick={handleBack}
              onMouseEnter={() => setIsHoveredBack(true)}
              onMouseLeave={() => setIsHoveredBack(false)}
              style={{
                color: isHoveredBack ? 'var(--color-text-primary, #0d0d0d)' : 'var(--color-text-secondary, #737373)',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: 0,
              }}
              aria-label={t('goBack')}
            >
              <svg style={{ width: '20px', height: '20px' }} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clipRule="evenodd"/>
              </svg>
            </button>
            <h3
              style={{
                fontSize: '16px',
                fontWeight: 600,
                color: 'var(--color-text-primary, #0d0d0d)',
              }}
            >
              {priorityType === 'deadline' ? t('deadlinePriority') : t('flexiblePriority')}
            </h3>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Deadline-specific fields */}
            {priorityType === 'deadline' && (
              <div>
                <label htmlFor="priority-deadline" style={labelStyle}>
                  {t('deadlineLabel')} <span style={{ color: 'var(--color-text-danger, #dc2626)' }}>*</span>
                </label>
                <input
                  id="priority-deadline"
                  type={dateInputType}
                  placeholder={datePlaceholder}
                  value={deadline}
                  onChange={(e) => {
                    setDeadline(e.target.value)
                    if (error) setError(null)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      handleSubmit()
                    }
                  }}
                  disabled={isSubmitting}
                  min={isTouchDevice ? undefined : minDate}
                  style={inputStyle}
                />
              </div>
            )}

            {/* Flexible-specific fields */}
            {priorityType === 'flexible' && (
              <>
                <div>
                  <label htmlFor="priority-hours" style={labelStyle}>
                    {t('weeklyHourTarget')} <span style={{ color: 'var(--color-text-danger, #dc2626)' }}>*</span>
                  </label>
                  <input
                    id="priority-hours"
                    type="number"
                    value={weeklyHourTarget}
                    onChange={(e) => {
                      setWeeklyHourTarget(e.target.value)
                      if (error) setError(null)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        handleSubmit()
                      }
                    }}
                    disabled={isSubmitting}
                    min="0.5"
                    step="0.5"
                    placeholder={t('hourTargetPlaceholder')}
                    style={inputStyle}
                  />
                </div>

                <div>
                  <label htmlFor="priority-checkpoint" style={labelStyle}>
                    {t('checkpointDate')} <span style={{ color: 'var(--color-text-danger, #dc2626)' }}>*</span>
                  </label>
                  <input
                    id="priority-checkpoint"
                    type={dateInputType}
                    placeholder={datePlaceholder}
                    value={checkpointDate}
                    onChange={(e) => {
                      setCheckpointDate(e.target.value)
                      if (error) setError(null)
                    }}
                    disabled={isSubmitting}
                    min={isTouchDevice ? undefined : minDate}
                    style={inputStyle}
                  />
                </div>

                <div>
                  <label htmlFor="priority-goal" style={labelStyle}>
                    {t('initialGoal')} <span style={{ color: 'var(--color-text-danger, #dc2626)' }}>*</span>
                  </label>
                  <textarea
                    id="priority-goal"
                    value={initialGoalText}
                    onChange={(e) => {
                      setInitialGoalText(e.target.value)
                      if (error) setError(null)
                    }}
                    disabled={isSubmitting}
                    maxLength={200}
                    rows={2}
                    placeholder={t('initialGoalPlaceholder')}
                    style={{
                      ...inputStyle,
                      resize: 'none',
                    }}
                  />
                </div>
              </>
            )}

            {/* Error display */}
            {error && (
              <p
                style={{
                  fontSize: '12px',
                  color: 'var(--color-text-danger, #dc2626)',
                }}
                role="alert"
              >
                {error}
              </p>
            )}

            {/* Actions */}
            <div style={{ display: 'flex', gap: '8px', paddingTop: '8px' }}>
              <Button
                color="primary"
                variant="solid"
                onClick={handleSubmit}
                disabled={isSubmitting}
              >
                {isSubmitting ? t('creating') : t('createPriority')}
              </Button>
              <Button
                color="secondary"
                variant="ghost"
                onClick={onCancel}
                disabled={isSubmitting}
              >
                {t('cancel')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// Add Priority Button (dashed border style)
export function AddPriorityButton({ onClick }: { onClick: () => void }) {
  const [isHovered, setIsHovered] = useState(false)

  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        width: '100%',
        padding: '16px',
        border: `2px dashed ${isHovered ? 'var(--color-border-strong, #a3a3a3)' : 'var(--color-border, #e5e5e5)'}`,
        borderRadius: '12px',
        background: isHovered ? 'var(--color-background-secondary, rgba(249, 249, 249, 0.5))' : 'transparent',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '8px',
        color: isHovered ? 'var(--color-text-primary, #0d0d0d)' : 'var(--color-text-secondary, #737373)',
        cursor: 'pointer',
        transition: 'border-color 0.15s, background 0.15s, color 0.15s',
      }}
      aria-label={t('addNewPriority')}
    >
      <svg style={{ width: '20px', height: '20px' }} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path fillRule="evenodd" d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z" clipRule="evenodd"/>
      </svg>
      <span style={{ fontWeight: 500 }}>{t('addNewPriority')}</span>
    </button>
  )
}
