// RightPanel.jsx — v0.8.5 ②a 共享右栏 chrome（BI da-asst「数据分析」+ ASK「思考过程」共用）。
// kk 根因修 #4：右栏是一个共享组件 —— 同宽(320) / 同表头(纯文字标题 12/600 + 可选 trailing + 同位 » 收起键) /
// 同收起 rail(52px)；只换内部内容。无前置 sparkle 图标。收起状态自管理（内部 useState）。
import { useState } from 'react';

export function RightPanel({ T, title, headerTrailing, children }) {
  const [collapsed, setCollapsed] = useState(false);
  if (collapsed) {
    return (
      <button onClick={() => setCollapsed(false)} title={`展开${title}`}
        style={{
          width: 52, flexShrink: 0, alignSelf: 'stretch', border: 'none', borderLeft: `1px solid ${T.border}`,
          background: T.sidebar, color: T.subtext, cursor: 'pointer',
          display: 'grid', placeItems: 'center', fontFamily: T.sans, fontSize: 12,
        }}>
        <span style={{ writingMode: 'vertical-rl', letterSpacing: '0.12em' }}>{title} «</span>
      </button>
    );
  }
  return (
    <aside style={{
      width: 320, flexShrink: 0, height: '100%', borderLeft: `1px solid ${T.border}`,
      background: T.sidebar, display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      <div style={{ padding: '14px 18px', flexShrink: 0, borderBottom: `1px solid ${T.border}`, display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: T.text }}>{title}</span>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
          {headerTrailing}
          <button onClick={() => setCollapsed(true)} title="收起面板"
            style={{ border: 'none', background: 'transparent', color: T.subtext, cursor: 'pointer', fontSize: 16, lineHeight: 0, display: 'grid', placeItems: 'center', padding: 0 }}>»</button>
        </div>
      </div>
      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {children}
      </div>
    </aside>
  );
}
