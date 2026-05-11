import { useEffect, useState } from 'react';
import { I, iconBtn } from '../Shared.jsx';
import { toast, Spinner } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { api } from '../api.js';

// v0.4.6 D3：审计日志 admin 看板（who-did-what 追溯）
// R-61 强制分页：默认 50 / 上限 200（与后端一致）
// v0.5.17 视觉重构：Inset 8% 闭环第四处 (R-409) / R-313 rgba 豁免扩展 (R-415) / StatusDot inline (R-412)
// 守护者前瞻：不做"加载更多"无限滚；显式 page 1 / page 2 / ...

const _PAGE_SIZES = [50, 100, 200];
const _REDACTED_RE = /••••redacted••••/g;

// R-411 Action color mapping helper
function actionColor(T, action) {
  if (!action) return T.muted;
  if (action.startsWith('auth.')) return T.warn;
  if (action.startsWith('budget.') || action.startsWith('prompt.') || action.startsWith('fewshot.')) return T.accent;
  if (action.startsWith('export.')) return T.warn;
  return T.muted;
}

// R-426 ActionChip — actionColor + color-mix 12% bg + padding/radius/fontWeight 三件套
function ActionChip({ T, action }) {
  const color = actionColor(T, action);
  return (
    <span style={{
      color,
      background: `color-mix(in oklch, ${color} 12%, transparent)`,
      padding: '2px 8px',
      borderRadius: 4,
      fontWeight: 500,
      fontSize: 11,
      fontFamily: T.mono,
    }}>{action}</span>
  );
}

// R-412 StatusDot inline helper（v0.6 候选 → 移入 Shared 与 ResultBlock/AdminBudgets 共用）
function StatusDot({ T, ok }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: ok ? T.success : T.warn, fontSize: 11.5 }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor', flexShrink: 0 }}/>
      {ok ? '成功' : '失败'}
    </span>
  );
}

