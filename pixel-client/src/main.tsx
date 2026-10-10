import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { initStandaloneBridge } from './standaloneBridge.js'
import { initHermesBridge } from './hermesBridge.js'

// Served by the Hermes office server at /pixel/ → drive the office from the real
// sanitized API. Anywhere else (e.g. vite dev) → the upstream demo bridge.
const isHermesOffice = window.location.pathname.startsWith('/pixel')

const ready = isHermesOffice ? initHermesBridge() : initStandaloneBridge()

// Initialize the bridge before rendering
ready.then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
