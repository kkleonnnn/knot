import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { installErrorReporter } from './error_reporter.js'

// v0.6.0.4 F-B: 全局 JS 错误 + Promise rejection 自动上报到 /api/frontend-errors
// throttle/dedupe 在 error_reporter.js 内部（守护者 M-B1 立约）
installErrorReporter()

createRoot(document.getElementById('root')).render(<App />)
