/**
 * MindSort Claude Widget - Entry Point
 *
 * Mounts the App with ErrorBoundary for crash protection.
 */
import './main.css'
import { createRoot } from 'react-dom/client'
import { Component, type ReactNode, type ErrorInfo } from 'react'
import App from './App'

/**
 * Error Boundary to catch React rendering errors.
 * Surfaces error details to console per mobile-error-exposure requirement.
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
    // Log full error details (name + message + stack + componentStack)
    console.error(
      'MindSort widget error:',
      error.name,
      error.message,
      error.stack,
      errorInfo.componentStack
    )
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: '24px',
          textAlign: 'center',
          background: 'var(--color-background-secondary, #F5F4ED)',
          borderRadius: '12px',
          fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
        }}>
          <p style={{
            fontSize: '14px',
            color: 'var(--color-text-danger, #dc2626)',
            fontWeight: 500,
            marginBottom: '8px',
          }}>
            Widget unavailable
          </p>
          <p style={{
            fontSize: '12px',
            color: 'var(--color-text-secondary, #3D3D3A)',
          }}>
            Please refresh to try again.
          </p>
        </div>
      )
    }
    return this.props.children
  }
}

// Safe root element lookup
const rootElement = document.getElementById('root')
if (!rootElement) {
  console.error('MindSort widget: #root element not found in DOM')
} else {
  createRoot(rootElement).render(
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  )
}
