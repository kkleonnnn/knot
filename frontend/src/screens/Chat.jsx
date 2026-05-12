// v0.5.3 拆分：本主文件作"调度员"；保留 ChatScreen export 名 + props 签名（R-116 强制）。
// 子模块（screens/chat/*）：
//   intent_helpers.js / sse_handler.js / ResultBlock.jsx / ChatEmpty.jsx
//   Conversation.jsx / ThinkingCard.jsx / Composer.jsx
//
// R-118 SSE handler 纯函数化（runQueryStream from sse_handler.js）— 通过 callbacks 注入 state setter。
// R-126 brand：CSV 导出文件名前缀 `knot-` 保留（L52）；KNOT 提示文字搬到 ChatEmpty.jsx。
// R-127 错误边界：error_kind / user_message / is_retryable 字段 sse_handler.js 透传 → ResultBlock.jsx 渲染。
import { useState, useRef, useEffect } from 'react';
import { I, iconBtn } from '../Shared.jsx';
import { usePersist, toast } from '../utils.jsx';
import { AppShell, SideHeading } from '../Shell.jsx';
import { api } from '../api.js';
import { ChatEmpty } from './chat/ChatEmpty.jsx';
import { ChatConversation } from './chat/Conversation.jsx';
import { runQueryStream } from './chat/sse_handler.js';

