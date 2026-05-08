import { useState, useRef, useEffect } from 'react';
import { I, iconBtn, pillBtn, LineChart, BarChart, PieChart, TypingDots } from '../Shared.jsx';
import { usePersist, toast, Spinner } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { api } from '../api.js';

// v0.4.0: Clarifier 输出的 7 类 intent → 前端 layout（与后端 INTENT_TO_HINT 一一对应）
const INTENT_TO_HINT = {
  metric: 'metric_card',
  trend: 'line',
  compare: 'bar',
  rank: 'rank_view',
  distribution: 'pie',
  retention: 'retention_matrix',
  detail: 'detail_table',
};

// v0.4.0 老消息（无 intent 字段）兼容降级：从 rows/cols 形态推断意图
function inferIntentFromShape(rows, cols) {
  if (!rows || rows.length === 0) return 'detail';
  if (rows.length === 1) return 'metric';  // 单行（不论几列）作 metric
  if (cols.some(c => /\d{4}[-/年]/.test(String(rows[0][c])))) return 'trend';
  if (cols.length >= 4) return 'detail';
  const idLikeCols = cols.filter(c => /(_id|^id)$/i.test(c));
  if (idLikeCols.length > 0 && cols.length <= 3) return 'detail';
  return 'rank';
}

// v0.4.1 R-S4 effectiveHint 三级优先级链：
//   1. msg.display_hint  — saved_report 快照（v0.4.1 SavedReportView 注入）
//   2. INTENT_TO_HINT[msg.intent] — v0.4.0 message + 当前 mapping
//   3. INTENT_TO_HINT[inferIntentFromShape(...)] — v0.4.0 之前老消息启发式
function resolveEffectiveHint(msg, rows, cols) {
  if (msg.display_hint) return msg.display_hint;
  if (msg.intent && INTENT_TO_HINT[msg.intent]) return INTENT_TO_HINT[msg.intent];
  return INTENT_TO_HINT[inferIntentFromShape(rows, cols)] || 'detail_table';
}

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

    try {
      const body = { question: q };
      if (activeUpload) body.upload_id = activeUpload.id;

      const resp = await fetch(`/api/conversations/${convId}/query-stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${api._token()}` },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(await resp.text());

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop();
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          let ev;
          try { ev = JSON.parse(line.slice(6)); } catch { continue; }

          if (ev.type === 'agent_start' || ev.type === 'agent_done' || ev.type === 'sql_step') {
            setAgentEvents(prev => [...prev, ev].slice(-20));
          }
          if (ev.type === 'clarification_needed') {
            setAgentEvents(prev => [...prev, ev].slice(-20));
            setMessages(prev => prev.map(m => m.id === tempId ? {
              id: ev.message_id, question: q,
              explanation: ev.question, is_clarification: true,
              sql: '', rows: [], confidence: 'low', error: '',
              input_tokens: ev.input_tokens, output_tokens: ev.output_tokens,
              cost_usd: ev.cost_usd, intent: ev.intent || null, loading: false,
            } : m));
            setLoading(false);
          }
          if (ev.type === 'error') {
            setMessages(prev => prev.map(m => m.id === tempId ? { ...m, loading: false, error: ev.message } : m));
            setLoading(false);
          }
          if (ev.type === 'final') {
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
              loading: false,
            } : m));
            loadConvs();
            setLoading(false);
          }
        }
      }
    } catch (err) {
      setMessages(prev => prev.map(m => m.id === tempId ? { ...m, loading: false, error: String(err) } : m));
      setLoading(false);
    }
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
    a.download = `bi-agent-${Date.now()}.csv`;
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

  const convList = convs.map(c => (
    <div key={c.id} onClick={() => setActiveConvId(c.id)} style={{
      display: 'flex', alignItems: 'center', gap: 6, padding: '7px 10px',
      borderRadius: 6, cursor: 'pointer',
      background: c.id === activeConvId ? T.accentSoft : 'transparent',
      color: c.id === activeConvId ? T.accent : T.subtext, fontSize: 12.5,
      borderLeft: c.id === activeConvId ? `2px solid ${T.accent}` : '2px solid transparent',
      paddingLeft: c.id === activeConvId ? 8 : 10,
      fontWeight: c.id === activeConvId ? 500 : 400,
    }}>
      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.title || '未命名对话'}</span>
      <button onClick={(e) => { e.stopPropagation(); deleteConv(c.id, e); }} style={{ ...iconBtn(T), width: 20, height: 20, opacity: 0.5, flexShrink: 0 }}><I.trash/></button>
    </div>
  ));

  const sidebarContent = (
    <>
      <button onClick={newChat} style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, width: '100%',
        padding: '9px 10px', borderRadius: 8, background: 'transparent',
        color: T.text, border: `1px solid ${T.border}`,
        fontFamily: 'inherit', fontSize: 13, fontWeight: 500, cursor: 'pointer', marginBottom: 8,
      }}>
        <I.plus width="14" height="14"/> 新建对话
      </button>
      {/* v0.4.1: 收藏报表入口 */}
      <button onClick={() => onNavigate('saved-reports')} style={{
        display: 'flex', alignItems: 'center', gap: 8, width: '100%',
        padding: '7px 10px', borderRadius: 6, background: 'transparent',
        color: T.subtext, border: 'none', fontFamily: 'inherit', fontSize: 12.5,
        cursor: 'pointer', marginBottom: 6,
      }}>
        <span>📌</span> 收藏报表
      </button>
      <div className="cb-sb" style={{ display: 'flex', flexDirection: 'column', gap: 1, flex: 1, overflowY: 'auto', minHeight: 0 }}>{convList}</div>
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
                                                        agentEvents={agentEvents}
                            activeUpload={activeUpload} setActiveUpload={setActiveUpload} onUpload={handleUpload}/>
      }
    </AppShell>
  );
}

