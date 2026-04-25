// app.jsx — BI-Agent production app (all screens, API, routing)

// ─── API client ───────────────────────────────────────────────────────────────
const api = {
  _token: () => localStorage.getItem('cb_token') || '',
  _h() { return { 'Content-Type': 'application/json', Authorization: `Bearer ${this._token()}` }; },
  async req(method, path, body) {
    const r = await fetch(path, {
      method, headers: this._h(),
      body: body ? JSON.stringify(body) : undefined,
    });
    if (r.status === 401) { localStorage.removeItem('cb_token'); window.location.reload(); return; }
    if (!r.ok) { const t = await r.text(); throw new Error(t || r.statusText); }
    if (r.status === 204) return {};
    return r.json();
  },
  get:    (p)    => api.req('GET',    p),
  post:   (p, b) => api.req('POST',   p, b),
  put:    (p, b) => api.req('PUT',    p, b),
  del:    (p)    => api.req('DELETE', p),
  login:  (u, p) => api.req('POST', '/api/auth/login', { username: u, password: p }),
  me:     ()     => api.get('/api/auth/me'),
};

// ─── Helpers ──────────────────────────────────────────────────────────────────
function useTheme() {
  const saved = localStorage.getItem('cb_theme');
  const [dark, setDark] = React.useState(saved ? saved === 'dark' : true);
  const toggle = () => { const nd = !dark; setDark(nd); localStorage.setItem('cb_theme', nd ? 'dark' : 'light'); };
  return [buildTheme(dark), toggle];
}

function usePersist(key, def) {
  const [v, set] = React.useState(() => { try { const s = localStorage.getItem(key); return s ? JSON.parse(s) : def; } catch { return def; } });
  const setP = nv => { set(nv); try { localStorage.setItem(key, JSON.stringify(nv)); } catch {} };
  return [v, setP];
}

function toast(msg, err = false) {
  const el = document.createElement('div');
  el.textContent = msg;
  Object.assign(el.style, {
    position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)',
    background: err ? '#FF4B4B' : '#09AB3B', color: '#fff',
    padding: '9px 18px', borderRadius: 8, fontSize: 13.5, fontFamily: 'inherit',
    boxShadow: '0 4px 20px rgba(0,0,0,0.2)', zIndex: 9999, animation: 'cb-fadein .3s ease',
  });
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

function Modal({ T, onClose, children, width = 480 }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(14,17,23,0.5)', backdropFilter: 'blur(2px)',
      display: 'grid', placeItems: 'center', zIndex: 1000,
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{
        width, background: T.content, borderRadius: 12, border: `1px solid ${T.border}`,
        boxShadow: '0 24px 60px -20px rgba(0,0,0,0.4)', overflow: 'hidden',
      }}>
        {children}
      </div>
    </div>
  );
}

function ModalHeader({ T, title, subtitle, onClose }) {
  return (
    <div style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: `1px solid ${T.border}` }}>
      <div>
        <div style={{ fontSize: 15, color: T.text, fontWeight: 600 }}>{title}</div>
        {subtitle && <div style={{ fontSize: 11.5, color: T.muted, marginTop: 2 }}>{subtitle}</div>}
      </div>
      <button onClick={onClose} style={iconBtn(T)}><I.x/></button>
    </div>
  );
}

function Input({ T, label, value, onChange, type = 'text', placeholder, mono, required, optional, trailing }) {
  const [show, setShow] = React.useState(false);
  const isPass = type === 'password';
  return (
    <div style={{ marginBottom: 12 }}>
      {label && (
        <div style={{ fontSize: 12, color: T.subtext, marginBottom: 5, fontWeight: 500, display: 'flex', gap: 4 }}>
          {label}
          {optional && <span style={{ fontSize: 10, color: T.muted, fontWeight: 400 }}>(可选)</span>}
          {required && <span style={{ color: T.accent }}>*</span>}
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 7 }}>
        <input
          type={isPass && !show ? 'password' : 'text'}
          value={value} onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          style={{
            flex: 1, background: 'transparent', border: 'none', outline: 'none',
            padding: '9px 11px', fontSize: 13, color: T.text,
            fontFamily: mono ? T.mono : T.sans,
          }}
        />
        {isPass && <button type="button" onClick={() => setShow(!show)} style={{ ...iconBtn(T), marginRight: 4 }}>{show ? <I.eyeoff/> : <I.eye/>}</button>}
        {trailing && <div style={{ paddingRight: 8 }}>{trailing}</div>}
      </div>
    </div>
  );
}

function Select({ T, label, value, onChange, options }) {
  return (
    <div style={{ marginBottom: 12 }}>
      {label && <div style={{ fontSize: 12, color: T.subtext, marginBottom: 5, fontWeight: 500 }}>{label}</div>}
      <select value={value} onChange={e => onChange(e.target.value)} style={{
        width: '100%', background: T.inputBg, border: `1px solid ${T.inputBorder}`,
        borderRadius: 7, padding: '9px 11px', fontSize: 13, color: T.text, cursor: 'pointer',
      }}>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

function Spinner({ size = 16, color = '#FF4B4B' }) {
  return <span style={{ display: 'inline-block', width: size, height: size, border: `2px solid ${color}30`, borderTopColor: color, borderRadius: '50%', animation: 'cb-spin 0.7s linear infinite' }}/>;
}

// ─── LOGIN ────────────────────────────────────────────────────────────────────
function LoginScreen({ T, onLogin, onToggleTheme }) {
  const [username, setUsername] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState('');
  const [showPw, setShowPw] = React.useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setLoading(true); setError('');
    try {
      const data = await api.login(username.trim(), password);
      localStorage.setItem('cb_token', data.token);
      onLogin(data.user);
    } catch (err) {
      setError('用户名或密码错误');
    } finally { setLoading(false); }
  };

  return (
    <div style={{
      width: '100vw', height: '100vh', display: 'flex',
      background: T.bg, color: T.text, fontFamily: T.sans, fontSize: 13.5,
    }}>
      <button onClick={onToggleTheme} style={{
        position: 'absolute', top: 20, right: 22,
        width: 32, height: 32, borderRadius: 8, background: T.content,
        border: `1px solid ${T.border}`, color: T.subtext,
        display: 'grid', placeItems: 'center', cursor: 'pointer',
      }}>{T.dark ? <I.sun/> : <I.moon/>}</button>

      {/* Left brand panel */}
      <div className="cb-grid-bg" style={{
        flex: 1, borderRight: `1px solid ${T.border}`,
        padding: '48px 60px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 30, height: 30, borderRadius: 8, background: T.accent, display: 'grid', placeItems: 'center', color: '#fff' }}><I.sparkle/></div>
          <span style={{ fontSize: 17, fontWeight: 600, letterSpacing: '-0.01em', color: T.text }}>BI-Agent</span>
          <span style={{ fontSize: 11, color: T.muted, padding: '2px 7px', background: T.chipBg, border: `1px solid ${T.border}`, borderRadius: 999, marginLeft: 4 }}>v 0.1</span>
        </div>

        <div>
          <div style={{ fontSize: 32, fontWeight: 600, color: T.text, lineHeight: 1.2, letterSpacing: '-0.02em', marginBottom: 14 }}>
            用自然语言<br/>查询你的业务数据
          </div>
          <div style={{ fontSize: 14, color: T.subtext, maxWidth: 360, lineHeight: 1.6 }}>
            用中文提问，自动生成 SQL、展示图表与数据洞察。
          </div>
          <div style={{ marginTop: 32, display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 360 }}>
            {['接入任意 MySQL 兼容数据库', '多模型支持（Claude / GPT / Gemini / DeepSeek）', '管理员统一管理账号与数据源'].map((t, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: T.subtext }}>
                <span style={{ width: 18, height: 18, borderRadius: '50%', background: T.accentSoft, color: T.accent, display: 'grid', placeItems: 'center', flexShrink: 0 }}><I.check width="10" height="10"/></span>
                {t}
              </div>
            ))}
          </div>
        </div>

        <div style={{ fontSize: 11, color: T.muted }}>© 2026 BI-Agent · 内部系统</div>
      </div>

      {/* Right form */}
      <div style={{ width: 420, flexShrink: 0, padding: '80px 48px', display: 'flex', flexDirection: 'column', justifyContent: 'center', background: T.content }}>
        <div style={{ fontSize: 22, fontWeight: 600, color: T.text, letterSpacing: '-0.015em', marginBottom: 6 }}>欢迎回来</div>
        <div style={{ fontSize: 13, color: T.muted, marginBottom: 26 }}>使用你的账号登录 BI-Agent</div>

        <form onSubmit={submit}>
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 12, color: T.subtext, marginBottom: 5, fontWeight: 500 }}>账号</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 7, padding: '9px 11px' }}>
              <I.user style={{ color: T.muted, flexShrink: 0 }}/>
              <input autoFocus value={username} onChange={e => setUsername(e.target.value)}
                placeholder="用户名" type="text" style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', fontSize: 13, color: T.text, fontFamily: T.sans }}/>
            </div>
          </div>
          <div style={{ marginBottom: 18 }}>
            <div style={{ fontSize: 12, color: T.subtext, marginBottom: 5, fontWeight: 500 }}>密码</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 7, padding: '9px 11px' }}>
              <I.lock style={{ color: T.muted, flexShrink: 0 }}/>
              <input value={password} onChange={e => setPassword(e.target.value)}
                placeholder="••••••••" type={showPw ? 'text' : 'password'}
                style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', fontSize: 13, color: T.text, fontFamily: T.sans }}/>
              <button type="button" onClick={() => setShowPw(!showPw)} style={{ ...iconBtn(T), width: 20, height: 20 }}>{showPw ? <I.eyeoff/> : <I.eye/>}</button>
            </div>
          </div>
          {error && <div style={{ color: T.accent, fontSize: 12.5, marginBottom: 12, padding: '8px 12px', background: T.accentSoft, borderRadius: 6 }}>{error}</div>}
          <button type="submit" disabled={loading} style={{
            width: '100%', padding: '11px 14px', border: 'none', borderRadius: 8,
            background: loading ? T.muted : T.accent, color: '#fff', fontFamily: 'inherit',
            fontSize: 13.5, fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
          }}>
            {loading ? <><Spinner size={14} color="#fff"/> 登录中…</> : '登录'}
          </button>
        </form>

        <div style={{ marginTop: 22, fontSize: 11, color: T.muted, textAlign: 'center' }}>
          内部系统 · 账号由管理员分配
        </div>
      </div>
    </div>
  );
}

