import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the FastAPI backend runs on :8000; Vite proxies API calls to it.
// In production FastAPI serves the built files from frontend/dist on the same origin.
const BACKEND = process.env.CONTEXTAI_BACKEND ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    proxy: {
      '/api': BACKEND,
      '/health': BACKEND,
    },
  },
})