function ChatEmpty({ T, user, question, setQuestion, loading, onSubmit, onKeyDown, activeUpload, setActiveUpload, onUpload }) {
  const firstName = user?.display_name?.split(' ')[0] || user?.username || '你';
  const suggestions = [
    '今天的订单总量是多少？',
    '最近 7 天每日 GMV 趋势',
    '新用户注册数量（本月）',
    '查看数据库有哪些表',
  ];
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '24px 28px' }}>
      <div style={{ width: '100%', maxWidth: 640, textAlign: 'center', marginBottom: 22 }}>
        <div style={{ fontSize: 28, fontWeight: 600, color: T.text, letterSpacing: '-0.02em', marginBottom: 8 }}>Hi {firstName}</div>
        <div style={{ fontSize: 14, color: T.subtext }}>今天想了解哪部分业务数据？</div>
      </div>
      <Composer T={T} value={question} onChange={setQuestion} loading={loading}
                onSubmit={onSubmit} onKeyDown={onKeyDown}
                                activeUpload={activeUpload} setActiveUpload={setActiveUpload} onUpload={onUpload}/>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8, marginTop: 14, maxWidth: 640, width: '100%' }}>
        {suggestions.map((s, i) => (
          <button key={i} onClick={() => setQuestion(s)} style={{
            display: 'flex', alignItems: 'center', gap: 10, padding: '11px 13px',
            border: `1px solid ${T.border}`, borderRadius: 8,
            cursor: 'pointer', background: T.content, textAlign: 'left',
            color: T.subtext, fontSize: 12.5, fontFamily: 'inherit',
          }}>
            <I.sparkle style={{ color: T.accent, flexShrink: 0 }}/>
            {s}
          </button>
        ))}
      </div>
      <div style={{ marginTop: 20, fontSize: 11, color: T.muted }}>BI-Agent 可能出错 · 关键结果请核对原始数据</div>
    </div>
  );
}