// ─── CHAT ─────────────────────────────────────────────────────────────────────
// ─── Schema Panel ─────────────────────────────────────────────────────────────
function SchemaPanel({ T, tables, onInsert }) {
  const [expanded, setExpanded] = React.useState({});
  const [search, setSearch] = React.useState('');
  const toggle = (name) => setExpanded(prev => ({ ...prev, [name]: !prev[name] }));
  const filtered = tables.filter(t =>
    !search || t.name.toLowerCase().includes(search.toLowerCase()) ||
    t.columns.some(c => c.name.toLowerCase().includes(search.toLowerCase()))
  );
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1, minHeight: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 6, padding: '5px 8px', marginBottom: 4, gap: 6 }}>
        <I.search style={{ color: T.muted, flexShrink: 0 }}/>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索表/字段…"
          style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', fontSize: 12, color: T.text, fontFamily: 'inherit' }}/>
      </div>
      {filtered.length === 0 && (
        <div style={{ fontSize: 12, color: T.muted, padding: '8px 4px' }}>
          {tables.length === 0 ? '暂无表结构' : '无匹配结果'}
        </div>
      )}
      <div className="cb-sb" style={{ overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: 1 }}>
        {filtered.map(t => (
          <div key={t.name}>
            <div onClick={() => toggle(t.name)} style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '5px 6px',
              borderRadius: 5, cursor: 'pointer', color: T.subtext, fontSize: 12.5,
              background: expanded[t.name] ? T.accentSoft : 'transparent',
            }}>
              <I.chev style={{ transform: expanded[t.name] ? 'rotate(180deg)' : 'rotate(-90deg)', transition: 'transform .15s', color: T.muted, flexShrink: 0 }}/>
              <I.db style={{ color: expanded[t.name] ? T.accent : T.muted, flexShrink: 0 }}/>
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: expanded[t.name] ? T.accent : T.subtext, fontWeight: expanded[t.name] ? 500 : 400 }}>{t.name}</span>
              <button onClick={e => { e.stopPropagation(); onInsert(t.name); }} title="插入到问题"
                style={{ ...iconBtn(T), width: 18, height: 18, opacity: 0.5, fontSize: 10 }}>+</button>
            </div>
            {expanded[t.name] && (
              <div style={{ paddingLeft: 20, paddingBottom: 2 }}>
                {t.columns.map(c => (
                  <div key={c.name} onClick={() => onInsert(`${t.name}.${c.name}`)}
                    style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '3px 6px', borderRadius: 4, cursor: 'pointer', color: T.muted, fontSize: 11.5 }}
                    onMouseEnter={e => e.currentTarget.style.background = T.hover}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}>{c.name}</span>
                      {c.comment && <span style={{ fontSize: 10, color: T.accent, opacity: 0.8, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.comment}</span>}
                    </div>
                    <span style={{ fontSize: 10, color: T.muted, fontFamily: T.mono, opacity: 0.6, flexShrink: 0 }}>{c.type.split('(')[0]}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function ChatScreen({ T, user, onToggleTheme, onNavigate, onLogout }) {
  const [convs, setConvs] = React.useState([]);
  const [activeConvId, setActiveConvId] = usePersist('cb_conv', null);
  const [messages, setMessages] = React.useState([]);
  const [question, setQuestion] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [dbOk, setDbOk] = React.useState(null);
  const [useAgent, setUseAgent] = React.useState(false);
  const [agentEvents, setAgentEvents] = React.useState([]);
  const [sidebarTab, setSidebarTab] = React.useState('history');
  const [schema, setSchema] = React.useState([]);
  const [activeUpload, setActiveUpload] = React.useState(null);
  const scrollRef = React.useRef(null);

  React.useEffect(() => { loadConvs(); checkDb(); loadSchema(); }, []);
  React.useEffect(() => { if (activeConvId) loadMessages(activeConvId); else setMessages([]); }, [activeConvId]);
  React.useEffect(() => { if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight; }, [messages]);

  const loadConvs = async () => {
    try { const d = await api.get('/api/conversations'); setConvs(d); } catch {}
  };
  const checkDb = async () => {
    try { const d = await api.get('/api/db/status'); setDbOk(d.connected); } catch { setDbOk(false); }
  };
  const loadMessages = async (cid) => {
    try { const d = await api.get(`/api/conversations/${cid}/messages`); setMessages(d); } catch {}
  };
  const loadSchema = async () => {
    try { const d = await api.get('/api/db/schema'); setSchema(d.tables || []); } catch {}
  };

  const newChat = async () => {
    try {
      const d = await api.post('/api/conversations', { title: '新对话' });
      setConvs(prev => [d, ...prev]);
      setActiveConvId(d.id);
      setMessages([]);
    } catch (e) { toast('创建对话失败', true); }
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
    if (!activeConvId) { await newChat(); return; }

    const q = question.trim();
    setQuestion('');
    setLoading(true);
    setAgentEvents([]);

    const tempId = Date.now();
    const tempMsg = { id: tempId, question: q, sql: '', rows: [], explanation: '', confidence: '', error: '', loading: true };
    setMessages(prev => [...prev, tempMsg]);

    if (!useAgent) {
      // Non-agent path: simple synchronous call
      try {
        const body = { question: q };
        if (activeUpload) body.upload_id = activeUpload.id;
        const d = await api.post(`/api/conversations/${activeConvId}/query`, body);
        setMessages(prev => prev.map(m => m.id === tempId ? { ...d, loading: false } : m));
        loadConvs();
      } catch (err) {
        setMessages(prev => prev.map(m => m.id === tempId ? { ...m, loading: false, error: String(err) } : m));
      } finally { setLoading(false); }
      return;
    }

    // Multi-agent SSE path
    try {
      const body = { question: q };
      if (activeUpload) body.upload_id = activeUpload.id;

      const resp = await fetch(`/api/conversations/${activeConvId}/query-stream`, {
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
            setAgentEvents(prev => [...prev, ev]);
          }
          if (ev.type === 'clarification_needed') {
            setAgentEvents(prev => [...prev, ev]);
            setMessages(prev => prev.map(m => m.id === tempId ? {
              id: ev.message_id, question: q,
              explanation: ev.question, is_clarification: true,
              sql: '', rows: [], confidence: 'low', error: '',
              input_tokens: ev.input_tokens, output_tokens: ev.output_tokens,
              cost_usd: ev.cost_usd, loading: false,
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
    <div key={c.id} onClick={() => { setActiveConvId(c.id); }} style={{
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
      <div style={{ display: 'flex', gap: 2, marginBottom: 8 }}>
        {[['history', <I.history/>, '历史'], ['schema', <I.db/>, '表结构']].map(([tab, icon, label]) => (
          <button key={tab} onClick={() => setSidebarTab(tab)} style={{
            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
            padding: '5px 0', borderRadius: 6, fontFamily: 'inherit', fontSize: 11.5, cursor: 'pointer',
            background: sidebarTab === tab ? T.accentSoft : 'transparent',
            color: sidebarTab === tab ? T.accent : T.muted,
            border: `1px solid ${sidebarTab === tab ? T.accent + '40' : T.border}`,
          }}>{icon} {label}</button>
        ))}
      </div>
      {sidebarTab === 'history'
        ? <div className="cb-sb" style={{ display: 'flex', flexDirection: 'column', gap: 1, flex: 1, overflowY: 'auto', minHeight: 0 }}>{convList}</div>
        : <SchemaPanel T={T} tables={schema} onInsert={(txt) => setQuestion(q => q ? q + ' ' + txt : txt)}/>
      }
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
        ? <ChatEmpty T={T} user={user} onSend={(q) => { setQuestion(q); }} onNewChat={newChat}
                     hasConv={!!activeConvId} question={question} setQuestion={setQuestion}
                     loading={loading} onSubmit={sendQuery} onKeyDown={handleKeyDown}
                     useAgent={useAgent} setUseAgent={setUseAgent}
                     activeUpload={activeUpload} setActiveUpload={setActiveUpload} onUpload={handleUpload}/>
        : <ChatConversation T={T} messages={messages} scrollRef={scrollRef} loading={loading}
                            question={question} setQuestion={setQuestion}
                            onSubmit={sendQuery} onKeyDown={handleKeyDown}
                            onCopy={copyToClipboard} onDownload={downloadCSV}
                            useAgent={useAgent} setUseAgent={setUseAgent}
                            agentEvents={agentEvents}
                            activeUpload={activeUpload} setActiveUpload={setActiveUpload} onUpload={handleUpload}/>
      }
    </AppShell>
  );
}

function ChatEmpty({ T, user, question, setQuestion, loading, onSubmit, onKeyDown, useAgent, setUseAgent, activeUpload, setActiveUpload, onUpload }) {
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
                useAgent={useAgent} setUseAgent={setUseAgent}
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

function ChatConversation({ T, messages, scrollRef, loading, question, setQuestion, onSubmit, onKeyDown, onCopy, onDownload, useAgent, setUseAgent, agentEvents, activeUpload, setActiveUpload, onUpload }) {
  const showPanel = useAgent && agentEvents.length > 0;
  return (
    <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
      {/* Main chat area */}
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
                                   onFollowup={(q) => { setQuestion(q); }}/>}
                </div>
              </div>
            </div>
          ))}
        </div>
        <div style={{ padding: '10px 28px 18px', background: `linear-gradient(to top, ${T.content} 80%, ${T.content}00)` }}>
          <div style={{ maxWidth: 800, margin: '0 auto' }}>
            <Composer T={T} value={question} onChange={setQuestion} loading={loading}
                      onSubmit={onSubmit} onKeyDown={onKeyDown}
                      useAgent={useAgent} setUseAgent={setUseAgent}
                      activeUpload={activeUpload} setActiveUpload={setActiveUpload} onUpload={onUpload}
                      placeholder="继续追问…"/>
          </div>
        </div>
      </div>
      {/* Right: Agent Thinking Panel */}
      {useAgent && <AgentThinkingPanel T={T} events={agentEvents} visible={showPanel}/>}
    </div>
  );
}

function ThinkingCard({ T, agentEvents = [] }) {
  const AGENT_LABELS = { clarifier: '理解问题', sql_planner: '生成 SQL', validator: '验证结果', presenter: '整理洞察' };
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

function ResultBlock({ T, msg, onCopy, onDownload, onFollowup }) {
  const [sqlOpen, setSqlOpen] = React.useState(false);
  const [chartType, setChartType] = React.useState('auto');
  const { sql, rows, explanation, confidence, error, input_tokens, output_tokens, cost_usd, retry_count, query_time_ms,
          insight, suggested_followups, is_clarification } = msg;

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

  const isDateLike = chartable && rows.some(r => /\d{4}[-/年]\d/.test(String(r[labelCols[0]] || '')));
  const autoType = (() => {
    if (!chartable) return 'bar';
    if (isDateLike || rows.length > 12) return 'line';
    if (numericCols.length === 1 && rows.length <= 10) return 'pie';
    return 'bar';
  })();

  const activeType = chartType === 'auto' ? autoType : chartType;

  // Include all numeric cols for multi-series; pie uses only first numeric col
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {explanation && <div style={{ fontSize: 13.5, color: T.text, lineHeight: 1.65 }}>{explanation}</div>}
      {error && <div style={{ padding: '8px 12px', background: T.accentSoft, borderRadius: 6, color: T.accent, fontSize: 12.5 }}>{error}</div>}

      {rows && rows.length > 0 && (
        <>
          {chartable && (
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
              <button onClick={() => onDownload(rows, msg.question)} style={{ ...iconBtn(T), gap: 4, fontSize: 11 }} title="下载 CSV"><I.dl/></button>
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
        <div style={{ display: 'flex', gap: 12, fontSize: 11, color: T.muted, fontFamily: T.mono }}>
          <span>↑ {input_tokens?.toLocaleString()} tok</span>
          <span>↓ {output_tokens?.toLocaleString()} tok</span>
          {cost_usd > 0 && <span>$ {cost_usd?.toFixed(5)}</span>}
          {confidence && <span style={{ color: confidence === 'high' ? T.success : confidence === 'medium' ? T.warn : T.accent }}>{confidence}</span>}
        </div>
      )}
    </div>
  );
}

// ─── AGENT THINKING PANEL ─────────────────────────────────────────────────────
function AgentThinkingPanel({ T, events, visible }) {
  if (!visible) return null;

  const AGENTS = [
    { key: 'clarifier',   label: '理解问题', emoji: '💡' },
    { key: 'sql_planner', label: '生成 SQL', emoji: '🔍' },
    { key: 'validator',   label: '验证结果', emoji: '✓' },
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

            {/* Clarifier output */}
            {key === 'clarifier' && isDone && output?.refined_question && (
              <div style={{ fontSize: 11.5, color: T.subtext, lineHeight: 1.55 }}>
                <div style={{ color: T.muted, fontSize: 10.5, marginBottom: 2 }}>精确问题</div>
                <div style={{ color: T.text }}>{output.refined_question}</div>
                {output.approach && <div style={{ color: T.muted, marginTop: 4, fontSize: 10.5 }}>{output.approach}</div>}
              </div>
            )}

            {/* SQL Planner steps */}
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

            {/* Validator output */}
            {key === 'validator' && isDone && output && (
              <div style={{ fontSize: 11.5, color: T.subtext }}>
                <span style={{
                  fontSize: 10.5, fontWeight: 600, padding: '1px 5px', borderRadius: 4,
                  background: output.confidence === 'high' ? '#09AB3B22' : output.confidence === 'medium' ? '#FF990022' : T.accentSoft,
                  color: output.confidence === 'high' ? '#09AB3B' : output.confidence === 'medium' ? '#FF9900' : T.accent,
                }}>{output.confidence}</span>
                {output.notes && <span style={{ marginLeft: 6 }}>{output.notes}</span>}
              </div>
            )}

            {/* Presenter output */}
            {key === 'presenter' && isDone && output?.insight && (
              <div style={{ fontSize: 11.5, color: T.subtext, lineHeight: 1.5 }}>
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
                   useAgent, setUseAgent, activeUpload, setActiveUpload, onUpload }) {
  const fileRef = React.useRef(null);

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
          <label style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', fontSize: 11.5, color: T.muted, userSelect: 'none' }}>
            <div style={{
              width: 28, height: 15, borderRadius: 999, background: useAgent ? T.accent : T.border, position: 'relative', transition: 'background .15s', flexShrink: 0,
            }} onClick={() => setUseAgent(!useAgent)}>
              <span style={{ position: 'absolute', top: 1.5, left: useAgent ? 14 : 1.5, width: 12, height: 12, borderRadius: '50%', background: '#fff', transition: 'left .15s' }}/>
            </div>
            多Agent
          </label>
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

// ─── ADMIN ────────────────────────────────────────────────────────────────────
function AdminScreen({ T, user, onToggleTheme, onNavigate, onLogout, screen: screenProp, initialTab = 'users' }) {
  const [tab, setTab] = React.useState(initialTab);
  const [users, setUsers] = React.useState([]);
  const [sources, setSources] = React.useState([]);
  const [models, setModels] = React.useState([]);
  const [knowledgeDocs, setKnowledgeDocs] = React.useState([]);
  const [stats, setStats] = React.useState({});
  const [modal, setModal] = React.useState(null);
  const [kbUploading, setKbUploading] = React.useState(false);
  const kbFileRef = React.useRef(null);

  React.useEffect(() => { setTab(initialTab); }, [initialTab]);
  React.useEffect(() => { loadAll(); }, [tab]);

  const loadAll = async () => {
    try {
      if (tab === 'users') { const [d, s] = await Promise.all([api.get('/api/admin/users'), api.get('/api/admin/datasources')]); setUsers(d); setSources(s); }
      if (tab === 'sources') { const d = await api.get('/api/admin/datasources'); setSources(d); }
      if (tab === 'models') { const d = await api.get('/api/admin/models'); setModels(d); }
      if (tab === 'knowledge') { const d = await api.get('/api/knowledge'); setKnowledgeDocs(d); }
      const s = await api.get('/api/admin/stats'); setStats(s);
    } catch {}
  };

  const handleKbUpload = async (file) => {
    setKbUploading(true);
    const fd = new FormData();
    fd.append('file', file);
    try {
      const r = await fetch('/api/knowledge/upload', {
        method: 'POST', headers: { Authorization: `Bearer ${api._token()}` }, body: fd,
      });
      if (!r.ok) throw new Error(await r.text());
      const d = await r.json();
      toast(`已上传「${d.name}」· ${d.chunk_count} 块${d.embedded_count < d.chunk_count ? '（部分未 embedding，将使用关键词检索）' : ''}`);
      loadAll();
    } catch (e) { toast(`上传失败: ${e.message}`, true); }
    finally { setKbUploading(false); }
  };

  const deleteKbDoc = async (id, name) => {
    if (!confirm(`删除「${name}」？`)) return;
    try { await api.del(`/api/knowledge/${id}`); loadAll(); toast('已删除'); }
    catch (e) { toast(String(e), true); }
  };

  const deleteUser = async (id) => {
    if (!confirm('停用该账号？')) return;
    try { await api.del(`/api/admin/users/${id}`); loadAll(); toast('已停用'); } catch (e) { toast(String(e), true); }
  };
  const deleteSrc = async (id) => {
    if (!confirm('删除该数据源？')) return;
    try { await api.del(`/api/admin/datasources/${id}`); loadAll(); toast('已删除'); } catch (e) { toast(String(e), true); }
  };
  const toggleModel = async (key) => {
    try { await api.post(`/api/admin/models/${key}/toggle`); loadAll(); } catch (e) { toast(String(e), true); }
  };
  const setDefaultModel = async (key) => {
    try { await api.post(`/api/admin/models/${key}/default`); loadAll(); toast('已设为默认'); } catch (e) { toast(String(e), true); }
  };

  const TAB_TITLES = { users: '用户', sources: '数据源', models: '模型库', knowledge: '知识库' };

  const roleChip = (role) => {
    const map = { admin: ['#FF4B4B', 'rgba(255,75,75,0.12)'], analyst: ['#2B7FFF', 'rgba(43,127,255,0.12)'], viewer: ['#8A8D94', 'rgba(0,0,0,0.06)'] };
    const [c, bg] = map[role] || [T.muted, T.hover];
    return <span style={{ fontSize: 10.5, padding: '2px 7px', borderRadius: 999, background: bg, color: c, fontWeight: 600 }}>{role}</span>;
  };

  return (
    <AppShell T={T} user={user} active={screenProp || `admin-${tab}`} topbarTitle={TAB_TITLES[tab] || '管理员'}
              showConnectionPill={false}
              topbarTrailing={
                tab === 'users' ? <button onClick={() => setModal({ type: 'user' })} style={{ ...pillBtn(T, true), padding: '6px 12px' }}><I.plus width="13" height="13"/> 新建账号</button>
                : tab === 'sources' ? <button onClick={() => setModal({ type: 'source' })} style={{ ...pillBtn(T, true), padding: '6px 12px' }}><I.plus width="13" height="13"/> 添加数据源</button>
                : tab === 'knowledge' ? (
                  <>
                    <input ref={kbFileRef} type="file" accept=".pdf,.md,.markdown,.txt" style={{ display: 'none' }}
                      onChange={e => { const f = e.target.files?.[0]; if (f) handleKbUpload(f); e.target.value = ''; }}/>
                    <button onClick={() => kbFileRef.current?.click()} disabled={kbUploading}
                      style={{ ...pillBtn(T, true), padding: '6px 12px' }}>
                      {kbUploading ? <><Spinner size={11} color="#fff"/> 处理中…</> : <><I.plus width="13" height="13"/> 上传文档</>}
                    </button>
                  </>
                ) : null
              }
              onToggleTheme={onToggleTheme} onNewChat={() => {}} onNavigate={onNavigate} onLogout={onLogout}>
      <div className="cb-sb" style={{ flex: 1, overflowY: 'auto', padding: '22px 28px' }}>

        {/* Users */}
        {tab === 'users' && (
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 0.8fr 0.8fr 80px', padding: '9px 16px', background: T.bg, fontSize: 11, color: T.muted, fontWeight: 600, letterSpacing: '0.03em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>
              <div>用户</div><div>账号</div><div>角色</div><div>状态</div><div></div>
            </div>
            {users.map((u, i) => (
              <div key={u.id} style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 0.8fr 0.8fr 80px', padding: '11px 16px', borderBottom: i < users.length - 1 ? `1px solid ${T.borderSoft}` : 'none', alignItems: 'center', fontSize: 12.5 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                  <div style={{ width: 26, height: 26, borderRadius: '50%', background: `linear-gradient(135deg, ${T.accent}, #ff7a3a)`, color: '#fff', display: 'grid', placeItems: 'center', fontSize: 10.5, fontWeight: 600, flexShrink: 0 }}>
                    {(u.display_name || u.username || '?').slice(0, 1).toUpperCase()}
                  </div>
                  <span style={{ color: T.text, fontWeight: 500 }}>{u.display_name || u.username}</span>
                </div>
                <div style={{ color: T.subtext, fontFamily: T.mono, fontSize: 11.5 }}>{u.username}</div>
                <div>{roleChip(u.role)}</div>
                <div style={{ fontSize: 11.5, color: u.is_active ? T.success : T.muted }}>{u.is_active ? '正常' : '已停用'}</div>
                <div style={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
                  <button onClick={() => setModal({ type: 'user', data: u })} style={iconBtn(T)} title="编辑"><I.pencil/></button>
                  <button onClick={() => deleteUser(u.id)} style={iconBtn(T)} title="停用"><I.trash/></button>
                </div>
              </div>
            ))}
            {users.length === 0 && <div style={{ padding: '24px', textAlign: 'center', color: T.muted }}>暂无用户</div>}
          </div>
        )}

        {/* Sources */}
        {tab === 'sources' && (
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr 1.6fr 0.8fr 80px', padding: '9px 16px', background: T.bg, fontSize: 11, color: T.muted, fontWeight: 600, letterSpacing: '0.03em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>
              <div>名称</div><div>类型</div><div>主机</div><div>状态</div><div></div>
            </div>
            {sources.map((s, i) => (
              <div key={s.id} style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr 1.6fr 0.8fr 80px', padding: '11px 16px', borderBottom: i < sources.length - 1 ? `1px solid ${T.borderSoft}` : 'none', alignItems: 'center', fontSize: 12.5 }}>
                <div style={{ color: T.text, fontWeight: 500, fontFamily: T.mono }}>{s.name}</div>
                <div style={{ color: T.subtext }}>{s.db_type || 'doris'}</div>
                <div style={{ color: T.muted, fontFamily: T.mono, fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.db_host}:{s.db_port}/{s.db_database}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: s.status === 'online' ? T.success : T.warn }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: s.status === 'online' ? T.success : T.warn }}/>
                  <span style={{ fontSize: 11.5 }}>{s.status === 'online' ? '正常' : '异常'}</span>
                </div>
                <div style={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
                  <button onClick={() => setModal({ type: 'source', data: s })} style={iconBtn(T)} title="编辑"><I.pencil/></button>
                  <button onClick={() => deleteSrc(s.id)} style={iconBtn(T)} title="删除"><I.trash/></button>
                </div>
              </div>
            ))}
            {sources.length === 0 && <div style={{ padding: '24px', textAlign: 'center', color: T.muted }}>暂无数据源</div>}
          </div>
        )}

        {/* Models */}
        {tab === 'models' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 0.7fr 1.4fr 1fr 0.7fr 100px', padding: '9px 16px', background: T.bg, fontSize: 11, color: T.muted, fontWeight: 600, letterSpacing: '0.03em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>
                <div>名称</div><div>提供方</div><div>Model ID</div><div>单价(入/出)</div><div>状态</div><div></div>
              </div>
              {models.map((m, i) => (
                <div key={m.id} style={{ display: 'grid', gridTemplateColumns: '1.5fr 0.7fr 1.4fr 1fr 0.7fr 100px', padding: '11px 16px', borderBottom: i < models.length - 1 ? `1px solid ${T.borderSoft}` : 'none', alignItems: 'center', fontSize: 12.5, opacity: m.enabled ? 1 : 0.55 }}>
                  <div>
                    <span style={{ color: T.text, fontWeight: 500 }}>{m.name}</span>
                    {m.is_default ? <span style={{ marginLeft: 6, fontSize: 9.5, padding: '1px 5px', borderRadius: 3, background: T.accentSoft, color: T.accent, fontWeight: 600 }}>默认</span> : null}
                  </div>
                  <div style={{ color: T.subtext }}>{m.provider}</div>
                  <div style={{ color: T.muted, fontFamily: T.mono, fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.model_id}</div>
                  <div style={{ color: T.subtext, fontFamily: T.mono, fontSize: 11 }}>${m.input_price}/{m.output_price}</div>
                  <div>
                    <span style={{ fontSize: 11.5, color: m.enabled ? T.success : T.muted }}>{m.enabled ? '启用' : '禁用'}</span>
                  </div>
                  <div style={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
                    <button onClick={() => setDefaultModel(m.id)} style={iconBtn(T)} title="设为默认"><I.check/></button>
                    <button onClick={() => toggleModel(m.id)} style={iconBtn(T)} title="启用/禁用"><I.zap/></button>
                  </div>
                </div>
              ))}
            </div>

          </div>
        )}

        {/* Knowledge */}
        {tab === 'knowledge' && (
          <div>
            <div style={{ fontSize: 12, color: T.muted, marginBottom: 14, lineHeight: 1.6 }}>
              上传业务文档（PDF / Markdown / TXT），每次 SQL 查询时自动检索相关片段注入 prompt，提升生成准确度。<br/>
              需要 OpenAI 或 OpenRouter API Key 才能使用向量检索；无 Key 时自动降级为关键词匹配。
            </div>
            {knowledgeDocs.length === 0 ? (
              <div style={{ padding: '40px 24px', textAlign: 'center', color: T.muted, background: T.card, borderRadius: 10, border: `1px solid ${T.border}` }}>
                暂无文档 · 点击右上角「上传文档」添加
              </div>
            ) : (
              <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1.8fr 1fr 0.8fr 0.8fr 60px', padding: '9px 16px', background: T.bg, fontSize: 11, color: T.muted, fontWeight: 600, letterSpacing: '0.03em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>
                  <div>文档名称</div><div>文件名</div><div>分块数</div><div>上传时间</div><div></div>
                </div>
                {knowledgeDocs.map((d, i) => (
                  <div key={d.id} style={{ display: 'grid', gridTemplateColumns: '1.8fr 1fr 0.8fr 0.8fr 60px', padding: '11px 16px', borderBottom: i < knowledgeDocs.length - 1 ? `1px solid ${T.borderSoft}` : 'none', alignItems: 'center', fontSize: 12.5 }}>
                    <div style={{ color: T.text, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.name}</div>
                    <div style={{ color: T.muted, fontFamily: T.mono, fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.filename}</div>
                    <div style={{ color: T.subtext, fontFamily: T.mono }}>{d.chunk_count}</div>
                    <div style={{ color: T.muted, fontSize: 11 }}>{d.created_at?.slice(0, 10)}</div>
                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                      <button onClick={() => deleteKbDoc(d.id, d.name)} style={iconBtn(T)} title="删除"><I.trash/></button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Modals */}
      {modal?.type === 'user' && <UserFormModal T={T} data={modal.data} sources={sources} onClose={() => setModal(null)} onSave={loadAll}/>}
      {modal?.type === 'source' && <SourceFormModal T={T} data={modal.data} onClose={() => setModal(null)} onSave={loadAll}/>}
    </AppShell>
  );
}

function UserFormModal({ T, data, sources, onClose, onSave }) {
  const isEdit = !!data;
  const [form, setForm] = React.useState({
    username: data?.username || '',
    password: '',
    display_name: data?.display_name || '',
    role: data?.role || 'analyst',
    source_ids: new Set(data?.source_ids?.map(Number) || []),
  });
  const [loading, setLoading] = React.useState(false);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const toggleSource = (id) => {
    const next = new Set(form.source_ids);
    next.has(id) ? next.delete(id) : next.add(id);
    set('source_ids', next);
  };

  const submit = async () => {
    if (!isEdit && (!form.username.trim() || !form.password)) { toast('账号和密码必填', true); return; }
    setLoading(true);
    try {
      const source_ids = [...form.source_ids];
      if (isEdit) {
        const up = { source_ids };
        if (form.display_name) up.display_name = form.display_name;
        if (form.role) up.role = form.role;
        if (form.password) up.password = form.password;
        await api.put(`/api/admin/users/${data.id}`, up);
      } else {
        const body = { username: form.username, password: form.password, display_name: form.display_name, role: form.role };
        await api.post('/api/admin/users', body);
        const users = await api.get('/api/admin/users');
        const created = users.find(u => u.username === form.username);
        if (created && source_ids.length) await api.put(`/api/admin/users/${created.id}`, { source_ids });
      }
      toast(isEdit ? '已更新' : '已创建');
      onSave(); onClose();
    } catch (e) { toast(String(e), true); }
    finally { setLoading(false); }
  };

  return (
    <Modal T={T} onClose={onClose} width={500}>
      <ModalHeader T={T} title={isEdit ? '编辑账号' : '新建账号'} onClose={onClose}/>
      <div style={{ padding: '16px 20px', maxHeight: '70vh', overflowY: 'auto' }} className="cb-sb">
        <Input T={T} label="账号" value={form.username} onChange={v => set('username', v)} required={!isEdit} placeholder="username"/>
        <Input T={T} label={isEdit ? '新密码（留空不修改）' : '密码'} value={form.password} onChange={v => set('password', v)} type="password" required={!isEdit} placeholder="••••••••"/>
        <Input T={T} label="显示名称" value={form.display_name} onChange={v => set('display_name', v)} placeholder="张三" optional/>
        <Select T={T} label="角色" value={form.role} onChange={v => set('role', v)} options={[{ value: 'analyst', label: 'analyst — 分析师' }, { value: 'admin', label: 'admin — 管理员' }, { value: 'viewer', label: 'viewer — 只读' }]}/>
        <div style={{ height: 1, background: T.border, margin: '12px 0' }}/>
        <div style={{ fontSize: 12, color: T.muted, marginBottom: 8 }}>数据源（可多选，查询时自动合并表结构）</div>
        {(sources || []).length === 0
          ? <div style={{ fontSize: 12, color: T.muted }}>暂无数据源，请先在「数据源」标签页创建</div>
          : <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {(sources || []).map(s => {
                const checked = form.source_ids.has(s.id);
                return (
                  <label key={s.id} onClick={() => toggleSource(s.id)} style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px',
                    borderRadius: 7, cursor: 'pointer',
                    background: checked ? T.accentSoft : T.content,
                    border: `1px solid ${checked ? T.accent : T.border}`,
                  }}>
                    <span style={{ width: 15, height: 15, borderRadius: 3, flexShrink: 0, border: `1.5px solid ${checked ? T.accent : T.border}`, background: checked ? T.accent : 'transparent', display: 'grid', placeItems: 'center' }}>
                      {checked && <span style={{ color: '#fff', fontSize: 10, fontWeight: 700 }}>✓</span>}
                    </span>
                    <span style={{ fontSize: 13, color: T.text, flex: 1 }}>{s.name}</span>
                    <span style={{ fontSize: 11, color: T.muted, fontFamily: T.mono }}>{s.db_database}</span>
                  </label>
                );
              })}
            </div>
        }
      </div>
      <div style={{ padding: '12px 20px', borderTop: `1px solid ${T.border}`, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={onClose} style={pillBtn(T)}>取消</button>
        <button onClick={submit} disabled={loading} style={pillBtn(T, true)}>
          {loading ? <Spinner size={12} color="#fff"/> : '保存'}
        </button>
      </div>
    </Modal>
  );
}

function SourceFormModal({ T, data, onClose, onSave }) {
  const isEdit = !!data;
  const [form, setForm] = React.useState({
    name: data?.name || '',
    description: data?.description || '',
    db_host: data?.db_host || '',
    db_port: data?.db_port || 9030,
    db_user: data?.db_user || '',
    db_password: '',
    db_database: data?.db_database || '',
    db_type: data?.db_type || 'doris',
  });
  const [loading, setLoading] = React.useState(false);
  const [testing, setTesting] = React.useState(false);
  const [testResult, setTestResult] = React.useState(null);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const testConn = async () => {
    setTesting(true); setTestResult(null);
    try {
      const d = await api.post('/api/db/test', form);
      setTestResult(d);
    } catch (e) { setTestResult({ connected: false, message: String(e) }); }
    finally { setTesting(false); }
  };

  const submit = async () => {
    if (!form.name.trim() || !form.db_host.trim()) { toast('名称和主机必填', true); return; }
    setLoading(true);
    try {
      const body = { ...form, db_port: Number(form.db_port) };
      if (isEdit) await api.put(`/api/admin/datasources/${data.id}`, body);
      else await api.post('/api/admin/datasources', body);
      toast(isEdit ? '已更新' : '已添加');
      onSave(); onClose();
    } catch (e) { toast(String(e), true); }
    finally { setLoading(false); }
  };

  return (
    <Modal T={T} onClose={onClose} width={480}>
      <ModalHeader T={T} title={isEdit ? '编辑数据源' : '添加数据源'} onClose={onClose}/>
      <div style={{ padding: '16px 20px', maxHeight: '70vh', overflowY: 'auto' }} className="cb-sb">
        <Input T={T} label="名称" value={form.name} onChange={v => set('name', v)} required placeholder="trading_core"/>
        <Input T={T} label="说明" value={form.description} onChange={v => set('description', v)} optional placeholder="交易核心库"/>
        <Select T={T} label="数据库类型" value={form.db_type} onChange={v => set('db_type', v)} options={[{ value: 'doris', label: 'Apache Doris' }, { value: 'mysql', label: 'MySQL' }, { value: 'clickhouse', label: 'ClickHouse' }]}/>
        <Input T={T} label="Host" value={form.db_host} onChange={v => set('db_host', v)} required placeholder="127.0.0.1" mono/>
        <Input T={T} label="Port" value={String(form.db_port)} onChange={v => set('db_port', v)} required placeholder="9030" mono/>
        <Input T={T} label="User" value={form.db_user} onChange={v => set('db_user', v)} required placeholder="root" mono/>
        <Input T={T} label="Password" value={form.db_password} onChange={v => set('db_password', v)} type="password" placeholder={isEdit ? '留空不修改' : '••••••••'} optional={isEdit}/>
        <Input T={T} label="Database" value={form.db_database} onChange={v => set('db_database', v)} required placeholder="mydb 或 ohx_ods,ohx_dwd" mono/>
        <div style={{ fontSize: 11.5, color: T.muted, marginTop: -6 }}>多个库用英文逗号分隔，查询时可跨库使用 库名.表名</div>
        {testResult && (
          <div style={{ padding: '8px 12px', borderRadius: 6, background: testResult.connected ? T.successSoft : T.accentSoft, color: testResult.connected ? T.success : T.accent, fontSize: 12.5, marginBottom: 12 }}>
            {testResult.connected ? '✓ ' : '✗ '}{testResult.message}
          </div>
        )}
      </div>
      <div style={{ padding: '12px 20px', borderTop: `1px solid ${T.border}`, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={testConn} disabled={testing} style={pillBtn(T)}>
          {testing ? <><Spinner size={11}/> 测试中…</> : <><I.wifi/> 测试连接</>}
        </button>
        <button onClick={onClose} style={pillBtn(T)}>取消</button>
        <button onClick={submit} disabled={loading} style={pillBtn(T, true)}>
          {loading ? <Spinner size={12} color="#fff"/> : '保存'}
        </button>
      </div>
    </Modal>
  );
}

// ─── USER CONFIG ──────────────────────────────────────────────────────────────
function UserConfigScreen({ T, user, onToggleTheme, onNavigate, onLogout }) {
  const [config, setConfig] = React.useState(null);
  const [form, setForm] = React.useState({ api_key: '', preferred_model: '', openrouter_api_key: '', embedding_api_key: '' });
  const [saving, setSaving] = React.useState(false);
  const [customModelDraft, setCustomModelDraft] = React.useState('');
  const [agentCfg, setAgentCfg] = React.useState({ clarifier: '', sql_planner: '', validator: '', presenter: '' });
  const [agentSaving, setAgentSaving] = React.useState(false);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  React.useEffect(() => {
    Promise.all([api.get('/api/user/config'), api.get('/api/user/agent-models')]).then(([d, ac]) => {
      setConfig(d);
      setForm({ api_key: d.api_key || '', preferred_model: d.preferred_model || '', openrouter_api_key: d.openrouter_api_key || '', embedding_api_key: d.embedding_api_key || '' });
      setCustomModelDraft(d.preferred_model?.includes('/') ? d.preferred_model : '');
      setAgentCfg(ac);
    }).catch(() => {});
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const body = {};
      if (form.api_key !== config?.api_key) body.api_key = form.api_key;
      if (form.preferred_model !== config?.preferred_model) body.preferred_model = form.preferred_model;
      if (form.openrouter_api_key !== config?.openrouter_api_key) body.openrouter_api_key = form.openrouter_api_key;
      if (form.embedding_api_key !== config?.embedding_api_key) body.embedding_api_key = form.embedding_api_key;
      if (Object.keys(body).length) await api.put('/api/user/config', body);
      setConfig(prev => ({ ...prev, ...body }));
      toast('已保存');
    } catch (e) { toast(String(e), true); }
    finally { setSaving(false); }
  };

  const saveAgentCfg = async () => {
    setAgentSaving(true);
    try { await api.put('/api/user/agent-models', agentCfg); toast('多Agent配置已保存'); }
    catch (e) { toast(String(e), true); }
    finally { setAgentSaving(false); }
  };

  const models = config?.models || [];

  const colStyle = { display: 'flex', flexDirection: 'column', gap: 0, minWidth: 0 };
  const cardStyle = { background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '18px 20px', marginBottom: 16 };

  return (
    <AppShell T={T} user={user} active="user-config" topbarTitle="API & 模型"
              showConnectionPill={false}
              topbarTrailing={
                <button onClick={save} disabled={saving} style={pillBtn(T, true)}>
                  {saving ? <><Spinner size={11} color="#fff"/> 保存中…</> : '保存更改'}
                </button>
              }
              onToggleTheme={onToggleTheme} onNewChat={() => {}} onNavigate={onNavigate} onLogout={onLogout}>
      <div className="cb-sb" style={{ flex: 1, overflowY: 'auto', padding: '22px 28px' }}>

        {/* Row 1: 本月用量 */}
        {config && (
          <div style={{ ...cardStyle, marginBottom: 16 }}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: T.text, marginBottom: 12 }}>本月用量</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
              {[
                { l: '总 Tokens', v: (config.monthly_tokens || 0).toLocaleString() },
                { l: '总花费',   v: `$${(config.monthly_cost_usd || 0).toFixed(4)}` },
                { l: '平均响应', v: config.avg_response_ms ? `${config.avg_response_ms}ms` : '—' },
              ].map((k, i) => (
                <div key={i} style={{ background: T.bg, border: `1px solid ${T.borderSoft}`, borderRadius: 7, padding: '10px 12px' }}>
                  <div style={{ fontSize: 11, color: T.muted }}>{k.l}</div>
                  <div style={{ fontSize: 18, fontFamily: T.mono, color: T.text, marginTop: 2, fontWeight: 500 }}>{k.v}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Row 2: API Key 左 | OpenRouter 右 */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 0 }}>
          {/* API Key */}
          <div style={cardStyle}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: T.text, marginBottom: 2 }}>API Key 自定义</div>
            <div style={{ fontSize: 11, color: T.muted, marginBottom: 12 }}>支持 Anthropic / OpenAI / Google / DeepSeek 等直连</div>
            <Input T={T} label="API Key" value={form.api_key} onChange={v => set('api_key', v)}
                   type="password" placeholder="sk-ant-api03-…" mono
                   trailing={<span style={{ fontSize: 11, color: form.api_key ? T.success : T.muted }}>{form.api_key ? '已填写' : '未填写'}</span>}/>
            <div style={{ fontSize: 11, color: T.muted, marginTop: -4, marginBottom: 10 }}>留空则使用系统全局 Key</div>
            <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 6 }}>热门模型快选（设为默认）</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginBottom: 10 }}>
              {[
                { id: 'claude-opus-4-7',   label: 'Claude Opus 4.7' },
                { id: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6' },
                { id: 'claude-haiku-4-5',  label: 'Claude Haiku 4.5' },
                { id: 'gpt-4o',            label: 'GPT-4o' },
                { id: 'gpt-4o-mini',       label: 'GPT-4o Mini' },
                { id: 'gemini-2.0-flash',  label: 'Gemini 2.0 Flash' },
                { id: 'deepseek-chat',     label: 'DeepSeek Chat' },
              ].map(({ id, label }) => {
                const active = form.preferred_model === id;
                return (
                  <button key={id} onClick={() => { set('preferred_model', active ? '' : id); setCustomModelDraft(''); }}
                          style={{ padding: '3px 9px', borderRadius: 12, fontSize: 11.5, cursor: 'pointer',
                                   background: active ? T.accent : T.chipBg, color: active ? '#fff' : T.text,
                                   border: `1px solid ${active ? T.accent : T.border}` }}>
                    {label}
                  </button>
                );
              })}
            </div>
            <Input T={T} label="自定义模型 ID"
                   value={form.preferred_model && !form.preferred_model.includes('/') ? form.preferred_model : ''}
                   onChange={v => { set('preferred_model', v); setCustomModelDraft(''); }}
                   placeholder="claude-sonnet-4-6 · gpt-4o · …" mono/>
            <div style={{ fontSize: 11, color: T.muted, marginTop: -4 }}>填写后将作为默认模型</div>
          </div>

          {/* OpenRouter */}
          <div style={cardStyle}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: T.text, marginBottom: 2 }}>OpenRouter 接入</div>
            <div style={{ fontSize: 11, color: T.muted, marginBottom: 12 }}>通过一个 Key 接入 OpenAI / Anthropic / Google 等 200+ 模型</div>
            <Input T={T} label="OpenRouter API Key" value={form.openrouter_api_key} onChange={v => set('openrouter_api_key', v)}
                   type="password" placeholder="sk-or-v1-…" mono
                   trailing={<span style={{ fontSize: 11, color: form.openrouter_api_key ? T.success : T.muted }}>{form.openrouter_api_key ? '已填写' : '未填写'}</span>}/>
            <div style={{ fontSize: 11, color: T.muted, marginTop: -4, marginBottom: 10 }}>前往 openrouter.ai/keys 创建</div>
            <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 6 }}>热门模型快选（设为默认）</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginBottom: 10 }}>
              {[
                { id: 'openai/gpt-4o',                      label: 'GPT-4o' },
                { id: 'openai/gpt-4o-mini',                 label: 'GPT-4o Mini' },
                { id: 'anthropic/claude-sonnet-4-5',        label: 'Claude Sonnet 4.5' },
                { id: 'google/gemini-2.0-flash-001',        label: 'Gemini 2.0 Flash' },
                { id: 'deepseek/deepseek-chat-v3-0324',     label: 'DeepSeek V3' },
                { id: 'meta-llama/llama-3.3-70b-instruct', label: 'Llama 3.3 70B' },
                { id: 'qwen/qwen-2.5-72b-instruct',        label: 'Qwen 2.5 72B' },
                { id: 'mistralai/mistral-large-2411',       label: 'Mistral Large' },
              ].map(({ id, label }) => {
                const active = form.preferred_model === id;
                return (
                  <button key={id} onClick={() => { const v = active ? '' : id; set('preferred_model', v); setCustomModelDraft(v); }}
                          style={{ padding: '3px 9px', borderRadius: 12, fontSize: 11.5, cursor: 'pointer',
                                   background: active ? T.accent : T.chipBg, color: active ? '#fff' : T.text,
                                   border: `1px solid ${active ? T.accent : T.border}` }}>
                    {label}
                  </button>
                );
              })}
            </div>
            <Input T={T} label="自定义模型 ID"
                   value={customModelDraft}
                   onChange={v => { setCustomModelDraft(v); set('preferred_model', v); }}
                   placeholder="openai/gpt-4o · anthropic/claude-opus-4-5 · …" mono/>
            <div style={{ fontSize: 11, color: T.muted, marginTop: -4 }}>格式：厂商/模型名 · 见 openrouter.ai/models</div>
          </div>
        </div>

        {/* Row 3: 直连模型 左 | Embedding + 多Agent 右 */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
          {/* 直连模型 */}
          <div style={cardStyle}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: T.text, marginBottom: 2 }}>直连模型</div>
            <div style={{ fontSize: 11, color: T.muted, marginBottom: 12 }}>管理员配置的可选模型 · 选择后作为默认</div>
            {form.preferred_model && form.preferred_model.includes('/') && (
              <div style={{ padding: '7px 10px', borderRadius: 6, background: T.accentSoft, border: `1px solid ${T.accent}`, fontSize: 11.5, color: T.accent, marginBottom: 10 }}>
                当前已选 OpenRouter 模型：<strong>{form.preferred_model}</strong>
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              {models.map(m => {
                const mid = m.model_id || m.id;
                const active = !form.preferred_model?.includes('/') && (form.preferred_model === mid || (!form.preferred_model && m.is_default));
                return (
                  <label key={mid} onClick={() => { set('preferred_model', mid); setCustomModelDraft(''); }} style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px',
                    background: active ? T.accentSoft : T.bg,
                    border: `1px solid ${active ? T.accent : T.borderSoft}`,
                    borderRadius: 7, cursor: 'pointer',
                  }}>
                    <span style={{ width: 14, height: 14, borderRadius: '50%', flexShrink: 0, border: `1.5px solid ${active ? T.accent : T.border}`, display: 'grid', placeItems: 'center', background: active ? T.accent : 'transparent' }}>
                      {active && <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#fff' }}/>}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12.5, color: T.text, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'wrap' }}>
                        {m.name}
                        <span style={{ fontSize: 10, padding: '1px 4px', borderRadius: 3, background: T.chipBg, color: T.muted }}>{m.provider}</span>
                        {m.is_default && <span style={{ fontSize: 10, padding: '1px 4px', borderRadius: 3, background: T.accentSoft, color: T.accent, fontWeight: 600 }}>默认</span>}
                      </div>
                    </div>
                    <span style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono, flexShrink: 0 }}>${m.input_price}/{m.output_price}</span>
                  </label>
                );
              })}
              {models.length === 0 && <div style={{ color: T.muted, fontSize: 12, padding: '12px 0' }}>暂无可用模型</div>}
            </div>
          </div>

          {/* Embedding + 多Agent */}
          <div style={colStyle}>
            {/* Embedding */}
            <div style={cardStyle}>
              <div style={{ fontSize: 12.5, fontWeight: 600, color: T.text, marginBottom: 2 }}>Embedding API Key</div>
              <div style={{ fontSize: 11, color: T.muted, marginBottom: 12 }}>用于知识库向量检索 · 填 OpenAI Key · 留空降级为关键词匹配</div>
              <Input T={T} label="Embedding API Key" value={form.embedding_api_key} onChange={v => set('embedding_api_key', v)}
                     type="password" placeholder="sk-…" mono
                     trailing={<span style={{ fontSize: 11, color: form.embedding_api_key ? T.success : T.muted }}>{form.embedding_api_key ? '已填写' : '未填写'}</span>}/>
              <div style={{ fontSize: 11, color: T.muted, marginTop: -4 }}>OpenRouter Key 可替代</div>
            </div>

            {/* 多Agent分配 */}
            <div style={{ ...cardStyle, marginBottom: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 600, color: T.text, marginBottom: 2 }}>多 Agent 分配</div>
              <div style={{ fontSize: 11, color: T.muted, marginBottom: 14 }}>
                为每个 Agent 指定模型，留空则跟随默认模型。优先使用你配置的 API Key。
              </div>
              {[
                { key: 'clarifier',   label: '理解问题',  hint: '推荐轻量模型' },
                { key: 'sql_planner', label: '生成 SQL',  hint: '推荐最强模型' },
                { key: 'validator',   label: '验证结果',  hint: '推荐轻量模型' },
                { key: 'presenter',   label: '整理洞察',  hint: '推荐中等模型' },
              ].map(({ key, label, hint }) => (
                <div key={key} style={{ marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
                    <span style={{ fontSize: 12, color: T.subtext, fontWeight: 500 }}>{label}</span>
                    <span style={{ fontSize: 10.5, color: T.muted }}>{hint}</span>
                  </div>
                  <select value={agentCfg[key] || ''} onChange={e => setAgentCfg(p => ({ ...p, [key]: e.target.value }))}
                    style={{ width: '100%', background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 7, padding: '6px 10px', fontSize: 12, color: T.text, fontFamily: T.sans, cursor: 'pointer', outline: 'none' }}>
                    <option value="">默认（跟随用户模型）</option>
                    {models.filter(m => m.enabled !== false).map(m => (
                      <option key={m.model_id} value={m.model_id}>{m.name} · {m.provider}</option>
                    ))}
                  </select>
                </div>
              ))}
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
                <button onClick={saveAgentCfg} disabled={agentSaving} style={{ ...pillBtn(T, true), padding: '6px 14px' }}>
                  {agentSaving ? <><Spinner size={11} color="#fff"/> 保存中…</> : '保存配置'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

function CfgSection({ T, title, subtitle, children }) {
  return (
    <div style={{ marginBottom: 28 }}>
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 14, color: T.text, fontWeight: 600 }}>{title}</div>
        {subtitle && <div style={{ fontSize: 11.5, color: T.muted, marginTop: 2 }}>{subtitle}</div>}
      </div>
      {children}
    </div>
  );
}

// ─── APP ROOT ─────────────────────────────────────────────────────────────────
function App() {
  const [T, toggleTheme] = useTheme();
  const [user, setUser] = usePersist('cb_user', null);
  const [screen, setScreen] = React.useState('chat');
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    const token = localStorage.getItem('cb_token');
    if (!token) { setLoading(false); return; }
    api.me().then(u => {
      setUser(u);
      setLoading(false);
    }).catch(() => {
      localStorage.removeItem('cb_token');
      setUser(null);
      setLoading(false);
    });
  }, []);

  const handleLogin = (u) => { setUser(u); setScreen('chat'); };
  const handleLogout = () => {
    localStorage.removeItem('cb_token');
    localStorage.removeItem('cb_user');
    setUser(null);
    setScreen('chat');
  };
  const navigate = (s) => setScreen(s);

  if (loading) {
    return (
      <div style={{ width: '100vw', height: '100vh', display: 'grid', placeItems: 'center', background: T.bg }}>
        <Spinner size={28} color={T.accent}/>
      </div>
    );
  }

  if (!user) return <LoginScreen T={T} onLogin={handleLogin} onToggleTheme={toggleTheme}/>;

  const commonProps = { T, user, onToggleTheme: toggleTheme, onNavigate: navigate, onLogout: handleLogout };

  const adminTabMap = { 'admin-sources': 'sources', 'admin-users': 'users', 'admin-models': 'models', 'admin-knowledge': 'knowledge' };
  if (adminTabMap[screen] && user.role === 'admin') return <AdminScreen {...commonProps} screen={screen} initialTab={adminTabMap[screen]}/>;
  if (screen === 'admin' && user.role === 'admin') return <AdminScreen {...commonProps} screen={screen} initialTab="users"/>;
  if (screen === 'user-config' || screen === 'settings') return <UserConfigScreen {...commonProps}/>;
  return <ChatScreen {...commonProps}/>;
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
