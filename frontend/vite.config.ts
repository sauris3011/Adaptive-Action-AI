import { defineConfig, type ProxyOptions } from 'vite'
import react from '@vitejs/plugin-react'

const BACKEND = 'http://127.0.0.1:8787'

/* The backend is a separate process, so it can be absent while the UI is up:
   it is restarted by hand during a session, and it takes a few seconds to boot.
   Vite answers a dead upstream with an empty 500, which reaches the operator as
   a bare "HTTP 500" that says nothing about which half of the stack is down.

   configure() runs before Vite installs its own error handler, so this one gets
   there first and Vite's finds the headers already sent and leaves the body
   alone. That makes the reply a 503 - the honest status for an upstream that is
   not there - carrying the `detail` field api.ts turns into the shown message.

   The startup scripts wait for /health before launching Vite, so this should
   only ever fire on a backend that goes away mid-session. */
const backend: ProxyOptions = {
  target: BACKEND,
  changeOrigin: true,
  configure: (proxy) => {
    proxy.on('error', (err, _req, res) => {
      /* A websocket upgrade hands back a raw socket with no response to write. */
      if (!('writeHead' in res) || res.headersSent || res.writableEnded) return
      const reason = (err as Error & { code?: string }).code ?? err.message
      res.writeHead(503, { 'Content-Type': 'application/json' })
      res.end(
        JSON.stringify({
          detail: `Cannot reach the backend at ${BACKEND} (${reason}). Is it running?`,
        }),
      )
    })
  },
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    // The UI never calls the LLM gateway directly (master prompt section 2).
    // Everything goes through the backend on an unprivileged port.
    proxy: {
      '/api': backend,
      '/health': backend,
    },
  },
})
