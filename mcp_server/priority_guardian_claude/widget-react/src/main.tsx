import './main.css'
import { createRoot } from 'react-dom/client'
import { Component, type ReactNode, type ErrorInfo } from 'react'
import App from './App'

/**
 * Error Boundary to catch React rendering errors.
 * Prevents entire widget from crashing on component errors.
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
    console.error('PG Claude widget error:', error, errorInfo.componentStack)
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: '24px',
          textAlign: 'center',
          background: 'var(--color-background-secondary, #f9f9f9)',
          borderRadius: '12px',
          fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
        }}>
          <p style={{ fontSize: '14px', color: 'var(--color-text-danger, #dc2626)', fontWeight: 600, marginBottom: '8px' }}>
            Dashboard unavailable
          </p>
          <p style={{ fontSize: '12px', color: 'var(--color-text-secondary, #5c5c5c)' }}>
            Please refresh to try again.
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
  console.error('PG Claude widget: #root element not found in DOM')
} else {
  createRoot(rootElement).render(
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  )
}
