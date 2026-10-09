import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ErrorBoundary } from './ErrorBoundary'

let shouldThrow = true
function Flaky() {
  if (shouldThrow) throw new Error('boom')
  return <p>page content</p>
}

describe('ErrorBoundary', () => {
  it('shows a message instead of a blank page, and recovers on retry', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ErrorBoundary>
        <Flaky />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Something broke')
    expect(screen.getByText('boom')).toBeInTheDocument()

    shouldThrow = false
    fireEvent.click(screen.getByText('Try again'))
    expect(screen.getByText('page content')).toBeInTheDocument()
  })
})
