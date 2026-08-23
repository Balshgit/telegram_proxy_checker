import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
// Общие стили подключаются до страничных, чтобы страницы могли их переопределять.
import './shared/ui/ui.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
