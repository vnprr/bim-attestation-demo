import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The backend serves /api on :8080 (solana-test-validator occupies ports from 8000 up).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8080' } },
})
