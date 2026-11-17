import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// npm run dev: giao diện ở 5173, gọi /api sang backend 8600. npm run build: ra dist/, backend phục vụ luôn.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8600' } },
  build: { outDir: 'dist', chunkSizeWarningLimit: 900 },
})
