import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { initStandaloneBridge } from './standaloneBridge.js'
import { initHermesBridge } from './hermesBridge.js'

// Served by the Hermes office server at /pixel/ → drive the office from the real
// sanitized API. Anywhere else (e.g. vite dev) → the upstream demo bridge.
// In a production build this bundle is only ever served by the Hermes office
// server, so the real bridge is always correct. Vite dev (import.meta.env.DEV)
// must use the upstream demo bridge even though its URL also starts with /pixel/.
const isHermesOffice = !import.meta.env.DEV

const ready = isHermesOffice ? initHermesBridge() : initStandaloneBridge()

// Initialize the bridge before rendering
ready.then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
