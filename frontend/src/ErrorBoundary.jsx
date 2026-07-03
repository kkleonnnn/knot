// v0.7.33 (B1.1) — React ErrorBoundary（白屏爆炸半径收敛）
// 两层：AppErrorBoundary（main.jsx 包 <App/>，全屏降级）+ ResultBlockErrorBoundary（单 block inline 降级）。
// componentDidCatch → error_reporter.reportError（复用节流/去重 pipeline，M-B1 契约）。
//
// ⚠️ 铁律（守护者 R1）：React **不 catch fallback render 自身抛的错**。AppErrorBoundary 是最顶层
// 无上级 boundary → 其 fallback 必须 **bulletproof**：纯 inline（buildTheme 纯 POJO + TOKENS_V2 const
// + raw <button>/<svg>），**不用 primitives.Btn / 不碰任何可崩组件**（防崩溃源在 Shared/primitives 时连环抛）。
// ResultBlockErrorBoundary 的 fallback 可宽松（AppErrorBoundary 兜底它）。
import { Component } from 'react';
import { buildTheme, TOKENS_V2 } from './Shared.jsx';
import { reportError } from './error_reporter.js';

// raw 三角警告 path（0 碰 frozen Shared.jsx I dict；同 ResultBlock RB_SVG one-off 先例）
const _TRIANGLE = 'M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z';

function _report(tag, error, info) {
  try {
    reportError(`[${tag}] ` + (error?.message || 'render crash'),
                (error?.stack || '') + '\n' + (info?.componentStack || ''));
  } catch { /* reporter 绝不可反过来炸 boundary */ }
}


export class AppErrorBoundary extends Component {
  state = { crashed: false };
  static getDerivedStateFromError() { return { crashed: true }; }
  componentDidCatch(error, info) { _report('AppErrorBoundary', error, info); }

  render() {
    if (!this.state.crashed) return this.props.children;
    // class 组件无 useTheme hook → 自读 cb_theme（镜像 utils.useTheme 默认：缺失/畸形 → dark）
    const saved = localStorage.getItem('cb_theme');
    const dark = saved ? saved === 'dark' : true;
    let T;
    try {
      T = buildTheme(dark);
    } catch {
      T = { bg: '#080a0e', card: '#11151b', border: 'rgba(255,255,255,0.08)', text: '#e8edf3',
            subtext: '#8c97a4', accent: '#2dd4bf', sendFg: '#062a30', sans: 'system-ui, sans-serif' };
    }
    const err = (TOKENS_V2 && TOKENS_V2.err) || 'oklch(66% 0.20 25)';
    return (
      <div style={{ position: 'fixed', inset: 0, background: T.bg, display: 'flex',
                    alignItems: 'center', justifyContent: 'center', padding: 24,
                    fontFamily: T.sans, zIndex: 99999 }}>
        <div style={{ maxWidth: 420, width: '100%', background: T.card,
                      border: `1px solid ${T.border}`, borderRadius: 14,
                      padding: '32px 28px', textAlign: 'center' }}>
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke={err}
               strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"
               style={{ margin: '0 auto 16px', display: 'block' }}>
            <path d={_TRIANGLE}/>
            <line x1="12" y1="9" x2="12" y2="13"/>
            <line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          <div style={{ fontSize: 17, fontWeight: 600, color: T.text, marginBottom: 8 }}>页面遇到错误</div>
          <div style={{ fontSize: 13, color: T.subtext, lineHeight: 1.6, marginBottom: 20 }}>
            界面渲染出现异常，已自动记录。刷新页面通常即可恢复。
          </div>
          <button onClick={() => window.location.reload()}
                  style={{ height: 40, padding: '0 20px', border: 'none', borderRadius: 8,
                           cursor: 'pointer', background: T.accent, color: T.sendFg || '#062a30',
                           fontSize: 14, fontWeight: 500, fontFamily: T.sans }}>
            刷新页面
          </button>
        </div>
      </div>
    );
  }
}


export class ResultBlockErrorBoundary extends Component {
  state = { crashed: false };
  static getDerivedStateFromError() { return { crashed: true }; }
  componentDidCatch(error, info) { _report('ResultBlockErrorBoundary', error, info); }

  render() {
    if (!this.state.crashed) return this.props.children;
    const T = this.props.T || {};
    const err = (TOKENS_V2 && TOKENS_V2.err) || 'oklch(66% 0.20 25)';
    // inline 降级卡（仿 ErrorBanner 风格；崩溃隔离单 msg，siblings + composer 存活）
    return (
      <div style={{ padding: '10px 14px', borderRadius: 10, background: T.card,
                    border: `1px solid ${err}`, color: err, fontSize: 12.5,
                    fontFamily: T.sans, display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={err}
             strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: 1 }}>
          <path d={_TRIANGLE}/>
          <line x1="12" y1="9" x2="12" y2="13"/>
          <line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 500, marginBottom: 2 }}>此结果渲染出错</div>
          <div style={{ opacity: 0.85, color: T.subtext || err }}>
            该条结果显示异常（已记录），其余对话不受影响。刷新页面可重试。
          </div>
        </div>
      </div>
    );
  }
}
