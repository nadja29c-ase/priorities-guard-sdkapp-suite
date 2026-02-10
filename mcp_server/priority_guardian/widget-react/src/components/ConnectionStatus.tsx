import { useState, useCallback } from 'react'
import { Button } from '@openai/apps-sdk-ui/components/Button'
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
        // Open OAuth URL in external browser
        if (window.openai.openExternal) {
          window.openai.openExternal({ href: connectUrl })
        } else {
          window.open(connectUrl, '_blank')
        }

        // Show "Check status" button instead of auto-refreshing
        // OAuth flow takes 10-30+ seconds (user reads consent, clicks allow, redirect)
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
      // Refresh to update connection status
      onRefresh()
    } catch (err) {
      console.error('Failed to disconnect:', err)
      setError('Failed to disconnect. Please try again.')
    } finally {
      setIsDisconnecting(false)
    }
  }, [onRefresh])

  return (
    <div className="mb-4">
      <div className="flex items-center justify-between p-3 bg-surface rounded-xl border border-default">
        <div className="flex items-center gap-2">
          <div
            className={`w-2.5 h-2.5 rounded-full ${
              connected ? 'bg-success' : 'bg-tertiary'
            }`}
            aria-hidden="true"
          />
          <span className="text-sm text-secondary">
            Google Calendar: {connected ? 'Connected \u2713' : 'Not connected'}
          </span>
        </div>

        {connected ? (
          showDisconnectConfirm ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-secondary">Disconnect?</span>
              <Button
                color="danger"
                variant="outline"
                size="sm"
                onClick={handleDisconnect}
                disabled={isDisconnecting}
                aria-label="Confirm disconnect"
              >
                {isDisconnecting ? 'Disconnecting...' : 'Yes'}
              </Button>
              <Button
                color="secondary"
                variant="ghost"
                size="sm"
                onClick={() => setShowDisconnectConfirm(false)}
                disabled={isDisconnecting}
                aria-label="Cancel disconnect"
              >
                No
              </Button>
            </div>
          ) : (
            <Button
              color="secondary"
              variant="outline"
              size="sm"
              onClick={() => setShowDisconnectConfirm(true)}
              disabled={isRefreshing}
              aria-label="Disconnect Google Calendar"
            >
              Disconnect
            </Button>
          )
        ) : awaitingOAuth ? (
          <Button
            color="primary"
            variant="outline"
            size="sm"
            onClick={handleCheckStatus}
            disabled={isRefreshing}
            aria-label="Check connection status"
          >
            {isRefreshing ? 'Checking...' : 'Check status'}
          </Button>
        ) : (
          <Button
            color="primary"
            variant="solid"
            size="sm"
            onClick={handleConnect}
            disabled={isConnecting || isRefreshing}
            aria-label="Connect Google Calendar"
          >
            {isConnecting ? 'Connecting...' : 'Connect'}
          </Button>
        )}
      </div>

      {awaitingOAuth && !connected && (
        <div className="mt-2 p-2 text-xs text-secondary bg-surface rounded-lg border border-default">
          Complete the authorization in the opened window, then click "Check status".
        </div>
      )}

      {error && (
        <div className="mt-2 p-2 text-xs text-danger bg-surface rounded-lg border border-danger-outline" role="alert">
          {error}
        </div>
      )}
    </div>
  )
}
