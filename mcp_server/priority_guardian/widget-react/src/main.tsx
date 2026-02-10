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
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="p-6 text-center bg-surface-secondary rounded-xl">
          <p className="text-sm text-danger font-medium mb-2">Something went wrong</p>
          <p className="text-xs text-secondary">
            Unable to display dashboard. Please refresh or try again later.
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
