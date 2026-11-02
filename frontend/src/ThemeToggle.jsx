import { useEffect, useState } from 'react'
import './theme.css'

// Share Django Admin's preference, including its system-following "auto" mode.
const storageKey = 'theme'
const systemTheme = () => window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'

function savedTheme() {
  try {
    const value = localStorage.getItem(storageKey)
    return value === 'dark' || value === 'light' ? value : null
  } catch { return null }
}

export default function ThemeToggle() {
  const [preference, setPreference] = useState(savedTheme)
  const [system, setSystem] = useState(systemTheme)
  const theme = preference || system

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const update = event => setSystem(event.matches ? 'dark' : 'light')
    media.addEventListener('change', update)
    const sync = event => { if (event.key === storageKey || event.key === null) setPreference(savedTheme()) }
    window.addEventListener('storage', sync)
    return () => {
      media.removeEventListener('change', update)
      window.removeEventListener('storage', sync)
    }
  }, [])

  useEffect(() => { document.documentElement.dataset.theme = theme }, [theme])

  function toggle() {
    const next = theme === 'dark' ? 'light' : 'dark'
    setPreference(next)
    try { localStorage.setItem(storageKey, next) } catch { /* The choice remains active for this visit. */ }
  }

  const label = theme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему'
  return <button type="button" className="theme-toggle" onClick={toggle} aria-label={label} title={label}>
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {theme === 'dark' ? <><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" /></> : <path d="M20.7 13.2A8.5 8.5 0 0 1 10.8 3.3 8.5 8.5 0 1 0 20.7 13.2Z" />}
    </svg>
  </button>
}
