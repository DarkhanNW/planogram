import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the UI calls the service directly through this proxy.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: process.env.PLANOGRAM_API_URL ?? 'http://localhost:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
