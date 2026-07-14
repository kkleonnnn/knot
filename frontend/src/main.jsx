import { createRoot } from 'react-dom/client'
// v0.9.1 type system：自托管真字体（治“雅黑小作坊味”：之前 index.html 零字体引入，Windows 全线回退）
// Inter var（英/数）+ Noto Sans SC 400/500/700（中，unicode-range 分包按需加载）+ JetBrains Mono var（仅数据）
// ※ MiSans 无 npm 官包；若要换 MiSans，woff2 放 src/assets/fonts 自写 @font-face，栈内 'MiSans VF' 已预留在 Noto 前
import '@fontsource-variable/inter'
import '@fontsource/noto-sans-sc/chinese-simplified-400.css'
import '@fontsource/noto-sans-sc/chinese-simplified-500.css'
import '@fontsource/noto-sans-sc/chinese-simplified-700.css'
import '@fontsource-variable/jetbrains-mono'
import './index.css'
import App from './App.jsx'
import { AppErrorBoundary } from './ErrorBoundary.jsx'
import { ConfirmHost } from './utils.jsx'  // v0.9.3 玻璃确认框宿主（替代 window.confirm）
import { installErrorReporter } from './error_reporter.js'

// v0.6.0.4 F-B: 全局 JS 错误 + Promise rejection 自动上报到 /api/frontend-errors
// throttle/dedupe 在 error_reporter.js 内部（守护者 M-B1 立约）
installErrorReporter()

// v0.7.33 (B1.1): AppErrorBoundary 兜底 render 崩溃（白屏 → 全屏降级可重试）
createRoot(document.getElementById('root')).render(
  <AppErrorBoundary><App /><ConfirmHost /></AppErrorBoundary>
)
