import { Component, type ErrorInfo, type ReactNode } from 'react'

/** Catches render crashes so one broken page shows a message instead of a blank screen. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { error: Error | null }> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Page crashed:', error, info.componentStack)
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    // Navigating to another tab clears the error.
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null })
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div role="alert" className="card flex flex-col items-center gap-3 py-10 text-center">
        <h2 className="text-lg font-semibold">Something broke on this page</h2>
        <p className="max-w-md text-sm text-slate-400">
          Your data is fine. Try again or switch tabs.
        </p>
        <code className="max-w-full overflow-x-auto rounded bg-slate-950 px-2 py-1 text-xs text-red-300">
          {this.state.error.message}
        </code>
        <button className="btn-primary" onClick={() => this.setState({ error: null })}>
          Try again
        </button>
      </div>
    )
  }
}
