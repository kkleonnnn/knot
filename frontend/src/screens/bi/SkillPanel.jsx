// SkillPanel.jsx — v0.8.5 (②a) BI 右栏 da-asst 数据分析面板（复刻 artboard chat UI 壳）。
// ⚠️ 本轮「先复刻 UI」：聊天区为**示例/静态**，真·skill 接入 = ③（da-asst 嵌入形态最大设计决策）。
// 缩进/展开（点 3 形态）。回复占位，不发真请求。
import { useState } from 'react';

const SUGGESTIONS = ['解读今日盈亏波动', '对比上周同期', '哪个品种贡献最大'];

function Bubble({ T, role, children }) {
  const me = role === 'user';
  return (
    <div style={{ display: 'flex', justifyContent: me ? 'flex-end' : 'flex-start', marginBottom: 12 }}>
      <div style={{
        maxWidth: '86%', padding: '9px 12px', borderRadius: 12, fontSize: 12.5, lineHeight: 1.6,
        whiteSpace: 'pre-wrap',
        background: me ? T.accent : T.chipBg, color: me ? T.sendFg : T.text,
        border: me ? 'none' : `1px solid ${T.border}`,
      }}>{children}</div>
    </div>
  );
}

export function SkillPanel({ T, report, collapsed, onToggle }) {
  const [q, setQ] = useState('');
  if (collapsed) {
    return (
      <button onClick={onToggle} title="展开数据分析"
        style={{
          width: 34, flexShrink: 0, alignSelf: 'stretch', border: `1px solid ${T.border}`,
          borderRadius: 14, background: T.content, color: T.subtext, cursor: 'pointer',
          display: 'grid', placeItems: 'center', fontFamily: T.sans, fontSize: 12,
        }}>
        <span style={{ writingMode: 'vertical-rl', letterSpacing: '0.12em' }}>数据分析 «</span>
      </button>
    );
  }
  const ctx = report ? report.title : '当前报表';
  return (
    <aside style={{
      width: 316, flexShrink: 0, border: `1px solid ${T.border}`, borderRadius: 14,
      background: T.content, display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      <div style={{ height: 56, padding: '0 18px', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: `1px solid ${T.border}` }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 14, fontWeight: 600, color: T.text }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={T.accent} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M5 3v4M3 5h4M6 17v4M4 19h4M13 3l2.5 6.5L22 12l-6.5 2.5L13 21l-2.5-6.5L4 12l6.5-2.5z" /></svg>
          数据分析
        </span>
        <button onClick={onToggle} title="收起面板" style={{ border: 'none', background: 'transparent', color: T.subtext, cursor: 'pointer', fontSize: 16 }}>»</button>
      </div>

      <div className="cb-sb" style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '16px 16px 0' }}>
        <div style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono, letterSpacing: '0.05em', marginBottom: 14, textAlign: 'center' }}>示例预览 · da-asst 即将接入（③）</div>
        <Bubble T={T} role="assistant">我是数据分析助手（da-asst），可以帮你解读「{ctx}」。想先看哪块？</Bubble>
        <Bubble T={T} role="user">今天手续费收入为什么涨这么多？</Bubble>
        <Bubble T={T} role="assistant">{'今日手续费收入 ¥893 万，环比 +18.4%，主要来自两块：\n① BTC 永续合约交易量 +24%，约贡献 ¥410 万；\n② SOL 永续新上线首日活跃，约贡献 ¥120 万。\n资金费率部分基本持平。'}</Bubble>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 9px', borderRadius: 7, background: T.accentSoft, color: T.accent, fontSize: 11, marginBottom: 12 }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" /></svg>
          {ctx}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => setQ(s)} style={{ padding: '5px 10px', borderRadius: 7, border: `1px solid ${T.border}`, background: 'transparent', color: T.subtext, fontSize: 11.5, cursor: 'pointer', fontFamily: 'inherit' }}>{s}</button>
          ))}
        </div>
      </div>

      <div style={{ padding: '10px 14px', borderTop: `1px solid ${T.border}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <textarea value={q} onChange={(e) => setQ(e.target.value)} rows={1} placeholder="追问这份报表…（da-asst 即将上线）"
            style={{ flex: 1, resize: 'none', background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 9, padding: '8px 11px', fontSize: 12.5, color: T.text, fontFamily: 'inherit' }} />
          <button title="即将上线（③）" disabled style={{ width: 34, height: 34, flexShrink: 0, borderRadius: 9, border: 'none', background: T.accent, color: T.sendFg, opacity: 0.5, cursor: 'default', display: 'grid', placeItems: 'center' }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4z" /></svg>
          </button>
        </div>
        <div style={{ marginTop: 8, fontSize: 11, color: T.muted, textAlign: 'center' }}>● 仅解读 · 不改写报表</div>
      </div>
    </aside>
  );
}
