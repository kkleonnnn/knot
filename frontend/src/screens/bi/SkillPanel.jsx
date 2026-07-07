// SkillPanel.jsx — v0.8.5 (②a) BI 右栏 da-asst 数据分析面板（内容层；chrome 走共享 <RightPanel>）。
// ⚠️ 本轮「先复刻 UI」：聊天区为**示例/静态**，真·skill 接入 = ③（da-asst 嵌入形态最大设计决策）。
// #4：宽度/表头/收起键由 RightPanel 统一（与 ASK 思考过程同一套）。#7：卡片式 composer（textarea 自增高 + 方形→发送）。
import { useState, useRef, useEffect } from 'react';
import { toast } from '../../utils.jsx';
import { RightPanel } from '../../RightPanel.jsx';

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

// 建议 chip —— pill 形，hover → accent 描边+字色（handoff §3 / #7）
function Chip({ T, label, onClick }) {
  const [hover, setHover] = useState(false);
  return (
    <button onClick={onClick} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        padding: '5px 10px', borderRadius: 999, fontSize: 11.5, cursor: 'pointer', fontFamily: 'inherit',
        border: `1px solid ${hover ? T.accent : T.border}`, background: T.content,
        color: hover ? T.accent : T.subtext, transition: 'color 120ms, border-color 120ms',
      }}>{label}</button>
  );
}

export function SkillPanel({ T, report }) {
  const [q, setQ] = useState('');
  const taRef = useRef(null);
  // 自增高：q 变（打字 / 点建议 chip）后统一在 effect 量 scrollHeight —— 复核 nit 修：
  // 原 chip onClick 同步 grow(taRef) 读到 setQ 前的旧值；effect 在 q 更新 re-render 后量，两路径都准。
  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(100, Math.max(22, el.scrollHeight))}px`;
  }, [q]);
  const ctx = report ? report.title : '当前报表';
  return (
    <RightPanel T={T} title="数据分析">
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

      {/* 底部：建议 chip 行 + 卡片 composer（#7）*/}
      <div style={{ padding: '12px 14px', borderTop: `1px solid ${T.border}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
          {SUGGESTIONS.map((s) => <Chip key={s} T={T} label={s} onClick={() => setQ(s)} />)}
        </div>
        <div style={{ background: T.content, border: `1px solid ${T.inputBorder}`, borderRadius: 12, padding: '11px 12px', display: 'flex', flexDirection: 'column', gap: 9 }}>
          <textarea ref={taRef} value={q} onChange={(e) => setQ(e.target.value)} rows={1} placeholder="追问这份报表…"
            style={{ width: '100%', minHeight: 22, maxHeight: 100, resize: 'none', background: 'transparent', border: 'none', outline: 'none', color: T.text, fontSize: 12.5, fontFamily: 'inherit', lineHeight: 1.55, padding: 0 }} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ flex: 1, display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: T.mono, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em', color: T.muted }}>
              <span style={{ width: 5, height: 5, borderRadius: '50%', background: T.accent, flexShrink: 0 }} />
              仅解读 · 不改写报表
            </span>
            <button onClick={() => toast('da-asst 即将接入（③）')} title="da-asst 即将接入（③）"
              style={{ width: 30, height: 30, flexShrink: 0, borderRadius: 8, border: 'none', background: T.accent, color: T.sendFg, cursor: 'pointer', display: 'grid', placeItems: 'center' }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'block' }}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
            </button>
          </div>
        </div>
      </div>
    </RightPanel>
  );
}
