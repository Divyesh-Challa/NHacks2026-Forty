import basicSsl from '@vitejs/plugin-basic-ssl'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The browser only ever talks to this dev server; /api (HTTP + WebSocket) is proxied to the
// backend. So a phone on the same Wi-Fi works with no config, and HTTPS=1 (self-signed cert)
// gives the secure context that browser Notifications require on a phone.
const BACKEND = process.env.BACKEND_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react(), ...(process.env.HTTPS ? [basicSsl()] : [])],
  server: {
    host: true,
    proxy: {
      '/api': { target: BACKEND, ws: true, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, '') },
    },
  },
})
