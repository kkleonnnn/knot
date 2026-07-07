// SkillPanel.jsx — v0.8.5 (②a) BI 右栏 da-asst 数据分析面板（handoff 定稿：满高 flex 列 + 卡片式 composer）。
// ⚠️ 本轮「先复刻 UI」：聊天区为**示例/静态**，真·skill 接入 = ③（da-asst 嵌入形态最大设计决策）。
// 结构：头部 → 消息区(flex:1 滚动) → 建议 chip 行 → 卡片 composer。整块在主面板内，仅一条 border-left（非浮层）。
import { useState } from 'react';
import { toast } from '../../utils.jsx';

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

// 建议 chip —— pill 形，hover → accent 描边+字色（handoff §3）
function Chip({ T, label, onClick }) {
  const [hover, setHover] = useState(false);
  return (
    <button onClick={onClick} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        padding: '5px 11px', borderRadius: 999, fontSize: 11.5, cursor: 'pointer', fontFamily: 'inherit',
        border: `1px solid ${hover ? T.accent : T.border}`, background: 'transparent',
        color: hover ? T.accent : T.subtext, transition: 'color 120ms, border-color 120ms',
      }}>{label}</button>
  );
}

export function SkillPanel({ T, report, collapsed, onToggle }) {
  const [q, setQ] = useState('');
  if (collapsed) {
    return (
      <button onClick={onToggle} title="展开数据分析"
        style={{
          width: 52, flexShrink: 0, alignSelf: 'stretch', border: 'none', borderLeft: `1px solid ${T.border}`,
          background: T.content, color: T.subtext, cursor: 'pointer',
          display: 'grid', placeItems: 'center', fontFamily: T.sans, fontSize: 12,
        }}>
        <span style={{ writingMode: 'vertical-rl', letterSpacing: '0.12em' }}>数据分析 «</span>
      </button>
    );
  }
  const ctx = report ? report.title : '当前报表';
  return (
    <aside style={{
      width: 352, flexShrink: 0, borderLeft: `1px solid ${T.border}`,
      background: T.content, display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      {/* 头部 */}
      <div style={{ height: 56, padding: '0 18px', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: `1px solid ${T.border}` }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 14, fontWeight: 600, color: T.text }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={T.accent} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M5 3v4M3 5h4M6 17v4M4 19h4M13 3l2.5 6.5L22 12l-6.5 2.5L13 21l-2.5-6.5L4 12l6.5-2.5z" /></svg>
          数据分析
        </span>
        <button onClick={onToggle} title="收起面板" style={{ border: 'none', background: 'transparent', color: T.subtext, cursor: 'pointer', fontSize: 16 }}>»</button>
      </div>

      {/* 消息区（flex:1 滚动）*/}
      <div className="cb-sb" style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '16px 16px 4px' }}>
        <div style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono, letterSpacing: '0.05em', marginBottom: 14, textAlign: 'center' }}>示例预览 · da-asst 即将接入（③）</div>
        <Bubble T={T} role="assistant">我是数据分析助手（da-asst），可以帮你解读「{ctx}」。想先看哪块？</Bubble>
        <Bubble T={T} role="user">今天手续费收入为什么涨这么多？</Bubble>
        <Bubble T={T} role="assistant">{'今日手续费收入 ¥893 万，环比 +18.4%，主要来自两块：\n① BTC 永续合约交易量 +24%，约贡献 ¥410 万；\n② SOL 永续新上线首日活跃，约贡献 ¥120 万。\n资金费率部分基本持平。'}</Bubble>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 9px', borderRadius: 7, background: T.accentSoft, color: T.accent, fontSize: 11 }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" /></svg>
          {ctx}
        </div>
      </div>

      {/* 底部：建议 chip 行 + 卡片 composer */}
      <div style={{ padding: '12px 14px', borderTop: `1px solid ${T.border}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
          {SUGGESTIONS.map((s) => <Chip key={s} T={T} label={s} onClick={() => setQ(s)} />)}
        </div>
        <div style={{ background: T.content, border: `1px solid ${T.inputBorder}`, borderRadius: 12, padding: '11px 12px' }}>
          <textarea value={q} onChange={(e) => setQ(e.target.value)} rows={2} placeholder="追问这份报表…"
            style={{ width: '100%', resize: 'none', background: 'transparent', border: 'none', outline: 'none', color: T.text, fontSize: 12.5, fontFamily: 'inherit', lineHeight: 1.55, padding: 0 }} />
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 8 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: T.mono, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.04em', color: T.muted }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.accent, flexShrink: 0 }} />
              仅解读 · 不改写报表
            </span>
            <button onClick={() => toast('da-asst 即将接入（③）')} title="da-asst 即将接入（③）"
              style={{ width: 30, height: 30, flexShrink: 0, borderRadius: 8, border: 'none', background: T.accent, color: T.sendFg, cursor: 'pointer', display: 'grid', placeItems: 'center' }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4z" /></svg>
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
}
