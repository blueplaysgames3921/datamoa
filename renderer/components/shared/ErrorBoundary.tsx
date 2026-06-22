import { Component, ErrorInfo, ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  error: Error | null
  errorInfo: ErrorInfo | null
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { error: null, errorInfo: null }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ error, errorInfo })
    console.error('[ErrorBoundary]', error, errorInfo)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex flex-col items-center justify-center h-full bg-surface-0 p-8">
          <div className="max-w-lg w-full">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-8 h-8 rounded-lg bg-red-500/20 border border-red-500/30 flex items-center justify-center">
                <span className="text-accent-red text-sm">✗</span>
              </div>
              <div>
                <div className="text-sm font-semibold text-text-primary">Something went wrong</div>
                <div className="text-xs text-text-muted mt-0.5">
                  {this.state.error.message}
                </div>
              </div>
            </div>

            <details className="mb-4">
              <summary className="text-xs text-text-muted cursor-pointer hover:text-text-secondary mb-2">
                Stack trace
              </summary>
              <pre className="text-[10px] font-mono text-text-muted bg-surface-2 rounded border border-border-subtle p-3 overflow-auto max-h-48 whitespace-pre-wrap">
                {this.state.error.stack}
                {this.state.errorInfo?.componentStack}
              </pre>
            </details>

            <button
              onClick={() => this.setState({ error: null, errorInfo: null })}
              className="px-4 py-2 bg-accent-blue text-white text-xs rounded hover:bg-blue-500 transition-colors"
            >
              Try Again
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
