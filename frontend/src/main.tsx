import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { isUnreachable, setSignedOutHandler } from './api/client'
import App from './App'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      refetchOnWindowFocus: true,
      // Keep retrying (with backoff) while the backend is down so the page reconnects by itself.
      retry: (failures, error) => isUnreachable(error) || failures < 1,
    },
  },
})

// The session ended (expired, or signed out in another tab): ask who we are again, which shows the sign-in page.
setSignedOutHandler(() => void queryClient.invalidateQueries({ queryKey: ['me'] }))

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
