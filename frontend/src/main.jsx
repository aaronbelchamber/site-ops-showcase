import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.scss'
import App from './App.jsx'
import { SitesProvider } from './context/SitesContext.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <SitesProvider>
      <App />
    </SitesProvider>
  </StrictMode>,
)
