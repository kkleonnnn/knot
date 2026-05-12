import { useState, useEffect } from 'react';
import { I, iconBtn } from '../Shared.jsx';
import { toast, Spinner } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { api } from '../api.js';

// v0.4.3: AdminBudgets — 预算 CRUD UI（R-18 幂等响应 + R-21 legacy 守护 + R-23 实时查）
// v0.5.18 视觉重构：Inset 8% 闭环第五处铁律化 (R-444) / Hero 部分聚合 (Q1) / WarnNote (D9) / R-461 progress transition / R-465 borderLeft 闭环

const SCOPE_TYPES = ['user', 'agent_kind', 'global'];
const BUDGET_TYPES = ['monthly_cost_usd', 'monthly_tokens', 'per_call_cost_usd'];
const ACTIONS = ['warn', 'block'];

const SCOPE_HINT = {
  user: '填写 user_id（数字字符串）',
  agent_kind: '填写 clarifier / sql_planner / fix_sql / presenter（不可填 legacy）',
  global: "固定填 'all'",
};

// R-445 BudgetActionChip — actionColor + color-mix 12% bg + padding/radius/fontWeight 三件套（v0.5.17 R-426 模式延伸）
function BudgetActionChip({ T, action }) {
  const color = action === 'block' ? T.warn : T.accent;
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

// R-446 EnabledChip — StatusDot pattern 6×6 圆 + currentColor + on/off 文字（v0.5.17 R-412 模式延伸）
function EnabledChip({ T, enabled, onClick }) {
  const color = enabled ? T.success : T.muted;
  return (
    <button onClick={onClick} style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      color, fontSize: 11.5,
      background: 'transparent', border: 'none', cursor: 'pointer',
      fontFamily: 'inherit', padding: 0,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor', flexShrink: 0 }}/>
      {enabled ? '已启用' : '已停用'}
    </button>
  );
}

// R-448 WarnNote — D9 修订：warning emoji 偿还 → 14×14 inline svg 感叹号 + T.warn 文字
function WarnNote({ T, children }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 8,
      color: T.warn, fontSize: 12, lineHeight: 1.4,
    }}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0 }}>
        <path d="M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
      </svg>
      {children}
    </div>
  );
}

