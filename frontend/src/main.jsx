import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.scss'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import { SitesProvider } from './context/SitesContext.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary>
      <SitesProvider>
        <App />
      </SitesProvider>
    </ErrorBoundary>
  </StrictMode>,
)