function ChatConversation({ T, messages, scrollRef, loading, question, setQuestion, onSubmit, onKeyDown, onCopy, onDownload, onPin, agentEvents, activeUpload, setActiveUpload, onUpload }) {
  const showPanel = agentEvents.length > 0;
  return (
    <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
        <div ref={scrollRef} className="cb-sb" style={{ flex: 1, overflowY: 'auto', padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          {messages.map((msg, i) => (
            <div key={msg.id || i} className="cb-fadein">
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
                <div style={{
                  background: T.chipBg, border: `1px solid ${T.chipBorder}`, color: T.text,
                  padding: '10px 14px', borderRadius: 12, borderTopRightRadius: 4,
                  fontSize: 14, maxWidth: 520,
                }}>{msg.question}</div>
              </div>
              <div style={{ display: 'flex', gap: 10 }}>
                <div style={{ width: 26, height: 26, borderRadius: 6, flexShrink: 0, background: T.accent, color: '#fff', display: 'grid', placeItems: 'center', boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.25)' }}>
                  <I.sparkle width="14" height="14"/>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  {msg.loading
                    ? <ThinkingCard T={T} agentEvents={agentEvents}/>
                    : <ResultBlock T={T} msg={msg} onCopy={onCopy} onDownload={onDownload}
                                   onPin={onPin}
                                   onFollowup={(q) => setQuestion(q)}/>}
                </div>
              </div>
            </div>
          ))}
        </div>
        <div style={{ padding: '10px 28px 18px', background: `linear-gradient(to top, ${T.content} 80%, ${T.content}00)` }}>
          <div style={{ maxWidth: 800, margin: '0 auto' }}>
            <Composer T={T} value={question} onChange={setQuestion} loading={loading}
                      onSubmit={onSubmit} onKeyDown={onKeyDown}
                                            activeUpload={activeUpload} setActiveUpload={setActiveUpload} onUpload={onUpload}
                      placeholder="继续追问…"/>
          </div>
        </div>
      </div>
      {showPanel && <AgentThinkingPanel T={T} events={agentEvents} visible={showPanel}/>}
    </div>
  );
}

function ThinkingCard({ T, agentEvents = [] }) {
  const AGENT_LABELS = { clarifier: '理解问题', sql_planner: '生成 SQL', presenter: '整理洞察' };
  const lastStart = [...agentEvents].reverse().find(e => e.type === 'agent_start');
  const label = lastStart ? AGENT_LABELS[lastStart.agent] || lastStart.label : '正在思考';
  return (
    <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '13px 16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: T.subtext }}>
        <TypingDots color={T.accent}/>
        <span>{agentEvents.length > 0 ? `${label}…` : '正在生成 SQL…'}</span>
      </div>
    </div>
  );
}

function ResultBlock({ T, msg, onCopy, onDownload, onFollowup, onPin }) {
  const [sqlOpen, setSqlOpen] = useState(false);
  const [chartType, setChartType] = useState('auto');
  const [pinned, setPinned] = useState(!!msg.is_pinned);
  const { sql, rows, explanation, confidence, error, input_tokens, output_tokens, cost_usd, retry_count, query_time_ms,
          insight, suggested_followups, is_clarification, intent,
          agent_costs, recovery_attempt,
          budget_status, budget_meta } = msg;  // v0.4.2 分桶 + 自纠正 / v0.4.3 预算告警

  if (is_clarification) {
    return (
      <div style={{ background: T.card, border: `1px solid ${T.accent}30`, borderRadius: 10, padding: '14px 16px' }}>
        <div style={{ fontSize: 13, color: T.accent, fontWeight: 500, marginBottom: 4 }}>需要澄清</div>
        <div style={{ fontSize: 13.5, color: T.text, lineHeight: 1.65 }}>{explanation}</div>
        {(input_tokens > 0 || output_tokens > 0) && (
          <div style={{ display: 'flex', gap: 12, fontSize: 11, color: T.muted, fontFamily: T.mono, marginTop: 8 }}>
            <span>↑ {input_tokens?.toLocaleString()} tok</span>
            <span>↓ {output_tokens?.toLocaleString()} tok</span>
            {cost_usd > 0 && <span>$ {cost_usd?.toFixed(5)}</span>}
          </div>
        )}
      </div>
    );
  }

  if (error && !sql) {
    return (
      <div style={{ background: T.accentSoft, border: `1px solid ${T.accent}30`, borderRadius: 10, padding: '13px 16px', color: T.accent, fontSize: 13 }}>
        {error}
      </div>
    );
  }

  const cols = rows && rows.length > 0 ? Object.keys(rows[0]) : [];
  const isNumericCol = (col) => rows && rows.some(r => typeof r[col] === 'number' && r[col] !== null);
  const numericCols = cols.filter(isNumericCol);
  const labelCols = cols.filter(c => !isNumericCol(c));
  const chartable = labelCols.length >= 1 && numericCols.length >= 1 && rows && rows.length >= 2;

  // v0.4.1 R-S4 三级优先级链：display_hint > INTENT_TO_HINT[intent] > inferIntentFromShape
  const layoutHint = resolveEffectiveHint(msg, rows, cols);
  const isMetric = layoutHint === 'metric_card';
  const isDetail = layoutHint === 'detail_table';
  const isRetention = layoutHint === 'retention_matrix';

  const isDateLike = chartable && rows.some(r => /\d{4}[-/年]\d/.test(String(r[labelCols[0]] || '')));
  // intent → 默认 chart type；retention/detail/metric 不画 chart
  const intentDefaultType = ({ line: 'line', bar: 'bar', pie: 'pie', rank_view: 'bar' })[layoutHint] || null;
  const autoType = (() => {
    if (intentDefaultType) return intentDefaultType;
    if (!chartable) return 'bar';
    if (isDateLike || rows.length > 12) return 'line';
    if (numericCols.length === 1 && rows.length <= 10) return 'pie';
    return 'bar';
  })();

  const activeType = chartType === 'auto' ? autoType : chartType;
  const showChart = chartable && !isMetric && !isDetail && !isRetention;

  const chartData = chartable
    ? (isDateLike ? [...rows].sort((a, b) => String(a[labelCols[0]]).localeCompare(String(b[labelCols[0]]))) : rows)
        .slice(0, 50).map(r => {
          const pt = { [labelCols[0]]: r[labelCols[0]] };
          numericCols.forEach(c => { pt[c] = r[c]; });
          return pt;
        })
    : [];
  const pieData = chartable
    ? rows.slice(0, 8).map(r => ({ [labelCols[0]]: r[labelCols[0]], [numericCols[0]]: r[numericCols[0]] }))
    : [];

  const chartBtns = [
    { id: 'line', label: '折线' },
    { id: 'bar',  label: '柱状' },
    { id: 'pie',  label: '饼图' },
  ];

  // v0.4.1 ⭐ 收藏按钮（仅当有 sql + msg.id 是真实数字 + 非 saved_report 内嵌渲染）
  const canPin = !!(sql && Number.isInteger(msg.id) && !msg.is_saved_report);

  const handlePin = async () => {
    if (!canPin || pinned || !onPin) return;
    const r = await onPin(msg.id);
    if (r && r.ok) setPinned(true);
  };

  // v0.4.3 R-20 预算 banner（sessionStorage 降噪）
  const yearMonth = new Date().toISOString().slice(0, 7).replace('-', '');  // 'YYYYMM'
  const dismissKey = `budget_warn_${msg.user_id || 'self'}_${yearMonth}`;
  const [budgetDismissed, setBudgetDismissed] = useState(
    () => typeof sessionStorage !== 'undefined' && sessionStorage.getItem(dismissKey) === '1'
  );
  const showBudgetBanner = budget_status && budget_status !== 'ok' && !budgetDismissed && budget_meta;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* v0.4.3 R-20 预算告警 banner（每 user × 月份 sessionStorage 降噪） */}
      {showBudgetBanner && (
        <div style={{
          padding: '10px 14px', borderRadius: 8,
          background: budget_status === 'block' ? T.accentSoft : '#FF990022',
          border: `1px solid ${budget_status === 'block' ? T.accent : '#FF9900'}`,
          color: budget_status === 'block' ? T.accent : '#cc6600',
          fontSize: 12.5, display: 'flex', alignItems: 'center', gap: 10,
        }}>
          <span style={{ fontSize: 16 }}>{budget_status === 'block' ? '🛑' : '⚠️'}</span>
          <span style={{ flex: 1 }}>
            {budget_status === 'block' ? '预算已达硬阈值（block）' : '预算告警'}：
            本月已用 <strong>{budget_meta.percentage}%</strong> 配额（${budget_meta.current?.toFixed(4)} / ${budget_meta.threshold?.toFixed(2)} {budget_meta.budget_type}）
          </span>
          <button onClick={() => {
            try { sessionStorage.setItem(dismissKey, '1'); } catch {}
            setBudgetDismissed(true);
          }} style={{
            padding: '4px 10px', borderRadius: 5, fontSize: 11,
            border: '1px solid currentColor', background: 'transparent', color: 'inherit',
            cursor: 'pointer', fontFamily: 'inherit',
          }}>本会话不再提醒</button>
        </div>
      )}

      {(canPin || explanation) && (
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
          {explanation && (
            <div style={{ flex: 1, fontSize: 13.5, color: T.text, lineHeight: 1.65 }}>{explanation}</div>
          )}
          {canPin && (
            <button
              onClick={handlePin}
              disabled={pinned}
              title={pinned ? '已收藏' : '收藏到报表'}
              style={{
                ...iconBtn(T),
                color: pinned ? T.accent : T.muted,
                cursor: pinned ? 'default' : 'pointer',
                fontSize: 14,
              }}
            >
              {pinned ? '🌟' : '⭐'}
            </button>
          )}
        </div>
      )}
      {error && <div style={{ padding: '8px 12px', background: T.accentSoft, borderRadius: 6, color: T.accent, fontSize: 12.5 }}>{error}</div>}

      {rows && rows.length > 0 && isMetric && (
        <MetricCard T={T} rows={rows} cols={cols} numericCols={numericCols}/>
      )}

      {rows && rows.length > 0 && !isMetric && (
        <>
          {showChart && (
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '12px 12px 10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <span style={{ fontSize: 11, color: T.muted, fontFamily: T.mono }}>{labelCols[0]} · {numericCols[0]}</span>
                <div style={{ display: 'flex', gap: 3 }}>
                  {chartBtns.map(btn => (
                    <button key={btn.id} onClick={() => setChartType(btn.id)} style={{
                      padding: '3px 9px', borderRadius: 5, fontSize: 11, fontFamily: 'inherit', cursor: 'pointer',
                      background: activeType === btn.id ? T.accent : 'transparent',
                      color: activeType === btn.id ? '#fff' : T.muted,
                      border: `1px solid ${activeType === btn.id ? T.accent : T.border}`,
                      transition: 'all .15s',
                    }}>{btn.label}</button>
                  ))}
                </div>
              </div>
              {activeType === 'line' && <LineChart data={chartData} stroke={T.accent} fill labelColor={T.muted} gridColor={T.borderSoft} width={640} height={190}/>}
              {activeType === 'bar'  && <BarChart  data={chartData} color={T.accent} labelColor={T.muted} gridColor={T.borderSoft} width={640} height={210}/>}
              {activeType === 'pie'  && <PieChart  data={pieData} width={640} height={210} labelColor={T.muted}/>}
            </div>
          )}
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
            <div style={{ padding: '10px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: `1px solid ${T.border}` }}>
              <span style={{ fontSize: 12, color: T.muted, fontFamily: T.mono }}>{rows.length} 行 · {cols.length} 列</span>
              {isDetail && msg.id
                ? <button onClick={() => exportMessageCsv(msg.id)} style={{ ...iconBtn(T), gap: 4, fontSize: 11 }} title="导出 CSV"><I.dl/></button>
                : <button onClick={() => onDownload(rows, msg.question)} style={{ ...iconBtn(T), gap: 4, fontSize: 11 }} title="下载 CSV"><I.dl/></button>}
            </div>
            <div className="cb-sb" style={{ overflowX: 'auto', maxHeight: 280 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                <thead>
                  <tr style={{ background: T.bg }}>
                    {cols.map(c => <th key={c} style={{ padding: '8px 12px', textAlign: 'left', color: T.muted, fontWeight: 600, fontSize: 11, letterSpacing: '0.03em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}`, whiteSpace: 'nowrap' }}>{c}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 100).map((row, ri) => (
                    <tr key={ri} style={{ borderBottom: ri < rows.length - 1 ? `1px solid ${T.borderSoft}` : 'none' }}>
                      {cols.map(c => <td key={c} style={{ padding: '8px 12px', color: T.text, whiteSpace: 'nowrap', fontFamily: typeof row[c] === 'number' ? T.mono : 'inherit' }}>{row[c] === null || row[c] === undefined ? <span style={{ color: T.muted }}>—</span> : String(row[c])}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {insight && (
        <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '12px 16px' }}>
          <div style={{ fontSize: 11, color: T.accent, fontWeight: 600, marginBottom: 6, letterSpacing: '0.04em', textTransform: 'uppercase' }}>洞察</div>
          <div style={{ fontSize: 13.5, color: T.text, lineHeight: 1.7 }}>{insight}</div>
        </div>
      )}

      {suggested_followups && suggested_followups.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {suggested_followups.map((q, i) => (
            <button key={i} onClick={() => onFollowup && onFollowup(q)} style={{
              padding: '5px 12px', borderRadius: 20, fontSize: 12, fontFamily: 'inherit', cursor: 'pointer',
              background: T.accentSoft, color: T.accent,
              border: `1px solid ${T.accent}30`, transition: 'all .15s',
            }}>{q}</button>
          ))}
        </div>
      )}

      {sql && (
        <div style={{ background: T.codeBg, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
          <div onClick={() => setSqlOpen(!sqlOpen)} style={{
            cursor: 'pointer', padding: '9px 14px', display: 'flex', alignItems: 'center', gap: 8,
            color: T.subtext, fontSize: 12.5,
          }}>
            <I.sql/> <span>查看 SQL</span>
            <span style={{ marginLeft: 'auto', color: T.muted, fontSize: 11, fontFamily: T.mono }}>
              {query_time_ms ? `${query_time_ms}ms` : ''}
              {retry_count > 0 ? ` · ${retry_count}次重试` : ''}
            </span>
            <I.chev style={{ transform: sqlOpen ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }}/>
          </div>
          {sqlOpen && (
            <div style={{ position: 'relative', borderTop: `1px solid ${T.border}` }}>
              <button onClick={() => onCopy(sql)} style={{ ...iconBtn(T), position: 'absolute', top: 8, right: 8 }} title="复制"><I.copy/></button>
              <pre style={{ margin: 0, padding: '10px 16px 14px', fontFamily: T.mono, fontSize: 12, lineHeight: 1.65, color: T.codeText, overflowX: 'auto', paddingRight: 40 }}>{sql}</pre>
            </div>
          )}
        </div>
      )}

      {(input_tokens > 0 || output_tokens > 0) && (
        <div style={{ display: 'flex', gap: 12, fontSize: 11, color: T.muted, fontFamily: T.mono, flexWrap: 'wrap' }}>
          <span>↑ {input_tokens?.toLocaleString()} tok</span>
          <span>↓ {output_tokens?.toLocaleString()} tok</span>
          {cost_usd > 0 && <span>$ {cost_usd?.toFixed(5)}</span>}
          {confidence && <span style={{ color: confidence === 'high' ? T.success : confidence === 'medium' ? T.warn : T.accent }}>{confidence}</span>}
          {recovery_attempt > 0 && (
            <span title="自纠正次数（fan-out reject + fix_sql retry）"
                  style={{ color: T.warn || '#FF9900' }}>
              ↻ {recovery_attempt}
            </span>
          )}
        </div>
      )}

      {/* v0.4.2 per-agent cost 分桶 chip（仅当 agent_costs 存在时；老消息走 cost_usd 单值兼容）*/}
      {agent_costs && Object.values(agent_costs).some(b => b && (b.cost > 0 || b.tokens > 0)) && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', fontSize: 10.5, fontFamily: T.mono }}>
          {Object.entries(agent_costs)
            .filter(([_, b]) => b && (b.cost > 0 || b.tokens > 0))
            .map(([kind, b]) => (
              <span key={kind} title={`${kind}: $${b.cost?.toFixed(5) || 0} / ${b.tokens || 0} tok`}
                    style={{
                      padding: '2px 8px', borderRadius: 10,
                      background: T.bg || '#0001', color: T.muted,
                      border: `1px solid ${T.borderSoft || T.border}`,
                    }}>
                {AGENT_KIND_EMOJI[kind] || '·'} {kind}: ${b.cost?.toFixed(5) || '0.00000'}
              </span>
            ))}
        </div>
      )}
    </div>
  );
}

// v0.4.2: agent_kind → emoji（与 SavedReports intent emoji 同款风格）
const AGENT_KIND_EMOJI = {
  clarifier:   '💡',
  sql_planner: '🔍',
  fix_sql:     '🔧',
  presenter:   '📊',
};

// v0.4.0: metric intent 渲染大数字卡片（取代 chart+table）
function MetricCard({ T, rows, cols, numericCols }) {
  if (!rows || rows.length === 0) return null;
  const r = rows[0];
  const valueCol = numericCols[0] || cols[0];
  const labelCol = cols.find(c => c !== valueCol);
  const value = r[valueCol];
  const display = (value === null || value === undefined)
    ? '—'
    : (typeof value === 'number' ? value.toLocaleString() : String(value));
  return (
    <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '20px 22px' }}>
      {labelCol && r[labelCol] !== undefined && (
        <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 6, letterSpacing: '0.04em',
                      textTransform: 'uppercase' }}>
          {labelCol}: {String(r[labelCol])}
        </div>
      )}
      <div style={{ fontSize: 48, fontWeight: 600, color: T.text, fontFamily: T.mono, lineHeight: 1.1 }}>
        {display}
      </div>
      <div style={{ fontSize: 12, color: T.muted, marginTop: 4 }}>{valueCol}</div>
    </div>
  );
}

// v0.4.0: detail intent 服务端 CSV 导出（utf-8-sig BOM, Excel 直开）
async function exportMessageCsv(messageId) {
  try {
    const r = await fetch(`/api/messages/${messageId}/export.csv`, {
      headers: { Authorization: `Bearer ${api._token()}` },
    });
    if (!r.ok) {
      toast(`导出失败: ${r.status}`, true);
      return;
    }
    const blob = await r.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `export_msg${messageId}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } catch (e) {
    toast(`导出失败: ${e.message}`, true);
  }
}

function AgentThinkingPanel({ T, events, visible }) {
  if (!visible) return null;

  const AGENTS = [
    { key: 'clarifier',   label: '理解问题', emoji: '💡' },
    { key: 'sql_planner', label: '生成 SQL', emoji: '🔍' },
    { key: 'presenter',   label: '整理洞察', emoji: '📊' },
  ];

  const getStatus = (key) => {
    const started = events.some(e => e.type === 'agent_start' && e.agent === key);
    const done    = events.some(e => e.type === 'agent_done'  && e.agent === key);
    if (!started) return 'pending';
    return done ? 'done' : 'thinking';
  };

  const getDoneOutput = (key) => {
    const ev = events.find(e => e.type === 'agent_done' && e.agent === key);
    return ev?.output || null;
  };

  const sqlSteps = events.filter(e => e.type === 'sql_step');

  return (
    <aside style={{
      width: 272, flexShrink: 0, height: '100%', overflowY: 'auto',
      borderLeft: `1px solid ${T.border}`, background: T.sidebar,
      padding: '16px 12px', display: 'flex', flexDirection: 'column', gap: 8,
    }} className="cb-sb">
      <div style={{ fontSize: 11.5, fontWeight: 600, color: T.muted, letterSpacing: '0.05em',
                    textTransform: 'uppercase', marginBottom: 4 }}>思考过程</div>

      {AGENTS.map(({ key, label, emoji }) => {
        const status = getStatus(key);
        const output = getDoneOutput(key);
        const isPending  = status === 'pending';
        const isThinking = status === 'thinking';
        const isDone     = status === 'done';

        return (
          <div key={key} style={{
            background: T.card, borderRadius: 8,
            border: `1px solid ${isThinking ? T.accent + '60' : T.border}`,
            padding: '10px 12px', opacity: isPending ? 0.45 : 1,
            transition: 'all .2s',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: output || (isThinking && key === 'sql_planner') ? 6 : 0 }}>
              <span style={{ fontSize: 13 }}>{emoji}</span>
              <span style={{ fontSize: 12.5, fontWeight: 500, color: T.text, flex: 1 }}>{label}</span>
              {isDone     && <span style={{ fontSize: 10, color: T.success || '#09AB3B', fontWeight: 600 }}>✓</span>}
              {isThinking && <TypingDots color={T.accent}/>}
              {isPending  && <span style={{ fontSize: 10, color: T.muted }}>○</span>}
            </div>

            {key === 'clarifier' && isDone && output?.refined_question && (
              <div style={{ fontSize: 11.5, color: T.subtext, lineHeight: 1.55 }}>
                <div style={{ color: T.muted, fontSize: 10.5, marginBottom: 2 }}>精确问题</div>
                <div style={{ color: T.text }}>{output.refined_question}</div>
                {output.approach && <div style={{ color: T.muted, marginTop: 4, fontSize: 10.5 }}>{output.approach}</div>}
              </div>
            )}

            {key === 'sql_planner' && (isThinking || isDone) && sqlSteps.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {sqlSteps.map((s, i) => (
                  <div key={i} style={{ fontSize: 11, color: T.muted, lineHeight: 1.45,
                                        paddingLeft: 8, borderLeft: `2px solid ${T.border}` }}>
                    {s.step > 0 && <span style={{ color: T.accent, fontWeight: 600, marginRight: 4 }}>S{s.step}</span>}
                    {s.thought ? s.thought.slice(0, 80) : s.action}
                    {s.thought && s.thought.length > 80 ? '…' : ''}
                  </div>
                ))}
              </div>
            )}

            {key === 'presenter' && isDone && output?.insight && (
              <div style={{ fontSize: 11.5, color: T.subtext, lineHeight: 1.5 }}>
                {output.confidence && output.confidence !== 'high' && (
                  <span style={{
                    fontSize: 10.5, fontWeight: 600, padding: '1px 5px', borderRadius: 4, marginRight: 6,
                    background: output.confidence === 'medium' ? '#FF990022' : T.accentSoft,
                    color: output.confidence === 'medium' ? '#FF9900' : T.accent,
                  }}>{output.confidence}</span>
                )}
                {output.insight.slice(0, 100)}{output.insight.length > 100 ? '…' : ''}
              </div>
            )}
          </div>
        );
      })}
    </aside>
  );
}

function Composer({ T, value, onChange, loading, onSubmit, onKeyDown,
                   placeholder = '用中文提问…',
                   activeUpload, setActiveUpload, onUpload }) {
  const fileRef = useRef(null);

  const handleFile = (e) => {
    const f = e.target.files?.[0];
    if (f && onUpload) onUpload(f);
    e.target.value = '';
  };

  return (
    <div style={{ position: 'relative', width: '100%', maxWidth: 640 }}>
      {activeUpload && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6,
          padding: '5px 10px', background: T.accentSoft, borderRadius: 8,
          border: `1px solid ${T.accent}30`,
        }}>
          <I.file style={{ color: T.accent, flexShrink: 0 }}/>
          <span style={{ flex: 1, fontSize: 12, color: T.accent, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {activeUpload.filename} · {activeUpload.row_count} 行
          </span>
          <button onClick={() => setActiveUpload(null)} style={{ ...iconBtn(T), width: 18, height: 18, color: T.accent }}>
            <I.x width="10" height="10"/>
          </button>
        </div>
      )}
      <div style={{
        background: T.inputBg, border: `1px solid ${T.inputBorder}`,
        borderRadius: 14, padding: '12px 14px', width: '100%',
        boxShadow: '0 1px 2px rgba(0,0,0,0.03), 0 8px 24px -16px rgba(0,0,0,0.12)',
      }}>
        <textarea
          value={value} onChange={e => onChange(e.target.value)} onKeyDown={onKeyDown}
          placeholder={activeUpload ? `询问关于 ${activeUpload.filename} 的问题…` : placeholder} rows={1}
          style={{
            width: '100%', background: 'transparent', border: 'none', outline: 'none', resize: 'none',
            fontSize: 14, color: T.text, fontFamily: T.sans, lineHeight: 1.5, minHeight: 24, maxHeight: 120,
            overflow: 'auto',
          }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
          <div style={{ flex: 1 }}/>
          {onUpload && (
            <>
              <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" onChange={handleFile} style={{ display: 'none' }}/>
              <button onClick={() => fileRef.current?.click()} title="上传 CSV / Excel"
                style={{ ...iconBtn(T), color: activeUpload ? T.accent : T.muted }}>
                <I.clip/>
              </button>
            </>
          )}
          <button onClick={onSubmit} disabled={loading || !value.trim()} style={{
            width: 30, height: 30, borderRadius: 8, border: 'none',
            background: loading || !value.trim() ? T.muted : T.sendBg, color: T.sendFg,
            display: 'grid', placeItems: 'center', cursor: loading || !value.trim() ? 'not-allowed' : 'pointer',
          }}>
            {loading ? <Spinner size={12} color="#fff"/> : <I.send/>}
          </button>
        </div>
      </div>
    </div>
  );
}
