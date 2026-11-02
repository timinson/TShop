import { installNavigation } from './navigation'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

const uninstallNavigation = installNavigation()
if (import.meta.hot) import.meta.hot.dispose(uninstallNavigation)

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
