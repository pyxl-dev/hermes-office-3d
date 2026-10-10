import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    // emitted into the existing Python server's static root, served at /pixel/
    outDir: '../web/pixel',
    emptyOutDir: true,
    target: 'es2020',
    // avoid an inline module-preload polyfill so the strict CSP (script-src 'self') holds
    modulePreload: { polyfill: false },
    assetsInlineLimit: 0,
  },
  base: '/pixel/',
})
