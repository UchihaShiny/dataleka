import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './theme.css'
import { applyTheme, savedTheme } from './format.js'

applyTheme(savedTheme())   // trước lần vẽ đầu: không nháy nền sai

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>)
