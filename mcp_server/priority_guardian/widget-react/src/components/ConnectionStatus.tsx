import { useState, useCallback } from 'react'
import { extractStructuredContent } from '../utils'

interface ConnectionStatusProps {
  connected: boolean
  connectedAt?: string
  onRefresh: () => void
  isRefreshing: boolean
}

export function ConnectionStatus({ connected, onRefresh, isRefreshing }: ConnectionStatusProps) {
  const [isConnecting, setIsConnecting] = useState(false)
  const [isDisconnecting, setIsDisconnecting] = useState(false)
  const [showDisconnectConfirm, setShowDisconnectConfirm] = useState(false)
  const [awaitingOAuth, setAwaitingOAuth] = useState(false)
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
        setAwaitingOAuth(true)
      }
    } catch (err) {
      console.error('Failed to initiate connection:', err)
      setError('Failed to start connection. Please try again.')
    } finally {
      setIsConnecting(false)
    }
  }, [])

  const handleCheckStatus = useCallback(() => {
    setAwaitingOAuth(false)
    onRefresh()
  }, [onRefresh])

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
    <section
      className="mt-4 rounded-xl p-4"
      style={{
        background: 'var(--gray-0, #ffffff)',
        border: '1px solid var(--gray-100, #ededed)',
      }}
    >
      {/* V7: Connection indicator row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className="w-2 h-2 rounded-full"
            style={{
              background: connected
                ? 'var(--green-500, #00a240)'
                : 'var(--gray-300, #afafaf)',
            }}
            aria-hidden="true"
          />
          <span
            className="text-sm font-medium"
            style={{ color: 'var(--gray-700, #303030)' }}
          >
            Google Calendar
          </span>
        </div>

        {connected ? (
          showDisconnectConfirm ? (
            <div className="flex items-center gap-2">
              <span
                className="text-xs"
                style={{ color: 'var(--gray-500, #5d5d5d)' }}
              >
                Disconnect?
              </span>
              <button
                onClick={handleDisconnect}
                disabled={isDisconnecting}
                className="text-xs font-medium px-2 py-1 rounded-lg transition-colors"
                style={{
                  color: 'var(--red-500, #e02e2a)',
                  background: 'var(--red-50, #fef2f2)',
                  opacity: isDisconnecting ? 0.6 : 1,
                }}
                aria-label="Confirm disconnect"
              >
                {isDisconnecting ? '...' : 'Yes'}
              </button>
              <button
                onClick={() => setShowDisconnectConfirm(false)}
                disabled={isDisconnecting}
                className="text-xs font-medium px-2 py-1 rounded-lg transition-colors"
                style={{
                  color: 'var(--gray-500, #5d5d5d)',
                  background: 'var(--gray-50, #f9f9f9)',
                }}
                aria-label="Cancel disconnect"
              >
                No
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowDisconnectConfirm(true)}
              disabled={isRefreshing}
              className="text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
              style={{
                color: 'var(--red-500, #e02e2a)',
                background: 'var(--red-50, #fef2f2)',
              }}
              aria-label="Disconnect Google Calendar"
            >
              Disconnect
            </button>
          )
        ) : awaitingOAuth ? (
          <button
            onClick={handleCheckStatus}
            disabled={isRefreshing}
            className="text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
            style={{
              color: 'var(--blue-500, #0169cc)',
              background: 'var(--blue-50, #eff6ff)',
              opacity: isRefreshing ? 0.6 : 1,
            }}
            aria-label="Check connection status"
          >
            {isRefreshing ? 'Checking...' : 'Check status'}
          </button>
        ) : (
          <button
            onClick={handleConnect}
            disabled={isConnecting || isRefreshing}
            className="text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
            style={{
              color: 'var(--blue-500, #0169cc)',
              background: 'var(--blue-50, #eff6ff)',
              opacity: (isConnecting || isRefreshing) ? 0.6 : 1,
            }}
            aria-label="Connect Google Calendar"
          >
            {isConnecting ? 'Connecting...' : 'Connect'}
          </button>
        )}
      </div>

      {/* V7: Instruction when connected - inside same section */}
      {connected && (
        <div
          className="rounded-lg px-3 py-2.5 mt-3 flex items-start gap-2"
          style={{ background: 'var(--gray-50, #f9f9f9)' }}
        >
          <svg
            className="w-3.5 h-3.5 flex-shrink-0 mt-0.5"
            viewBox="0 0 16 16"
            fill="none"
            stroke="var(--gray-400, #8f8f8f)"
            strokeWidth="1.5"
          >
            <rect x="2" y="3" width="12" height="11" rx="1.5" />
            <path d="M5 1.5v3M11 1.5v3M2 7h12" />
          </svg>
          <p
            className="text-xs leading-relaxed"
            style={{ color: 'var(--gray-450, #767676)' }}
          >
            Add <strong style={{ color: 'var(--gray-700, #303030)' }}>P1</strong>,{' '}
            <strong style={{ color: 'var(--gray-700, #303030)' }}>P2</strong>, or{' '}
            <strong style={{ color: 'var(--gray-700, #303030)' }}>P3</strong>{' '}
            to your calendar event titles to track time toward each priority.
          </p>
        </div>
      )}

      {/* OAuth awaiting message */}
      {awaitingOAuth && !connected && (
        <div
          className="rounded-lg px-3 py-2.5 mt-3"
          style={{ background: 'var(--gray-50, #f9f9f9)' }}
        >
          <p
            className="text-xs"
            style={{ color: 'var(--gray-500, #5d5d5d)' }}
          >
            Complete the authorization in the opened window, then click "Check status".
          </p>
        </div>
      )}

      {/* Error message */}
      {error && (
        <div
          className="rounded-lg px-3 py-2.5 mt-3"
          style={{
            background: 'var(--red-50, #fef2f2)',
            border: '1px solid var(--red-200, #fecaca)',
          }}
          role="alert"
        >
          <p
            className="text-xs"
            style={{ color: 'var(--red-600, #dc2626)' }}
          >
            {error}
          </p>
        </div>
      )}
    </section>
  )
}