export function AdminBudgetsScreen({ T, user, onToggleTheme, onNavigate, onLogout }) {
  const [budgets, setBudgets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState({
    scope_type: 'user', scope_value: '', budget_type: 'monthly_cost_usd',
    threshold: 5, action: 'warn',
  });
  const [editingId, setEditingId] = useState(null);
  const [bstats, setBstats] = useState(null);  // v0.5.40 — { tokens_used, cost_usd, usage_pct, cap }

  useEffect(() => { load(); }, []);
  // v0.5.40 — Hero card 真数据
  useEffect(() => { api.get('/api/admin/budgets-stats').then(setBstats).catch(() => {}); }, []);

  async function load() {
    setLoading(true);
    try { setBudgets(await api.get('/api/admin/budgets') || []); }
    catch (e) { toast(`加载失败: ${e.message}`, true); }
    finally { setLoading(false); }
  }

  // R-21 client-side 守护：legacy scope 禁用提交按钮
  const isLegacyScope = draft.scope_type === 'agent_kind' && draft.scope_value === 'legacy';
  const isBlockMisuse = draft.action === 'block' && !(
    draft.scope_type === 'agent_kind' && draft.budget_type === 'per_call_cost_usd'
  );
  const canSubmit = !isLegacyScope && !isBlockMisuse && draft.scope_value.trim() && draft.threshold > 0;

  async function handleSubmit() {
    try {
      const r = await api.post('/api/admin/budgets', draft);
      toast(r.already_existed ? '已更新' : '已创建');
      setDraft({ ...draft, scope_value: '', threshold: 5 });
      setEditingId(null);
      load();
    } catch (e) {
      toast(`保存失败: ${e.message}`, true);
    }
  }

  async function handleDelete(id) {
    if (!confirm('确认删除此预算？')) return;
    try {
      await api.del(`/api/admin/budgets/${id}`);
      toast('已删除');
      load();
    } catch (e) {
      toast(`删除失败: ${e.message}`, true);
    }
  }

  async function handleToggle(b) {
    try {
      await api.put(`/api/admin/budgets/${b.id}`, { enabled: b.enabled ? 0 : 1 });
      load();
    } catch (e) {
      toast(`切换失败: ${e.message}`, true);
    }
  }

  // v0.5.38 — 返回对话 button 移除（Shell.jsx 全屏底部统一渲染）
  const sidebarContent = null;

  // R-447 4 rules — brandSoft inset + R-465 borderLeft 3px 25%
  const rules = [
    { tag: 'R-16', body: 'user 级预算覆盖 global 预算（user 有独立预算时忽略 global）' },
    { tag: 'R-23', body: 'admin 改完预算后下次查询立即生效（无 cache）' },
    { tag: 'R-21', body: "'legacy' 是 v0.4.2 历史标记，不可作 agent_kind scope_value" },
    { tag: 'block', body: "仅允许配 (agent_kind, per_call_cost_usd)，防 fix_sql 死循环；其他组合用 'warn'" },
  ];

  return (
    <AppShell T={T} user={user} active="admin-budgets" sidebarContent={sidebarContent}
              topbarTitle="预算配置" onToggleTheme={onToggleTheme}
              onNavigate={onNavigate} onLogout={onLogout}>
      <div style={{ padding: '20px 28px 24px', overflowY: 'auto', flex: 1 }} className="cb-sb">
        <div style={{ maxWidth: 960, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 18 }}>

          {/* v0.5.34 Hero usage card 对照 demo budget.jsx L57-87 — 横向 flex 3 block + borderLeft separator + 进度条
              （部分聚合 sustained：本月已用/预计花费/使用率 placeholder，待 v0.5.38 后端聚合 endpoint） */}
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: '20px 24px' }}>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 32, marginBottom: 14, flexWrap: 'wrap' }}>
              {/* v0.5.40 Hero 真数据 from /api/admin/budgets-stats */}
              <div style={{ minWidth: 0 }}>
                <div style={statLabelStyle(T)}>本月已用 token</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 4 }}>
                  <span style={{ fontSize: 36, fontWeight: 700, letterSpacing: '-0.02em', fontFamily: T.sans, lineHeight: 1, color: T.text }}>
                    {bstats ? bstats.tokens_used.toLocaleString() : '—'}
                  </span>
                  <span style={{ fontSize: 14, color: T.muted }}>
                    {bstats && bstats.cap ? `/ ${bstats.cap.toLocaleString()}` : '/ —'}
                  </span>
                  {bstats && bstats.usage_pct !== null && (
                    <span style={{ padding: '2px 8px', borderRadius: 4, background: `color-mix(in oklch, ${T.accent} 12%, transparent)`, color: T.accent, fontSize: 11, fontWeight: 500, fontFamily: T.mono, textTransform: 'uppercase', letterSpacing: '0.02em' }}>
                      {bstats.usage_pct}%
                    </span>
                  )}
                </div>
              </div>
              <div style={{ flex: 1, borderLeft: `1px solid ${T.border}`, paddingLeft: 24, minWidth: 0 }}>
                <div style={statLabelStyle(T)}>预计花费</div>
                <div style={{ fontSize: 24, fontWeight: 600, fontFamily: T.sans, marginTop: 4, color: T.text }}>
                  {bstats ? `$ ${bstats.cost_usd.toFixed(4)}` : '—'}
                </div>
              </div>
              <div style={{ borderLeft: `1px solid ${T.border}`, paddingLeft: 24, minWidth: 0 }}>
                <div style={statLabelStyle(T)}>已配置预算项</div>
                <div style={{ fontSize: 24, fontWeight: 600, fontFamily: T.sans, marginTop: 4, color: T.text }}>{budgets.length}</div>
              </div>
              <div style={{ borderLeft: `1px solid ${T.border}`, paddingLeft: 24, minWidth: 0 }}>
                <div style={statLabelStyle(T)}>结算日</div>
                <div style={{ fontSize: 24, fontWeight: 600, fontFamily: T.mono, marginTop: 4, color: T.text }}>
                  {(() => { const d = new Date(); d.setMonth(d.getMonth() + 1); d.setDate(1); return `${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; })()}
                </div>
              </div>
            </div>
            {/* v0.5.40 progress bar — width from usage_pct（无 cap 时 0% 占位）*/}
            <div style={{ height: 8, background: T.bg, border: `1px solid ${T.border}`, borderRadius: 99, overflow: 'hidden' }}>
              <div style={{
                width: bstats && bstats.usage_pct !== null ? `${Math.min(100, bstats.usage_pct)}%` : '0%',
                height: '100%',
                background: T.accent,
                transition: 'width 0.3s ease-in-out',
                opacity: bstats && bstats.usage_pct !== null ? 1 : 0.5,
              }}/>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: T.muted, marginTop: 8, fontFamily: T.mono }}>
              <span>0</span><span>50%</span><span>100%</span>
            </div>
          </div>

          {/* R-441/R-442/R-462 Form — D2 双兼 + gap 16 + minmax + 双按钮 */}
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: 16 }}>
            <div style={{ fontSize: 14, fontWeight: 500, color: T.text, marginBottom: 12 }}>
              {editingId ? '编辑预算' : '新建预算'}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 16, marginBottom: 12 }}>
              <Field T={T} label="作用范围 (Scope Type)">
                <select value={draft.scope_type} onChange={e => setDraft({ ...draft, scope_type: e.target.value })}
                        style={inputStyle(T)}>
                  {SCOPE_TYPES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              <Field T={T} label={`范围值 (Value) — ${SCOPE_HINT[draft.scope_type]}`}>
                <input value={draft.scope_value} onChange={e => setDraft({ ...draft, scope_value: e.target.value })}
                       placeholder={draft.scope_type === 'global' ? 'all' : ''}
                       style={inputStyle(T)}/>
              </Field>
              <Field T={T} label="预算类型 (Budget Type)">
                <select value={draft.budget_type} onChange={e => setDraft({ ...draft, budget_type: e.target.value })}
                        style={inputStyle(T)}>
                  {BUDGET_TYPES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              <Field T={T} label="阈值 (Threshold)">
                <input type="number" step="0.001" value={draft.threshold}
                       onChange={e => setDraft({ ...draft, threshold: parseFloat(e.target.value) || 0 })}
                       style={inputStyle(T)}/>
              </Field>
              <Field T={T} label="超阈值动作 (Action)">
                <select value={draft.action} onChange={e => setDraft({ ...draft, action: e.target.value })}
                        style={inputStyle(T)}>
                  {ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
                </select>
              </Field>
            </div>
            {/* R-448 WarnNote — D9 修订（warning emoji 偿还 → svg 感叹号 + T.warn） */}
            {isLegacyScope && (
              <div style={{ marginBottom: 10 }}>
                <WarnNote T={T}>R-21：'legacy' 是 v0.4.2 历史标记，不可设预算</WarnNote>
              </div>
            )}
            {isBlockMisuse && (
              <div style={{ marginBottom: 10 }}>
                <WarnNote T={T}>'block' 仅允许配 (scope_type=agent_kind, budget_type=per_call_cost_usd)</WarnNote>
              </div>
            )}
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={handleSubmit} disabled={!canSubmit}
                      style={primaryBtnStyle(T, canSubmit)}>
                {editingId ? '更新' : '创建（R-18 幂等：相同 scope+type 三元组会覆盖）'}
              </button>
              <button onClick={() => setDraft({
                scope_type: 'user', scope_value: '', budget_type: 'monthly_cost_usd',
                threshold: 5, action: 'warn',
              })} style={ghostBtnStyle(T)}>重置</button>
            </div>
          </div>

          {/* R-443 Table HTML → CSS Grid 7-col */}
          {loading ? (
            <div style={{ textAlign: 'center', padding: 32 }}><Spinner size={24} color={T.accent}/></div>
          ) : budgets.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 32, color: T.muted, fontSize: 13 }}>
              暂无预算。新建一条以开启成本监控。
            </div>
          ) : (
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden' }}>
              {/* v0.5.38 thead bg brandSoft 8% → T.bg gray + color T.subtext → T.muted（资深反馈"底色改成灰色 + 字体统一"）*/}
              <div style={{
                display: 'grid', gridTemplateColumns: '0.8fr 1fr 1.4fr 0.6fr 0.8fr 0.9fr 50px',
                padding: '10px 18px',
                background: T.bg,
                borderBottom: `1px solid ${T.border}`,
                fontSize: 11, color: T.muted, fontFamily: T.mono,
                fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase',
              }}>
                <span>Scope</span><span>Value</span><span>类型</span><span>阈值</span><span>Action</span><span>Enabled</span><span></span>
              </div>
              {budgets.map((b, i) => (
                <div key={b.id} style={{
                  display: 'grid', gridTemplateColumns: '0.8fr 1fr 1.4fr 0.6fr 0.8fr 0.9fr 50px',
                  padding: '11px 18px', alignItems: 'center', fontSize: 12.5,
                  borderBottom: i === budgets.length - 1 ? 'none' : `1px solid ${T.borderSoft}`,
                }}>
                  <span style={{ color: T.text, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.scope_type}</span>
                  <span style={{ color: T.text, fontFamily: T.mono, fontSize: 11.5, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.scope_value}</span>
                  <span style={{ color: T.muted, fontFamily: T.mono, fontSize: 11.5, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.budget_type}</span>
                  <span style={{ color: T.text, fontFamily: T.mono, fontSize: 11.5, minWidth: 0 }}>{b.threshold}</span>
                  {/* R-445 BudgetActionChip */}
                  <span style={{ minWidth: 0, overflow: 'hidden' }}><BudgetActionChip T={T} action={b.action}/></span>
                  {/* R-446 EnabledChip */}
                  <span style={{ minWidth: 0 }}><EnabledChip T={T} enabled={b.enabled} onClick={() => handleToggle(b)}/></span>
                  <span style={{ display: 'inline-flex', justifyContent: 'flex-end' }}>
                    <button onClick={() => handleDelete(b.id)} style={iconBtn(T)} title="删除">
                      <I.trash/>
                    </button>
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* v0.5.34 Rules note 改 demo budget.jsx L128-140 byte-equal — borderLeft 3px→2px + 删 brandSoft 8% bg（更 subtle，与 v0.5.33 AdminRecovery 一致）*/}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {rules.map((n, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'flex-start', gap: 10,
                padding: '10px 14px',
                borderLeft: `2px solid color-mix(in oklch, ${T.accent} 25%, transparent)`,
                fontSize: 12, color: T.subtext, lineHeight: 1.55,
              }}>
                <span style={{
                  padding: '2px 8px', borderRadius: 4,
                  background: `color-mix(in oklch, ${T.accent} 12%, transparent)`,
                  color: T.accent,
                  fontSize: 11, fontWeight: 500, fontFamily: T.mono,
                  flexShrink: 0, textTransform: 'uppercase', letterSpacing: '0.02em',
                }}>{n.tag}</span>
                <span>{n.body}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
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

function inputStyle(T) {
  return {
    width: '100%', padding: '8px 10px', borderRadius: 6,
    border: `1px solid ${T.border}`, background: T.inputBg, color: T.text,
    fontSize: 13, fontFamily: 'inherit', outline: 'none',
  };
}

// R-450 primary btn — T.sendFg 替代 hex 白（严禁 'white' 字面 — v0.5.15 Q4 sustained）
function primaryBtnStyle(T, enabled) {
  return {
    padding: '8px 16px', borderRadius: 6,
    border: `1px solid ${enabled ? T.accent : T.border}`,
    background: enabled ? T.accent : 'transparent',
    color: enabled ? T.sendFg : T.muted,
    cursor: enabled ? 'pointer' : 'not-allowed',
    fontFamily: 'inherit', fontSize: 13, fontWeight: 500,
  };
}

function ghostBtnStyle(T) {
  return {
    padding: '8px 16px', borderRadius: 6,
    border: `1px solid ${T.border}`, background: 'transparent',
    color: T.subtext, cursor: 'pointer',
    fontFamily: 'inherit', fontSize: 13,
  };
}

function statLabelStyle(T) {
  return { fontSize: 10.5, color: T.muted, fontFamily: T.mono, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6 };
}

function statValueStyle(T) {
  return { fontSize: 22, fontWeight: 600, color: T.muted, fontFamily: T.mono, letterSpacing: '-0.02em' };
}
