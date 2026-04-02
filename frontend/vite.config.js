import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/agents': 'http://localhost:8000',
      '/tasks': 'http://localhost:8000',
      '/status': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