export function ChatScreen({ T, user, onToggleTheme, onNavigate, onLogout }) {
  const [convs, setConvs] = useState([]);
  const [activeConvId, setActiveConvId] = usePersist('cb_conv', null);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [dbOk, setDbOk] = useState(null);
  const [agentEvents, setAgentEvents] = useState([]);
  const [activeUpload, setActiveUpload] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => { loadConvs(); checkDb(); }, []);
  useEffect(() => { if (activeConvId) loadMessages(activeConvId); else setMessages([]); }, [activeConvId]);
  useEffect(() => { if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight; }, [messages]);

  const loadConvs = async () => {
    try {
      const d = await api.get('/api/conversations');
      setConvs(d);
      // 若当前 activeConvId 不在该 user 的列表中（账号切换 / 会话已删），重置避免 query 报 404
      if (activeConvId && !d.some(c => c.id === activeConvId)) {
        setActiveConvId(null);
        setMessages([]);
      }
    } catch {}
  };
  const checkDb = async () => {
    try { const d = await api.get('/api/db/status'); setDbOk(d.connected); } catch { setDbOk(false); }
  };
  const loadMessages = async (cid) => {
    try { const d = await api.get(`/api/conversations/${cid}/messages`); setMessages(d); } catch {}
  };

  const newChat = async () => {
    try {
      const d = await api.post('/api/conversations', { title: '新对话' });
      setConvs(prev => [d, ...prev]);
      setActiveConvId(d.id);
      setMessages([]);
    } catch { toast('创建对话失败', true); }
  };

  const deleteConv = async (cid, e) => {
    e.stopPropagation();
    try {
      await api.del(`/api/conversations/${cid}`);
      setConvs(prev => prev.filter(c => c.id !== cid));
      if (activeConvId === cid) { setActiveConvId(null); setMessages([]); }
    } catch { toast('删除失败', true); }
  };

  const sendQuery = async (e) => {
    e?.preventDefault();
    if (!question.trim() || loading) return;

    // 没活动会话则即时创建并直接用 id 发送，避免依赖 setState 异步更新导致首次发送丢失
    let convId = activeConvId;
    if (!convId) {
      try {
        const d = await api.post('/api/conversations', { title: '新对话' });
        setConvs(prev => [d, ...prev]);
        setActiveConvId(d.id);
        setMessages([]);
        convId = d.id;
      } catch { toast('创建对话失败', true); return; }
    }

    const q = question.trim();
    setQuestion('');
    setLoading(true);
    setAgentEvents([]);

    const tempId = Date.now();
    const tempMsg = { id: tempId, question: q, sql: '', rows: [], explanation: '', confidence: '', error: '', loading: true };
    setMessages(prev => [...prev, tempMsg]);

    const body = { question: q };
    if (activeUpload) body.upload_id = activeUpload.id;

    // R-118 纯函数 runQueryStream + callbacks 注入 state setter
    await runQueryStream(`/api/conversations/${convId}/query-stream`, body, api._token(), {
      onAgentEvent: (ev) => setAgentEvents(prev => [...prev, ev].slice(-20)),
      onClarification: (ev) => {
        setMessages(prev => prev.map(m => m.id === tempId ? {
          id: ev.message_id, question: q,
          explanation: ev.question, is_clarification: true,
          sql: '', rows: [], confidence: 'low', error: '',
          input_tokens: ev.input_tokens, output_tokens: ev.output_tokens,
          cost_usd: ev.cost_usd, intent: ev.intent || null, loading: false,
        } : m));
        setLoading(false);
      },
      onError: (ev) => {
        // v0.4.4 R-30/R-33：error_translator 翻译产物（kind/user_message/is_retryable）
        setMessages(prev => prev.map(m => m.id === tempId ? {
          ...m, loading: false,
          error: ev.user_message || ev.message,
          error_kind: ev.error_kind || null,
          user_message: ev.user_message || null,
          is_retryable: ev.is_retryable ?? null,
        } : m));
        setLoading(false);
      },
      onFinal: (ev) => {
        setMessages(prev => prev.map(m => m.id === tempId ? {
          id: ev.message_id, question: q,
          sql: ev.sql, rows: ev.rows || [],
          explanation: ev.explanation, confidence: ev.confidence,
          error: ev.error || '',
          insight: ev.insight, suggested_followups: ev.suggested_followups || [],
          input_tokens: ev.input_tokens, output_tokens: ev.output_tokens,
          cost_usd: ev.cost_usd, query_time_ms: ev.query_time_ms,
          intent: ev.intent || null,
          // v0.4.2 新增（向前展开）
          agent_costs: ev.agent_costs || null,
          recovery_attempt: ev.recovery_attempt || 0,
          // v0.4.3 R-22 双路径同字段（流式 SSE final 事件）
          budget_status: ev.budget_status || null,
          budget_meta: ev.budget_meta || null,
          // v0.4.4 R-33 双路径同字段（success path 也带 null 占位）
          error_kind: ev.error_kind || null,
          user_message: ev.user_message || null,
          is_retryable: ev.is_retryable ?? null,
          loading: false,
        } : m));
        loadConvs();
        setLoading(false);
      },
      onException: (err) => {
        setMessages(prev => prev.map(m => m.id === tempId ? { ...m, loading: false, error: String(err) } : m));
        setLoading(false);
      },
    });
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuery(); }
  };

  const copyToClipboard = (text) => { navigator.clipboard?.writeText(text); toast('已复制'); };

  // v0.4.1 ⭐ 收藏：POST /api/messages/{id}/pin；R-12 幂等：already_pinned=true 也算成功
  const pinMessage = async (mid) => {
    try {
      const sr = await api.post(`/api/messages/${mid}/pin`, {});
      toast(sr.already_pinned ? '该消息已收藏过' : '已收藏到报表');
      return { ok: true, sr };
    } catch (e) {
      toast(`收藏失败: ${e.message}`, true);
      return { ok: false };
    }
  };

  const downloadCSV = (rows, question) => {
    if (!rows || !rows.length) return;
    const headers = Object.keys(rows[0]);
    const csv = [headers.join(','), ...rows.map(r => headers.map(h => JSON.stringify(r[h] ?? '')).join(','))].join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    a.download = `knot-${Date.now()}.csv`;
    a.click();
  };

  const handleUpload = async (file) => {
    const fd = new FormData();
    fd.append('file', file);
    try {
      const r = await fetch('/api/upload', { method: 'POST', headers: { Authorization: `Bearer ${api._token()}` }, body: fd });
      if (!r.ok) throw new Error(await r.text());
      const d = await r.json();
      setActiveUpload(d);
      toast(`已加载 ${d.filename}（${d.row_count} 行）`);
    } catch (e) { toast(`上传失败: ${e.message}`, true); }
  };

  // v0.5.30 #31 — 历史对话按 updated_at 切 最近(7d内) / 更早 两组（demo home.jsx L14-35 byte-equal）
  const _NOW = Date.now();
  const _WEEK_MS = 7 * 24 * 3600 * 1000;
  const recentConvs = convs.filter(c => _NOW - new Date(c.updated_at).getTime() < _WEEK_MS);
  const olderConvs  = convs.filter(c => _NOW - new Date(c.updated_at).getTime() >= _WEEK_MS);

  const convRow = (c) => {
    // v0.5.31 #35 — active conv 高亮 demo byte-equal（thinking.jsx ChatItem L281-291）：
    // brandSoft 8% bg + brandSoftBorder 25% + T.text；inactive 加 transparent 1px border 防 layout shift；
    // 撤回 v0.5.26 brandSoft 12% bg + T.accent text（资深"框比例不对 + 左侧深色边"反馈）
    const isActive = c.id === activeConvId;
    return (
      <div key={c.id} onClick={() => setActiveConvId(c.id)} style={{
        display: 'flex', alignItems: 'center', gap: 6, padding: '7px 10px',
        margin: '0 8px',
        borderRadius: 6, cursor: 'pointer',
        background: isActive ? `color-mix(in oklch, ${T.accent} 8%, transparent)` : 'transparent',
        border: isActive ? `1px solid color-mix(in oklch, ${T.accent} 25%, transparent)` : '1px solid transparent',
        color: isActive ? T.text : T.subtext, fontSize: 12.5,
        fontWeight: isActive ? 500 : 400,
      }}>
        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.title || '未命名对话'}</span>
        <button onClick={(e) => { e.stopPropagation(); deleteConv(c.id, e); }} style={{ ...iconBtn(T), width: 20, height: 20, opacity: 0.5, flexShrink: 0 }}><I.trash/></button>
      </div>
    );
  };

  const sidebarContent = (
    <>
      {/* v0.5.30 #29 — 新建对话 button: justify left-start + padding 升级 + gap 10（demo Btn variant=default size=md byte-equal）*/}
      <div style={{ padding: '0 8px 8px' }}>
        <button onClick={newChat} style={{
          display: 'flex', alignItems: 'center', justifyContent: 'flex-start', gap: 10, width: '100%',
          padding: '10px 14px', borderRadius: 8, background: T.card,
          color: T.text, border: `1px solid ${T.border}`,
          fontFamily: 'inherit', fontSize: 13, fontWeight: 500, cursor: 'pointer',
        }}>
          <I.plus width="14" height="14"/> 新建对话
        </button>
      </div>
      {/* v0.5.30 #30 — 收藏报表 → 收藏查询；删 📌；左 bookmark svg + 右 chev 右箭头（指明跳转）*/}
      <div style={{ padding: '0 8px 8px' }}>
        <button onClick={() => onNavigate('saved-reports')} style={{
          display: 'flex', alignItems: 'center', gap: 10, width: '100%',
          padding: '8px 14px', borderRadius: 8, background: 'transparent',
          color: T.subtext, border: 'none', fontFamily: 'inherit', fontSize: 12.5,
          cursor: 'pointer',
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
            <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
          </svg>
          <span style={{ flex: 1, textAlign: 'left' }}>收藏查询</span>
          <I.chev style={{ transform: 'rotate(-90deg)', flexShrink: 0, opacity: 0.6 }}/>
        </button>
      </div>
      {/* v0.5.30 #31 — 最近 / 更早 分组 + SideHeading（demo home.jsx byte-equal）*/}
      <div className="cb-sb" style={{ display: 'flex', flexDirection: 'column', gap: 1, flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {recentConvs.length > 0 && (
          <>
            <SideHeading T={T}>最近</SideHeading>
            {recentConvs.map(convRow)}
          </>
        )}
        {olderConvs.length > 0 && (
          <>
            <SideHeading T={T}>更早</SideHeading>
            {olderConvs.map(convRow)}
          </>
        )}
      </div>
    </>
  );

  const title = activeConvId ? (convs.find(c => c.id === activeConvId)?.title || '对话') : '新对话';

  return (
    <AppShell T={T} user={user} active="chat" sidebarContent={sidebarContent}
              topbarTitle={title} hideSidebarNewChat
              showConnectionPill connectionOk={dbOk}
              onToggleTheme={onToggleTheme} onNewChat={newChat}
              onNavigate={onNavigate} onLogout={onLogout}>
      {!activeConvId || messages.length === 0
        ? <ChatEmpty T={T} user={user} onSend={(q) => setQuestion(q)} onNewChat={newChat}
                     hasConv={!!activeConvId} question={question} setQuestion={setQuestion}
                     loading={loading} onSubmit={sendQuery} onKeyDown={handleKeyDown}
                                          activeUpload={activeUpload} setActiveUpload={setActiveUpload} onUpload={handleUpload}/>
        : <ChatConversation T={T} messages={messages} scrollRef={scrollRef} loading={loading}
                            question={question} setQuestion={setQuestion}
                            onSubmit={sendQuery} onKeyDown={handleKeyDown}
                            onCopy={copyToClipboard} onDownload={downloadCSV} onPin={pinMessage}
                            onRetry={(q) => { setQuestion(q); }}
                                                        agentEvents={agentEvents}
                            activeUpload={activeUpload} setActiveUpload={setActiveUpload} onUpload={handleUpload}/>
      }
    </AppShell>
  );
}
