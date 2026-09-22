import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/andika';
import '@fontsource/andika/700.css'; 
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
