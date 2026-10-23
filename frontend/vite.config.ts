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
  build: {
    // The lazily-loaded markdown chunk (highlight.js + KaTeX) is ~180 KB gzipped by design
    chunkSizeWarningLimit: 650,
    rolldownOptions: {
      output: {
        // Long-lived vendor chunks: shipping an app change doesn't re-download React or the UI kit.
        // Markdown/highlighting/math stay in their own lazily-loaded chunk.
        codeSplitting: {
          groups: [
            { name: "react", test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/, priority: 3 },
            { name: "router", test: /node_modules[\\/]react-router[\\/]/, priority: 2 },
            {
              name: "ui",
              test: /node_modules[\\/](@radix-ui|radix-ui|@floating-ui|sonner|lucide-react|tailwind-merge|clsx|class-variance-authority|next-themes|zustand)[\\/]/,
              priority: 1,
            },
          ],
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': BACKEND,
      '/health': BACKEND,
    },
  },
})
