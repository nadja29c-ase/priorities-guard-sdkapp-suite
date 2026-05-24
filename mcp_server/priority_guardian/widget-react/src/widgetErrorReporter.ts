/**
 * Widget Error Reporter — sends crash reports to backend for Better Stack ingestion.
 *
 * Fire-and-forget, never throws, never blocks render.
 * Client-side caps prevent abuse: 10 reports/session, dedup by name+message.
 */

const WIDGET_ERROR_ENDPOINT =
  'https://priorities-guard-sdkapp-suite.onrender.com/api/priority-guardian/widget-error'

// Per-session caps
const MAX_REPORTS_PER_SESSION = 10
let errorCount = 0
const seenErrors = new Set<string>()

/**
 * Payload shape matching backend WidgetErrorReport Pydantic model.
 */
export interface WidgetErrorPayload {
  name?: string | null
  message?: string | null
  stack?: string | null
  componentStack?: string | null
  ua?: string
}

/**
 * Truncate a string to maxLength characters.
 */
function truncate(value: string | null | undefined, maxLength: number): string | null {
  if (value == null) return null
  return value.length > maxLength ? value.slice(0, maxLength) : value
}

/**
 * Report a widget error to the backend.
 *
 * - Fire-and-forget: async but callers should not await
 * - Silent failure: never throws, never logs on failure
 * - Respects per-session cap (10 reports) and dedup (same name+message)
 * - Truncates stack/componentStack to 2000 chars each
 */
export async function reportWidgetError(payload: WidgetErrorPayload): Promise<void> {
  try {
    // Deduplication: skip if we've seen this name+message combo
    const dedupKey = `${payload.name ?? ''}|${payload.message ?? ''}`
    if (seenErrors.has(dedupKey)) {
      return
    }

    // Per-session cap: stop after 10 reports
    if (errorCount >= MAX_REPORTS_PER_SESSION) {
      return
    }

    // Record this error
    seenErrors.add(dedupKey)
    errorCount++

    // Build payload with truncation
    const body = {
      name: payload.name ?? undefined,
      message: payload.message ?? undefined,
      stack: truncate(payload.stack, 2000) ?? undefined,
      componentStack: truncate(payload.componentStack, 2000) ?? undefined,
      ua: payload.ua ?? (typeof navigator !== 'undefined' ? navigator.userAgent : undefined),
    }

    await fetch(WIDGET_ERROR_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      keepalive: true,
    })
  } catch {
    // Silent failure — we already have the error in the boundary/console
  }
}

// ============ Diagnostic Reporter (Inc 89 / 89.8) ============
// Temporary — remove after fullscreen flash-revert bug is diagnosed.
//
// Inc 89.8: routes through window.openai.callTool() instead of fetch().
// Browser CSP blocks direct widget->backend HTTP calls (Issue #85), so we
// invoke a private MCP tool which the host runs server-side, bypassing
// iframe CSP entirely.

const MAX_DIAGNOSTIC_EVENTS_PER_SESSION = 20
let diagnosticCount = 0

export interface WidgetDiagnosticPayload {
  event: string
  data?: Record<string, unknown>
}

interface OpenAIHostWithCallTool {
  callTool?: (name: string, args: Record<string, unknown>) => Promise<unknown>
}

export async function reportWidgetDiagnostic(payload: WidgetDiagnosticPayload): Promise<void> {
  try {
    if (diagnosticCount >= MAX_DIAGNOSTIC_EVENTS_PER_SESSION) return
    diagnosticCount++

    const host = (typeof window !== 'undefined'
      ? (window.openai as OpenAIHostWithCallTool | undefined)
      : undefined)

    if (!host?.callTool) return  // No host bridge available — silent skip

    await host.callTool('record_widget_diagnostic', {
      event: payload.event,
      data: payload.data ?? {},
      ts: Date.now(),
      ua: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
    })
  } catch {
    // Silent failure — diagnostic must never break the widget
  }
}

/**
 * Reset reporter state for testing. Internal use only.
 */
export function __resetReporterStateForTesting(): void {
  errorCount = 0
  seenErrors.clear()
  diagnosticCount = 0  // Inc 89
}
