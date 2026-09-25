import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/fonts.css'
import './styles/tokens.css'
import './styles/base.css'
import './styles/hero.css'
import './styles/toast.css'
import './styles/settings.css'
import './styles/notifications.css'
import App from './App'

// PWA: manifest + service worker, resolved against the deploy base (/ or /Dexter/).
const base = import.meta.env.BASE_URL
const manifest = document.createElement('link')
manifest.rel = 'manifest'
manifest.href = `${base}manifest.webmanifest`
document.head.appendChild(manifest)
const icon = document.createElement('link')
icon.rel = 'icon'
icon.href = `${base}icon.svg`
document.head.appendChild(icon)
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register(`${base}sw.js`, { scope: base }).catch(() => { /* PWA is optional */ })
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
