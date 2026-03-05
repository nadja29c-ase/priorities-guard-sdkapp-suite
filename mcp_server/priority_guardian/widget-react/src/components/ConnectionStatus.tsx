import { useState, useCallback } from 'react'
import { extractStructuredContent } from '../utils'

interface ConnectionStatusProps {
  connected: boolean
  onRefresh: () => void
  isRefreshing: boolean
  awaitingOAuth: boolean
  onAwaitingOAuthChange: (awaiting: boolean) => void
}

export function ConnectionStatus({
  connected,
  onRefresh,
  isRefreshing,
  awaitingOAuth,
  onAwaitingOAuthChange,
}: ConnectionStatusProps) {
  const [isConnecting, setIsConnecting] = useState(false)
  const [isDisconnecting, setIsDisconnecting] = useState(false)
  const [showDisconnectConfirm, setShowDisconnectConfirm] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleConnect = useCallback(async () => {
    if (!window.openai?.callTool) {
      setError('Connection not available')
      return
    }

    setIsConnecting(true)
    setError(null)

    try {
      const result = await window.openai.callTool<{
        data?: { connect_url?: string }
      }>('connect_google_calendar', {})

      const content = extractStructuredContent<{ data?: { connect_url?: string } }>(result)
      const connectUrl = content?.data?.connect_url

      if (connectUrl) {
        if (window.openai.openExternal) {
          window.openai.openExternal({ href: connectUrl })
        } else {
          window.open(connectUrl, '_blank')
        }
        onAwaitingOAuthChange(true)
      }
    } catch (err) {
      console.error('Failed to initiate connection:', err)
      setError('Failed to start connection. Please try again.')
    } finally {
      setIsConnecting(false)
    }
  }, [onAwaitingOAuthChange])

  const handleCheckStatus = useCallback(() => {
    onAwaitingOAuthChange(false)
    onRefresh()
  }, [onRefresh, onAwaitingOAuthChange])

  const handleDisconnect = useCallback(async () => {
    if (!window.openai?.callTool) {
      setError('Disconnection not available')
      return
    }

    setIsDisconnecting(true)
    setError(null)

    try {
      await window.openai.callTool('disconnect_google_calendar', { confirm: true })
      setShowDisconnectConfirm(false)
      onRefresh()
    } catch (err) {
      console.error('Failed to disconnect:', err)
      setError('Failed to disconnect. Please try again.')
    } finally {
      setIsDisconnecting(false)
    }
  }, [onRefresh])

  return (
    <section className="rounded-xl p-4 bg-surface border border-default">
      {/* V7: Connection indicator row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full ${connected ? 'bg-success-solid' : 'bg-outline-default'}`}
            aria-hidden="true"
          />
          <span className="text-sm font-medium text-default">
            Google Calendar
          </span>
        </div>

        {connected ? (
          showDisconnectConfirm ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-secondary">
                Disconnect?
              </span>
              <button
                onClick={handleDisconnect}
                disabled={isDisconnecting}
                className={`text-xs font-medium px-2 py-1 rounded-lg transition-colors text-danger bg-danger-soft-alpha ${isDisconnecting ? 'opacity-60' : ''}`}
                aria-label="Confirm disconnect"
              >
                {isDisconnecting ? '...' : 'Yes'}
              </button>
              <button
                onClick={() => setShowDisconnectConfirm(false)}
                disabled={isDisconnecting}
                className="text-xs font-medium px-2 py-1 rounded-lg transition-colors text-secondary bg-surface-secondary"
                aria-label="Cancel disconnect"
              >
                No
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowDisconnectConfirm(true)}
              disabled={isRefreshing}
              className="text-xs font-medium px-3 py-1.5 rounded-lg transition-colors text-danger bg-danger-soft-alpha"
              aria-label="Disconnect Google Calendar"
            >
              Disconnect
            </button>
          )
        ) : awaitingOAuth ? (
          <button
            onClick={handleCheckStatus}
            disabled={isRefreshing}
            className={`text-xs font-medium px-3 py-1.5 rounded-lg transition-colors text-info bg-info-soft ${isRefreshing ? 'opacity-60' : ''}`}
            aria-label="Check connection status"
          >
            {isRefreshing ? 'Checking...' : 'Check status'}
          </button>
        ) : (
          <button
            onClick={handleConnect}
            disabled={isConnecting || isRefreshing}
            className={`text-xs font-medium px-3 py-1.5 rounded-lg transition-colors text-info bg-info-soft ${(isConnecting || isRefreshing) ? 'opacity-60' : ''}`}
            aria-label="Connect Google Calendar"
          >
            {isConnecting ? 'Connecting...' : 'Connect'}
          </button>
        )}
      </div>

      {/* V7: Instruction when connected - inside same section */}
      {connected && (
        <div className="rounded-lg px-3 py-2.5 mt-3 flex items-start gap-2 bg-surface-secondary">
          <svg
            className="w-3.5 h-3.5 flex-shrink-0 mt-0.5 text-tertiary"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            aria-hidden="true"
          >
            <rect x="2" y="3" width="12" height="11" rx="1.5" />
            <path d="M5 1.5v3M11 1.5v3M2 7h12" />
          </svg>
          <p className="text-xs leading-relaxed text-secondary">
            Add <strong className="text-default">P1</strong>,{' '}
            <strong className="text-default">P2</strong>, or{' '}
            <strong className="text-default">P3</strong>{' '}
            to your calendar event titles to track time toward each priority.
          </p>
        </div>
      )}

      {/* OAuth awaiting message */}
      {awaitingOAuth && !connected && (
        <div className="rounded-lg px-3 py-2.5 mt-3 bg-surface-secondary">
          <p className="text-xs text-secondary">
            Complete the authorization in the opened window, then click "Check status".
          </p>
        </div>
      )}

      {/* Error message */}
      {error && (
        <div
          className="rounded-lg px-3 py-2.5 mt-3 bg-danger-soft-alpha border border-danger-outline"
          role="alert"
        >
          <p className="text-xs text-danger">{error}</p>
        </div>
      )}
    </section>
  )
}
