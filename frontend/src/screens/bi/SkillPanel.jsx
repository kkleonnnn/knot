// SkillPanel.jsx — v0.8.10 §5（③ 提前落地）BI 右栏 da-asst 数据分析：真·只读报表解读。
// chrome 走共享 <RightPanel>（与 ASK 思考过程同一套壳）。POST /api/bi/reports/{id}/analyze。
// 「仅解读 · 不改写报表」：后端只读冻结快照，不跑新 SQL、不写库（da_asst.arun_da_asst）。
import { useState, useRef, useEffect } from 'react';
import { toast } from '../../utils.jsx';
import { api } from '../../api.js';
import { RightPanel } from '../../RightPanel.jsx';
import { TypingDots } from '../../Shared.jsx';

function Bubble({ T, role, error, children }) {
  const me = role === 'user';
  return (
    <div style={{ display: 'flex', justifyContent: me ? 'flex-end' : 'flex-start', marginBottom: 12 }}>
      <div style={{
        maxWidth: '86%', padding: '9px 12px', borderRadius: 12, fontSize: 13, lineHeight: 1.6,
        whiteSpace: 'pre-wrap',
        background: me ? T.accent : T.chipBg, color: me ? T.sendFg : (error ? T.error : T.text),
        border: me ? 'none' : `1px solid ${error ? T.error : T.border}`,
      }}>{children}</div>
    </div>
  );
}

const intro = (ctx) => ({
  role: 'assistant',
  content: `我是数据分析助手（da-asst），可以帮你解读「${ctx}」。问我任何关于这份报表的问题，比如趋势、异动、对比或占比 —— 我只解读，不改写报表。`,
});

export function SkillPanel({ T, report }) {
  const ctx = report ? report.title : '当前报表';
  const [messages, setMessages] = useState([intro(ctx)]);
  const [q, setQ] = useState('');
  const [sending, setSending] = useState(false);
  const taRef = useRef(null);
  const scrollRef = useRef(null);

  // 切换报表 → 重置对话（新报表新上下文；避免把上一份报表的问答带过来）
  const rid = report ? report.id : null;
  useEffect(() => { setMessages([intro(ctx)]); setQ(''); setSending(false); },
    [rid]);   // eslint-disable-line react-hooks/exhaustive-deps

  // textarea 自增高（打字后统一在 effect 量 scrollHeight）
  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(100, Math.max(22, el.scrollHeight))}px`;
  }, [q]);
  // 新消息 / typing → 滚到底
  useEffect(() => { const el = scrollRef.current; if (el) el.scrollTop = el.scrollHeight; }, [messages, sending]);

  const send = async () => {
    const question = q.trim();
    if (!question || sending) return;
    if (!rid) { toast('请先选择一份报表', true); return; }
    // history = 当前已展示的对话（不含即将追加的这条 user）；**截近 20 条**：后端硬拒 >24（对话久了永久 400），
    // service 侧只取近 12 轮 → 截 20 既不触顶又留足上下文（长对话不会卡死）。
    const history = messages
      .filter((m) => m.role === 'user' || (m.role === 'assistant' && !m.error))
      .map((m) => ({ role: m.role, content: m.content }))
      .slice(-20);
    setMessages((m) => [...m, { role: 'user', content: question }]);
    setQ('');
    setSending(true);
    try {
      const res = await api.post(`/api/bi/reports/${rid}/analyze`, { question, history });
      setMessages((m) => [...m, { role: 'assistant', content: res.answer }]);
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', error: true, content: `分析失败：${e.message || e}` }]);
    } finally {
      setSending(false);
    }
  };

  const onKeyDown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };
  const canSend = !!q.trim() && !sending;

  return (
    <RightPanel T={T} title="数据分析">
      {/* 消息区（flex:1 滚动）*/}
      <div ref={scrollRef} className="cb-sb" style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '16px 16px 4px' }}>
        {messages.map((m, i) => <Bubble key={i} T={T} role={m.role} error={m.error}>{m.content}</Bubble>)}
        {sending && (
          <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 12 }}>
            <div style={{ padding: '10px 14px', borderRadius: 12, background: T.chipBg, border: `1px solid ${T.border}` }}>
              <TypingDots color={T.accent} />
            </div>
          </div>
        )}
      </div>

      {/* 底部：卡片 composer（仅解读 · 不改写报表）*/}
      <div style={{ padding: '12px 14px', borderTop: `1px solid ${T.border}`, flexShrink: 0 }}>
        <div style={{ background: T.content, border: `1px solid ${T.inputBorder}`, borderRadius: 12, padding: '11px 12px', display: 'flex', flexDirection: 'column', gap: 9 }}>
          <textarea ref={taRef} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKeyDown} rows={1}
            placeholder="追问这份报表…" disabled={sending}
            style={{ width: '100%', minHeight: 22, maxHeight: 100, resize: 'none', background: 'transparent', border: 'none', outline: 'none', color: T.text, fontSize: 13, fontFamily: 'inherit', lineHeight: 1.55, padding: 0 }} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ flex: 1, display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 500, letterSpacing: '0.02em', color: T.muted }}>
              <span style={{ width: 5, height: 5, borderRadius: '50%', background: T.accent, flexShrink: 0 }} />
              仅解读 · 不改写报表
            </span>
            <button onClick={send} disabled={!canSend} title="发送（Enter）"
              style={{ width: 30, height: 30, flexShrink: 0, borderRadius: 8, border: 'none', background: T.accent, color: T.sendFg, cursor: canSend ? 'pointer' : 'default', opacity: canSend ? 1 : 0.5, display: 'grid', placeItems: 'center' }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'block' }}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
            </button>
          </div>
        </div>
      </div>
    </RightPanel>
  );
}
