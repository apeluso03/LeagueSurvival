/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Bind to IPv4 explicitly: on Windows "localhost" can resolve to IPv6 only, which some browsers can't reach.
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': process.env.API_URL ?? 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
})
