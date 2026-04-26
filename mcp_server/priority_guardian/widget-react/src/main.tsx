import './main.css'
import { createRoot } from 'react-dom/client'
import { Component, type ReactNode, type ErrorInfo } from 'react'
import App from './App'
import { reportWidgetError } from './widgetErrorReporter'

// Set document language BEFORE React renders (for VoiceOver)
// Must run synchronously before createRoot to ensure correct voice from start
;(() => {
  const rawLocale = ((window as { openai?: { locale?: string } }).openai?.locale ?? 'en').replace(/_/g, '-')
  document.documentElement.lang = rawLocale
})()

/**
 * Error Boundary to catch React rendering errors
 * Prevents entire widget from crashing on component errors
 */
interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

class ErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  constructor(props: { children: ReactNode }) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('PG widget error:', error, errorInfo.componentStack)
    reportWidgetError({
      name: error.name,
      message: error.message,
      stack: error.stack,
      componentStack: errorInfo.componentStack ?? undefined,
    })
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div style={{padding:'24px',textAlign:'center',background:'var(--color-surface-secondary)',borderRadius:'12px',fontFamily:'var(--font-sans)'}}>
          <p style={{fontSize:'14px',color:'var(--color-text-danger)',fontWeight:600,marginBottom:'8px'}}>Dashboard unavailable</p>
          <p style={{fontSize:'12px',color:'var(--color-text-secondary)',marginBottom:'8px'}}>
            Please refresh to try again.
          </p>
          <p style={{fontSize:'11px',color:'var(--color-text-tertiary)',wordBreak:'break-all',marginBottom:'4px'}}>
            {this.state.error?.name || 'UnknownError'}: {this.state.error?.message || '(no message)'}
          </p>
          <p style={{fontSize:'10px',color:'var(--color-text-tertiary)',wordBreak:'break-all'}}>
            {this.state.error?.stack?.split('\n').slice(0,4).join(' | ')}
          </p>
        </div>
      )
    }
    return this.props.children
  }
}

// Global error handlers — catch errors outside React's tree
window.addEventListener('error', (event: ErrorEvent) => {
  const error = event.error
  if (error instanceof Error) {
    reportWidgetError({
      name: error.name,
      message: error.message,
      stack: error.stack,
    })
  } else {
    reportWidgetError({
      message: event.message || 'Unknown window error',
      stack: null,
    })
  }
})

window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
  const reason = event.reason
  if (reason instanceof Error) {
    reportWidgetError({
      name: reason.name,
      message: reason.message,
      stack: reason.stack,
    })
  } else {
    reportWidgetError({
      message: String(reason),
      stack: null,
    })
  }
})

// Safe root element lookup with fallback
const rootElement = document.getElementById('root')
if (!rootElement) {
  console.error('PG widget: #root element not found in DOM')
} else {
  createRoot(rootElement).render(
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  )
}

// Test-only export
export { ErrorBoundary as __ErrorBoundaryForTesting }
