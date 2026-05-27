import { useState, useCallback } from 'react'
import type { App as McpApp } from '@modelcontextprotocol/ext-apps'
import { extractClaudeStructuredContent } from '../utils'
import { t } from '../i18n'

// Timeout wrapper for callServerTool — detects stale sessions
const TOOL_TIMEOUT_MS = 9000

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return Promise.race([
    promise,
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('timeout')), ms)
    ),
  ])
}

interface ConnectionStatusProps {
  app: McpApp
  connected: boolean
  onRefresh: () => void
  isRefreshing: boolean
  awaitingOAuth: boolean
  onAwaitingOAuthChange: (awaiting: boolean) => void
}

export function ConnectionStatus({
  app,
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
    if (!app?.callServerTool) {
      setError(t('connectionNotAvailable'))
      return
    }

    setIsConnecting(true)
    setError(null)

    try {
      const result = await withTimeout(
        app.callServerTool({
          name: 'connect_google_calendar',
          arguments: {},
        }),
        TOOL_TIMEOUT_MS
      )

      const content = extractClaudeStructuredContent<{ data?: { connect_url?: string } }>(result)
      const connectUrl = content?.data?.connect_url

      if (connectUrl) {
        // MCP Apps SDK uses openLink for external URLs
        if (app.openLink) {
          await app.openLink({ url: connectUrl })
          onAwaitingOAuthChange(true)
        } else {
          setError(t('failedToConnect'))
          return
        }
      } else {
        setError(t('failedToConnect'))
      }
    } catch (err) {
      console.error('Failed to initiate connection:', err)
      if (err instanceof Error && err.message === 'timeout') {
        setError(t('sessionExpiredRetry'))
      } else {
        setError(t('failedToConnect'))
      }
    } finally {
      setIsConnecting(false)
    }
  }, [app, onAwaitingOAuthChange])

  const handleCheckStatus = useCallback(() => {
    onAwaitingOAuthChange(false)
    onRefresh()
  }, [onRefresh, onAwaitingOAuthChange])

  const handleDisconnect = useCallback(async () => {
    if (!app?.callServerTool) {
      setError(t('connectionNotAvailable'))
      return
    }

    setIsDisconnecting(true)
    setError(null)

    try {
      await withTimeout(
        app.callServerTool({
          name: 'disconnect_google_calendar',
          arguments: { confirm: true },
        }),
        TOOL_TIMEOUT_MS
      )
      setShowDisconnectConfirm(false)
      onAwaitingOAuthChange(false)
      onRefresh()
    } catch (err) {
      console.error('Failed to disconnect:', err)
      if (err instanceof Error && err.message === 'timeout') {
        setError(t('sessionExpiredRetry'))
      } else {
        setError(t('failedToDisconnect'))
      }
    } finally {
      setIsDisconnecting(false)
    }
  }, [app, onRefresh, onAwaitingOAuthChange])

  return (
    <section
      style={{
        borderRadius: '12px',
        padding: '16px',
        background: 'var(--color-background-primary, #fff)',
        border: '1px solid var(--color-border, #e5e5e5)',
      }}
    >
      {/* V7: Connection indicator row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: connected ? 'var(--color-background-success-solid, #10b981)' : 'var(--color-background-tertiary, #ebebeb)',
            }}
            aria-hidden="true"
          />
          <span style={{ fontSize: '14px', fontWeight: 500, color: 'var(--color-text-primary, #0d0d0d)' }}>
            {t('googleCalendar')}
          </span>
        </div>

        {connected ? (
          showDisconnectConfirm ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '12px', color: 'var(--color-text-secondary, #737373)' }}>
                {t('disconnectConfirm')}
              </span>
              <button
                type="button"
                onClick={handleDisconnect}
                disabled={isDisconnecting}
                style={{
                  fontSize: '12px',
                  fontWeight: 500,
                  padding: '4px 8px',
                  borderRadius: '8px',
                  color: 'var(--color-text-danger, #dc2626)',
                  background: 'rgba(220, 38, 38, 0.1)',
                  border: 'none',
                  cursor: isDisconnecting ? 'not-allowed' : 'pointer',
                  opacity: isDisconnecting ? 0.6 : 1,
                }}
                aria-label={t('disconnectYes')}
              >
                {isDisconnecting ? '...' : t('disconnectYes')}
              </button>
              <button
                type="button"
                onClick={() => setShowDisconnectConfirm(false)}
                disabled={isDisconnecting}
                style={{
                  fontSize: '12px',
                  fontWeight: 500,
                  padding: '4px 8px',
                  borderRadius: '8px',
                  color: 'var(--color-text-secondary, #737373)',
                  background: 'var(--color-background-secondary, #f9f9f9)',
                  border: 'none',
                  cursor: 'pointer',
                }}
                aria-label={t('disconnectNo')}
              >
                {t('disconnectNo')}
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShowDisconnectConfirm(true)}
              disabled={isRefreshing}
              style={{
                fontSize: '12px',
                fontWeight: 500,
                padding: '4px 12px',
                borderRadius: '8px',
                color: 'var(--color-text-danger, #dc2626)',
                background: 'rgba(220, 38, 38, 0.1)',
                border: 'none',
                cursor: 'pointer',
              }}
              aria-label={t('disconnect')}
            >
              {t('disconnect')}
            </button>
          )
        ) : awaitingOAuth ? (
          <button
            type="button"
            onClick={handleCheckStatus}
            disabled={isRefreshing}
            style={{
              fontSize: '12px',
              fontWeight: 500,
              padding: '4px 12px',
              borderRadius: '8px',
              color: 'var(--color-text-info, #2563eb)',
              background: 'rgba(37, 99, 235, 0.1)',
              border: 'none',
              cursor: 'pointer',
              opacity: isRefreshing ? 0.6 : 1,
            }}
            aria-label={t('checkStatus')}
          >
            {isRefreshing ? t('checking') : t('checkStatus')}
          </button>
        ) : (
          <button
            type="button"
            onClick={handleConnect}
            disabled={isConnecting || isRefreshing}
            style={{
              fontSize: '12px',
              fontWeight: 500,
              padding: '4px 12px',
              borderRadius: '8px',
              color: 'var(--color-text-info, #2563eb)',
              background: 'rgba(37, 99, 235, 0.1)',
              border: 'none',
              cursor: 'pointer',
              opacity: (isConnecting || isRefreshing) ? 0.6 : 1,
            }}
            aria-label={t('connect')}
          >
            {isConnecting ? t('connecting') : t('connect')}
          </button>
        )}
      </div>

      {/* V7: Instruction when connected - inside same section */}
      {connected && (
        <div
          style={{
            borderRadius: '8px',
            padding: '10px 12px',
            marginTop: '12px',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '8px',
            background: 'var(--color-background-secondary, #f9f9f9)',
          }}
        >
          <svg
            style={{
              width: '14px',
              height: '14px',
              flexShrink: 0,
              marginTop: '2px',
              color: 'var(--color-text-tertiary, #8c8c8c)',
            }}
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            aria-hidden="true"
          >
            <rect x="2" y="3" width="12" height="11" rx="1.5" />
            <path d="M5 1.5v3M11 1.5v3M2 7h12" />
          </svg>
          <p style={{ fontSize: '12px', lineHeight: 1.5, color: 'var(--color-text-secondary, #737373)' }}>
            {t('calendarInstructionPrefix')}{' '}
            <strong style={{ color: 'var(--color-text-primary, #0d0d0d)' }}>P1</strong>,{' '}
            <strong style={{ color: 'var(--color-text-primary, #0d0d0d)' }}>P2</strong>,{' '}
            {t('calendarInstructionOr')}{' '}
            <strong style={{ color: 'var(--color-text-primary, #0d0d0d)' }}>P3</strong>{' '}
            {t('calendarInstructionSuffix')}
          </p>
        </div>
      )}

      {/* OAuth awaiting message */}
      {awaitingOAuth && !connected && (
        <div
          style={{
            borderRadius: '8px',
            padding: '10px 12px',
            marginTop: '12px',
            background: 'var(--color-background-secondary, #f9f9f9)',
          }}
        >
          <p style={{ fontSize: '12px', color: 'var(--color-text-secondary, #737373)' }}>
            {t('awaitingOAuth')}
          </p>
        </div>
      )}

      {/* Error message */}
      {error && (
        <div
          style={{
            borderRadius: '8px',
            padding: '10px 12px',
            marginTop: '12px',
            background: 'rgba(220, 38, 38, 0.1)',
            border: '1px solid rgba(220, 38, 38, 0.3)',
          }}
          role="alert"
        >
          <p style={{ fontSize: '12px', color: 'var(--color-text-danger, #dc2626)' }}>{error}</p>
        </div>
      )}
    </section>
  )
}
