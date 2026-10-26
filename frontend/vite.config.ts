import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dashboard calls /api/...; Vite forwards those requests to the FastAPI backend on port 8765.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8765' },
  },
})
