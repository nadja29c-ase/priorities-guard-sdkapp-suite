import { useState } from 'react'
import { Button } from '@openai/apps-sdk-ui/components/Button'
import type { PriorityType } from '../types'

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

  // Get tomorrow's date for min date constraint
  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  const minDate = tomorrow.toISOString().split('T')[0]

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
      setError('Name is required')
      return false
    }
    if (priorityType === 'deadline' && !deadline) {
      setError('Deadline is required')
      return false
    }
    if (priorityType === 'flexible') {
      if (!weeklyHourTarget) {
        setError('Weekly hour target is required')
        return false
      }
      if (parseFloat(weeklyHourTarget) <= 0) {
        setError('Weekly hour target must be greater than 0')
        return false
      }
      if (!checkpointDate) {
        setError('Checkpoint date is required')
        return false
      }
      if (!initialGoalText.trim()) {
        setError('Initial goal is required')
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
      setError(e instanceof Error ? e.message : 'Failed to create priority')
    } finally {
      setIsSubmitting(false)
    }
  }

  // No available keywords = max priorities reached
  if (availableKeywords.length === 0) {
    return null
  }

  return (
    <div className="bg-surface rounded-xl border border-default p-4">
      {step === 'name' && (
        <div>
          <h3 className="text-base font-semibold text-default mb-3">Add Priority</h3>

          <div className="space-y-4">
            <div>
              <label htmlFor="priority-name" className="block text-xs font-medium text-secondary mb-1">
                What do you want to track?
              </label>
              <input
                id="priority-name"
                type="text"
                value={name}
                onChange={(e) => {
                  setName(e.target.value)
                  if (error) setError(null)
                }}
                maxLength={100}
                placeholder="e.g., Ship v1.0, Client outreach"
                className="w-full text-sm text-default bg-surface border border-default rounded-md px-3 py-2 focus:outline-none focus:border-tertiary"
                autoFocus
              />
            </div>

            {/* Error display */}
            {error && (
              <p className="text-xs text-danger" role="alert">
                {error}
              </p>
            )}

            {/* Actions */}
            <div className="flex gap-2 pt-2">
              <Button
                color="primary"
                variant="solid"
                onClick={handleNameNext}
                disabled={!name.trim()}
              >
                Next
              </Button>
              <Button
                color="secondary"
                variant="outline"
                onClick={onCancel}
              >
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}

      {step === 'type' && (
        <div>
          <div className="flex items-center gap-2 mb-4">
            <button
              type="button"
              onClick={handleBack}
              className="text-secondary hover:text-default"
              aria-label="Go back to name"
            >
              <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clipRule="evenodd"/>
              </svg>
            </button>
            <h3 className="text-base font-semibold text-default">What kind of priority?</h3>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => handleTypeSelect('deadline')}
              className="p-4 border border-default rounded-lg hover:border-strong hover:bg-surface-secondary text-left transition-colors"
              aria-label="Create deadline priority"
            >
              <div className="text-lg mb-1">{'\u23F1'}</div>
              <div className="font-medium text-default">Deadline</div>
              <div className="text-xs text-secondary">Has a hard end date</div>
            </button>

            <button
              type="button"
              onClick={() => handleTypeSelect('flexible')}
              className="p-4 border border-default rounded-lg hover:border-strong hover:bg-surface-secondary text-left transition-colors"
              aria-label="Create flexible priority"
            >
              <div className="text-lg mb-1">{'\u21BB'}</div>
              <div className="font-medium text-default">Flexible</div>
              <div className="text-xs text-secondary">Ongoing weekly commitment</div>
            </button>
          </div>

          <div className="mt-4">
            <Button
              color="secondary"
              variant="outline"
              onClick={onCancel}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {step === 'fields' && priorityType && (
        <div>
          <div className="flex items-center gap-2 mb-4">
            <button
              type="button"
              onClick={handleBack}
              className="text-secondary hover:text-default"
              aria-label="Go back to type selection"
            >
              <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clipRule="evenodd"/>
              </svg>
            </button>
            <h3 className="text-base font-semibold text-default">
              {priorityType === 'deadline' ? 'Deadline Priority' : 'Flexible Priority'}
            </h3>
          </div>

          <div className="space-y-4">
            {/* Deadline-specific fields */}
            {priorityType === 'deadline' && (
              <div>
                <label htmlFor="priority-deadline" className="block text-xs font-medium text-secondary mb-1">
                  Deadline <span className="text-danger">*</span>
                </label>
                <input
                  id="priority-deadline"
                  type="date"
                  value={deadline}
                  onChange={(e) => {
                    setDeadline(e.target.value)
                    if (error) setError(null)
                  }}
                  disabled={isSubmitting}
                  min={minDate}
                  className="w-full text-sm text-default bg-surface border border-default rounded-md px-3 py-2 focus:outline-none focus:border-tertiary"
                />
              </div>
            )}

            {/* Flexible-specific fields */}
            {priorityType === 'flexible' && (
              <>
                <div>
                  <label htmlFor="priority-hours" className="block text-xs font-medium text-secondary mb-1">
                    Weekly Hour Target <span className="text-danger">*</span>
                  </label>
                  <input
                    id="priority-hours"
                    type="number"
                    value={weeklyHourTarget}
                    onChange={(e) => {
                      setWeeklyHourTarget(e.target.value)
                      if (error) setError(null)
                    }}
                    disabled={isSubmitting}
                    min="0.5"
                    step="0.5"
                    placeholder="e.g., 10"
                    className="w-full text-sm text-default bg-surface border border-default rounded-md px-3 py-2 focus:outline-none focus:border-tertiary"
                  />
                </div>

                <div>
                  <label htmlFor="priority-checkpoint" className="block text-xs font-medium text-secondary mb-1">
                    Checkpoint Date <span className="text-danger">*</span>
                  </label>
                  <input
                    id="priority-checkpoint"
                    type="date"
                    value={checkpointDate}
                    onChange={(e) => {
                      setCheckpointDate(e.target.value)
                      if (error) setError(null)
                    }}
                    disabled={isSubmitting}
                    min={minDate}
                    className="w-full text-sm text-default bg-surface border border-default rounded-md px-3 py-2 focus:outline-none focus:border-tertiary"
                  />
                </div>

                <div>
                  <label htmlFor="priority-goal" className="block text-xs font-medium text-secondary mb-1">
                    Initial Goal <span className="text-danger">*</span>
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
                    placeholder="What do you want to achieve in ~1 month?"
                    className="w-full text-sm text-default bg-surface border border-default rounded-md px-3 py-2 focus:outline-none focus:border-tertiary resize-none"
                  />
                </div>
              </>
            )}

            {/* Error display */}
            {error && (
              <p className="text-xs text-danger" role="alert">
                {error}
              </p>
            )}

            {/* Actions */}
            <div className="flex gap-2 pt-2">
              <Button
                color="primary"
                variant="solid"
                onClick={handleSubmit}
                disabled={isSubmitting}
              >
                {isSubmitting ? 'Creating...' : 'Create Priority'}
              </Button>
              <Button
                color="secondary"
                variant="outline"
                onClick={onCancel}
                disabled={isSubmitting}
              >
                Cancel
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
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full p-4 border-2 border-dashed border-default rounded-xl hover:border-strong hover:bg-surface-secondary/50 transition-colors flex items-center justify-center gap-2 text-secondary hover:text-default"
      aria-label="Add a new priority"
    >
      <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path fillRule="evenodd" d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z" clipRule="evenodd"/>
      </svg>
      <span className="font-medium">Add a new priority</span>
    </button>
  )
}
