import './main.css'
import { createRoot } from 'react-dom/client'
import { Component, type ReactNode, type ErrorInfo } from 'react'
import App from './App'

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
    // DEBUG: store full error info on window for post-crash inspection
    ;(window as Record<string, unknown>).__PG_LAST_ERROR__ = {
      message: error.message,
      name: error.name,
      stack: error.stack,
      componentStack: errorInfo.componentStack,
      ts: new Date().toISOString(),
    }
    // Phone home: POST error to backend so we can see it in Render logs
    // Fire and forget — must not throw
    try {
      fetch('https://priorities-guard-sdkapp-suite.onrender.com/api/priority-guardian/widget-error', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: error?.name ?? null,
          message: error?.message ?? null,
          stack: error?.stack?.slice(0, 800) ?? null,
          componentStack: errorInfo?.componentStack?.slice(0, 400) ?? null,
          ua: navigator?.userAgent ?? null,
        }),
      }).catch(() => {})
    } catch (_) {
      // Never let telemetry throw
    }
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div style={{padding:'24px',textAlign:'center',background:'#f9f9f9',borderRadius:'12px',fontFamily:'system-ui,sans-serif'}}>
          <p style={{fontSize:'14px',color:'#dc2626',fontWeight:600,marginBottom:'8px'}}>Something went wrong</p>
          <p style={{fontSize:'12px',color:'#666',marginBottom:'8px'}}>
            Unable to display dashboard. Please refresh or try again later.
          </p>
          <p style={{fontSize:'11px',color:'#999',wordBreak:'break-all',marginBottom:'4px'}}>
            {this.state.error?.name || 'UnknownError'}: {this.state.error?.message || '(no message)'}
          </p>
          <p style={{fontSize:'10px',color:'#bbb',wordBreak:'break-all'}}>
            {this.state.error?.stack?.split('\n').slice(0,4).join(' | ')}
          </p>
        </div>
      )
    }
    return this.props.children
  }
}

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