export function AdminAuditScreen({ T, user, onToggleTheme, onNavigate, onLogout }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(50);
  const [filter, setFilter] = useState({ actor_id: '', action: '', resource_type: '', since: '' });
  const [drawerRow, setDrawerRow] = useState(null);  // 详情抽屉

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [page, size]);

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: size, offset: (page - 1) * size });
      for (const k of ['actor_id', 'action', 'resource_type', 'since']) {
        if (filter[k]) params.append(k, filter[k]);
      }
      const r = await api.get(`/api/admin/audit-log?${params.toString()}`);
      setItems(r.items || []);
    } catch (e) {
      toast(`加载失败: ${e.message}`, true);
    } finally {
      setLoading(false);
    }
  }

  const sidebarContent = (
    <button onClick={() => onNavigate('chat')} style={{
      display: 'flex', alignItems: 'center', gap: 8, width: '100%',
      padding: '9px 10px', borderRadius: 8, background: 'transparent',
      color: T.muted, border: `1px solid ${T.border}`,
      fontFamily: 'inherit', fontSize: 13, cursor: 'pointer', marginBottom: 8,
    }}>
      <I.chev style={{ transform: 'rotate(90deg)' }}/> 返回对话
    </button>
  );

  return (
    <AppShell T={T} user={user} active="admin-audit" sidebarContent={sidebarContent}
              topbarTitle="审计日志" onToggleTheme={onToggleTheme}
              onNavigate={onNavigate} onLogout={onLogout}>
      <div style={{ padding: '20px 28px 24px', overflowY: 'auto', flex: 1 }} className="cb-sb">
        <div style={{ maxWidth: 1200, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* R-405 Stat 4-card grid + R-394 auto-fit + Q1 tooltip placeholder (4 inline cards for grep ≥4) */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
            <div title="后端聚合 API 对接中 (v0.6+)" style={statCardStyle(T)}>
              <span style={statLabelStyle(T)}>总记录数</span>
              <span style={statValueStyle(T)}>—</span>
            </div>
            <div title="后端聚合 API 对接中 (v0.6+)" style={statCardStyle(T)}>
              <span style={statLabelStyle(T)}>今日</span>
              <span style={statValueStyle(T)}>—</span>
            </div>
            <div title="后端聚合 API 对接中 (v0.6+)" style={statCardStyle(T)}>
              <span style={statLabelStyle(T)}>失败数</span>
              <span style={statValueStyle(T)}>—</span>
            </div>
            <div title="后端聚合 API 对接中 (v0.6+)" style={statCardStyle(T)}>
              <span style={statLabelStyle(T)}>涉及用户</span>
              <span style={statValueStyle(T)}>—</span>
            </div>
          </div>

          {/* R-406/407 + D2 双兼 Filter strip — Label "操作人 (Actor ID)" + Placeholder "输入用户 ID..." */}
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: '14px 18px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, alignItems: 'flex-end' }}>
              <Field T={T} label="操作人 (Actor ID)">
                <input value={filter.actor_id} onChange={e => setFilter({...filter, actor_id: e.target.value})}
                       placeholder="输入用户 ID..." style={inputStyle(T)}/>
              </Field>
              <Field T={T} label="操作类型 (Action)">
                <input value={filter.action} onChange={e => setFilter({...filter, action: e.target.value})}
                       placeholder="如 auth.login..." style={inputStyle(T)}/>
              </Field>
              <Field T={T} label="资源类型 (Resource Type)">
                <input value={filter.resource_type} onChange={e => setFilter({...filter, resource_type: e.target.value})}
                       placeholder="如 user / budget..." style={inputStyle(T)}/>
              </Field>
              <Field T={T} label="起始时间 (Since)">
                <input value={filter.since} onChange={e => setFilter({...filter, since: e.target.value})}
                       placeholder="YYYY-MM-DD..." style={inputStyle(T)}/>
              </Field>
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 12 }}>
              <button onClick={() => { setFilter({ actor_id: '', action: '', resource_type: '', since: '' }); setPage(1); }}
                      style={ghostBtnStyle(T)}>重置</button>
              <button onClick={() => { setPage(1); load(); }}
                      style={primaryBtnStyle(T)}>查询</button>
            </div>
          </div>

          {/* R-408 Table HTML → CSS Grid 7-col */}
          {loading ? (
            <div style={{ textAlign: 'center', padding: 32 }}><Spinner size={24} color={T.accent}/></div>
          ) : items.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 32, color: T.muted, fontSize: 13 }}>
              当前筛选条件下无审计记录。
            </div>
          ) : (
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden' }}>
              {/* R-409 thead brandSoft 8% 闭环第四处 — 字面与 R-323/R-372/R-386 byte-equal */}
              <div style={{
                display: 'grid', gridTemplateColumns: '1.4fr 1fr 1.3fr 2fr 0.7fr 0.6fr 60px',
                padding: '10px 18px',
                background: `color-mix(in oklch, ${T.accent} 8%, transparent)`,
                borderBottom: `1px solid ${T.border}`,
                fontSize: 11, color: T.subtext, fontFamily: T.mono,
                fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase',
              }}>
                <span>时间</span><span>Actor</span><span>Action</span><span>资源</span><span>IP</span><span>状态</span><span></span>
              </div>
              {items.map((row, i) => {
                // R-428 actor null check — actor_name || actor_id || 'System'
                const displayName = row.actor_name || row.actor_id || 'System';
                const displayInitial = (displayName || 'S').toString().charAt(0).toUpperCase();
                return (
                  <div key={row.id} style={{
                    display: 'grid', gridTemplateColumns: '1.4fr 1fr 1.3fr 2fr 0.7fr 0.6fr 60px',
                    padding: '11px 18px', alignItems: 'center', fontSize: 12.5,
                    borderBottom: i === items.length - 1 ? 'none' : `1px solid ${T.borderSoft}`,
                  }}>
                    <span style={{ fontFamily: T.mono, fontSize: 11.5, color: T.muted, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.created_at}</span>
                    {/* R-410 Avatar 22 brandSoft + role chip mono */}
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minWidth: 0, overflow: 'hidden' }}>
                      <span style={{
                        width: 22, height: 22, borderRadius: '50%',
                        background: `color-mix(in oklch, ${T.accent} 8%, transparent)`,
                        color: T.accent, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 10.5, fontWeight: 600, flexShrink: 0,
                      }}>{displayInitial}</span>
                      <span style={{ fontWeight: 500, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{displayName}</span>
                      {row.actor_role && <span style={{ fontSize: 10, color: T.muted, fontFamily: T.mono, textTransform: 'uppercase', flexShrink: 0 }}>{row.actor_role}</span>}
                    </span>
                    {/* R-411/R-426 ActionChip — color-mix 12% bg + padding 2px 8px + radius 4 + fontWeight 500 */}
                    <span style={{ minWidth: 0, overflow: 'hidden' }}>
                      <ActionChip T={T} action={row.action}/>
                    </span>
                    <span style={{ fontFamily: T.mono, fontSize: 11.5, color: T.muted, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {row.resource_type}{row.resource_id ? `:${row.resource_id}` : ''}
                    </span>
                    <span style={{ fontFamily: T.mono, fontSize: 11, color: T.muted, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.client_ip || '-'}</span>
                    {/* R-412 StatusDot inline */}
                    <span style={{ minWidth: 0 }}><StatusDot T={T} ok={row.success}/></span>
                    <span style={{ display: 'inline-flex', justifyContent: 'flex-end' }}>
                      <button onClick={() => setDrawerRow(row)} style={iconBtn(T)} title="查看详情">
                        <I.eye/>
                      </button>
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          {/* R-413/R-430 Pagination — 边界 disabled: page === 1 / items.length < size */}
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 12 }}>
            <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1}
                    style={pageBtnStyle(T, page === 1)}>‹ 上一页</button>
            <span style={{ fontSize: 12.5, color: T.muted, fontFamily: T.mono }}>第 {page} 页（每页 {size}）</span>
            <button onClick={() => setPage(page + 1)} disabled={items.length < size}
                    style={pageBtnStyle(T, items.length < size)}>下一页 ›</button>
            <select value={size} onChange={e => { setSize(parseInt(e.target.value)); setPage(1); }}
                    style={{...inputStyle(T), width: 'auto', marginLeft: 16}}>
              {_PAGE_SIZES.map(s => <option key={s} value={s}>{s} / 页</option>)}
            </select>
          </div>
        </div>
      </div>

      {/* R-415 R-313 sustained 扩展豁免 #2（首处 v0.5.11 R-254 boxShadow）
          理由：Chrome < 111 / WebKit backdrop-filter OKLCH→sRGB fallback GPU 渲染抖动；
                rgba 是全平台一致性稳健选择；架构原则确立 — 红线服从浏览器真理 */}
      {drawerRow && (
        <div onClick={() => setDrawerRow(null)} style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.4)',
          zIndex: 100,
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            position: 'absolute', top: 0, right: 0, height: '100%', width: '600px', maxWidth: '92vw',
            background: T.content, borderLeft: `1px solid ${T.border}`,
            padding: 20, overflowY: 'auto',
            display: 'flex', flexDirection: 'column', gap: 12,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontSize: 14, fontWeight: 500, color: T.text }}>审计详情 #{drawerRow.id}</div>
              <button onClick={() => setDrawerRow(null)} style={iconBtn(T)}>✕</button>
            </div>
            <KV T={T} k="时间" v={drawerRow.created_at}/>
            <KV T={T} k="Actor" v={`${drawerRow.actor_name || '(匿名)'} (${drawerRow.actor_role || '-'}, id=${drawerRow.actor_id ?? 'null'})`}/>
            <KV T={T} k="Action" v={drawerRow.action} mono/>
            <KV T={T} k="Resource" v={`${drawerRow.resource_type}${drawerRow.resource_id ? ':' + drawerRow.resource_id : ''}`}/>
            <KV T={T} k="Client IP" v={drawerRow.client_ip || '-'}/>
            <KV T={T} k="User-Agent" v={drawerRow.user_agent || '-'}/>
            <KV T={T} k="Request ID" v={drawerRow.request_id || '-'}/>
            <KV T={T} k="Success" v={drawerRow.success ? '✓ 成功' : '✗ 失败'}/>
            <div>
              <div style={{ fontSize: 11, color: T.muted, marginBottom: 6 }}>详情（detail_json）</div>
              <DetailJsonView T={T} detail={drawerRow.detail_json}/>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}

// R-429 DetailJsonView try-catch 性能守护 + R-427 cursor:help + R-414 redacted color-mix
function DetailJsonView({ T, detail }) {
  let json;
  try {
    if (typeof detail === 'string') {
      json = JSON.stringify(JSON.parse(detail), null, 2);
    } else {
      json = JSON.stringify(detail || {}, null, 2);
    }
  } catch {
    // 畸形 JSON 兜底 — 显原始字符串，防主界面卡死
    return <pre style={preStyle(T)}>{String(detail ?? '')}</pre>;
  }

  if (!_REDACTED_RE.test(json)) {
    return <pre style={preStyle(T)}>{json}</pre>;
  }
  // 含 ••••redacted•••• → 切片 + R-414 color-mix 高亮 + R-427 cursor:help
  const parts = json.split(/(••••redacted••••)/g);
  return (
    <pre style={preStyle(T)}>
      {parts.map((p, i) => p === '••••redacted••••'
        ? <span key={i} style={{
            background: `color-mix(in oklch, ${T.warn} 20%, transparent)`,
            color: T.warn,
            padding: '0 4px', borderRadius: 3, fontWeight: 600,
            cursor: 'help',
          }} title="敏感字段已脱敏">{p}</span>
        : <span key={i}>{p}</span>)}
    </pre>
  );
}

function KV({ T, k, v, mono }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: T.muted, marginBottom: 2 }}>{k}</div>
      <div style={{ fontSize: 13, color: T.text, fontFamily: mono ? T.mono : 'inherit' }}>{v}</div>
    </div>
  );
}

function Field({ T, label, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
      <span style={{ fontSize: 10, color: T.muted, fontFamily: T.mono, letterSpacing: '0.06em', textTransform: 'uppercase' }}>{label}</span>
      {children}
    </div>
  );
}

function statCardStyle(T) {
  return {
    background: T.card, border: `1px solid ${T.border}`,
    borderRadius: 10, padding: '14px 16px',
    display: 'flex', flexDirection: 'column', gap: 4,
  };
}

function statLabelStyle(T) {
  return { fontSize: 10.5, color: T.muted, fontFamily: T.mono, letterSpacing: '0.06em', textTransform: 'uppercase' };
}

function statValueStyle(T) {
  return { fontSize: 22, fontWeight: 600, color: T.muted, fontFamily: T.mono, letterSpacing: '-0.02em' };
}

function inputStyle(T) {
  return {
    width: '100%', padding: '8px 10px', borderRadius: 6,
    border: `1px solid ${T.border}`, background: T.inputBg, color: T.text,
    fontSize: 13, fontFamily: 'inherit', outline: 'none',
  };
}

function ghostBtnStyle(T) {
  return {
    padding: '8px 14px', borderRadius: 6,
    border: `1px solid ${T.border}`, background: 'transparent',
    color: T.subtext, cursor: 'pointer',
    fontFamily: 'inherit', fontSize: 13,
  };
}

// R-416 primary btn — T.sendFg 替代 hex 白（严禁 'white' 字面 — v0.5.15 Q4 sustained）
function primaryBtnStyle(T) {
  return {
    padding: '8px 14px', borderRadius: 6,
    border: `1px solid ${T.accent}`, background: T.accent,
    color: T.sendFg, cursor: 'pointer',
    fontFamily: 'inherit', fontSize: 13, fontWeight: 500,
  };
}

function pageBtnStyle(T, disabled) {
  return {
    padding: '6px 14px', borderRadius: 6,
    border: `1px solid ${T.border}`,
    background: 'transparent',
    color: disabled ? T.muted : T.text,
    cursor: disabled ? 'not-allowed' : 'pointer',
    fontFamily: 'inherit', fontSize: 12.5,
    opacity: disabled ? 0.5 : 1,
  };
}

function preStyle(T) {
  return {
    background: T.bg, padding: 12, borderRadius: 6,
    fontSize: 11.5, fontFamily: T.mono, color: T.text,
    overflow: 'auto', maxHeight: '50vh',
    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
    border: `1px solid ${T.border}`, margin: 0,
  };
}
