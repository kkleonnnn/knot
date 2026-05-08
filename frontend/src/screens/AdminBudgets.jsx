import { useState, useEffect } from 'react';
import { I, iconBtn } from '../Shared.jsx';
import { toast, Spinner } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { api } from '../api.js';

const SCOPE_TYPES = ['user', 'agent_kind', 'global'];
const BUDGET_TYPES = ['monthly_cost_usd', 'monthly_tokens', 'per_call_cost_usd'];
const ACTIONS = ['warn', 'block'];

const SCOPE_HINT = {
  user: '填写 user_id（数字字符串）',
  agent_kind: '填写 clarifier / sql_planner / fix_sql / presenter（不可填 legacy）',
  global: "固定填 'all'",
};

// v0.4.3: AdminBudgets — 预算 CRUD UI（R-18 幂等响应 + R-21 legacy 守护 + R-23 实时查）
export function AdminBudgetsScreen({ T, user, onToggleTheme, onNavigate, onLogout }) {
  const [budgets, setBudgets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState({
    scope_type: 'user', scope_value: '', budget_type: 'monthly_cost_usd',
    threshold: 5, action: 'warn',
  });
  const [editingId, setEditingId] = useState(null);

  useEffect(() => { load(); }, []);

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
    <AppShell T={T} user={user} active="admin-budgets" sidebarContent={sidebarContent}
              topbarTitle="💰 预算配置" onToggleTheme={onToggleTheme}
              onNavigate={onNavigate} onLogout={onLogout}>
      <div style={{ padding: '20px 28px 24px', overflowY: 'auto', flex: 1 }} className="cb-sb">
        <div style={{ maxWidth: 960, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 18 }}>

          {/* 创建表单 */}
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: 16 }}>
            <div style={{ fontSize: 14, fontWeight: 500, color: T.text, marginBottom: 12 }}>
              {editingId ? '✏️ 编辑预算' : '➕ 新建预算'}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginBottom: 10 }}>
              <Field T={T} label="作用范围 (scope_type)">
                <select value={draft.scope_type} onChange={e => setDraft({ ...draft, scope_type: e.target.value })}
                        style={inputStyle(T)}>
                  {SCOPE_TYPES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              <Field T={T} label={`scope_value（${SCOPE_HINT[draft.scope_type]}）`}>
                <input value={draft.scope_value} onChange={e => setDraft({ ...draft, scope_value: e.target.value })}
                       placeholder={draft.scope_type === 'global' ? 'all' : ''}
                       style={inputStyle(T)}/>
              </Field>
              <Field T={T} label="预算类型">
                <select value={draft.budget_type} onChange={e => setDraft({ ...draft, budget_type: e.target.value })}
                        style={inputStyle(T)}>
                  {BUDGET_TYPES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              <Field T={T} label="阈值">
                <input type="number" step="0.001" value={draft.threshold}
                       onChange={e => setDraft({ ...draft, threshold: parseFloat(e.target.value) || 0 })}
                       style={inputStyle(T)}/>
              </Field>
              <Field T={T} label="超阈值动作">
                <select value={draft.action} onChange={e => setDraft({ ...draft, action: e.target.value })}
                        style={inputStyle(T)}>
                  {ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
                </select>
              </Field>
            </div>
            {/* R-21 客户端守护提示 */}
            {isLegacyScope && (
              <div style={{ fontSize: 12, color: T.accent, marginBottom: 8 }}>
                ⚠️ R-21：'legacy' 是 v0.4.2 历史标记，不可设预算
              </div>
            )}
            {isBlockMisuse && (
              <div style={{ fontSize: 12, color: T.accent, marginBottom: 8 }}>
                ⚠️ 'block' 仅允许配 (scope_type=agent_kind, budget_type=per_call_cost_usd)
              </div>
            )}
            <button onClick={handleSubmit} disabled={!canSubmit}
                    style={{
                      padding: '8px 16px', borderRadius: 6,
                      border: `1px solid ${canSubmit ? T.accent : T.border}`,
                      background: canSubmit ? T.accent : 'transparent',
                      color: canSubmit ? '#fff' : T.muted,
                      cursor: canSubmit ? 'pointer' : 'not-allowed',
                      fontFamily: 'inherit', fontSize: 13,
                    }}>
              {editingId ? '更新' : '创建（R-18 幂等：相同 scope+type 三元组会覆盖）'}
            </button>
          </div>

          {/* 列表 */}
          {loading ? (
            <div style={{ textAlign: 'center', padding: 32 }}><Spinner size={24} color={T.accent}/></div>
          ) : budgets.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 32, color: T.muted, fontSize: 13 }}>
              暂无预算。新建一条以开启成本监控。
            </div>
          ) : (
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                <thead>
                  <tr style={{ background: T.bg }}>
                    {['Scope', 'Value', '类型', '阈值', 'Action', 'Enabled', '操作'].map(c =>
                      <th key={c} style={{ padding: '8px 12px', textAlign: 'left', color: T.muted,
                                            fontWeight: 600, fontSize: 11, letterSpacing: '0.03em',
                                            textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>{c}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {budgets.map(b => (
                    <tr key={b.id} style={{ borderBottom: `1px solid ${T.borderSoft}` }}>
                      <td style={cellStyle(T)}>{b.scope_type}</td>
                      <td style={cellStyle(T)}>{b.scope_value}</td>
                      <td style={{ ...cellStyle(T), fontFamily: T.mono, fontSize: 11.5 }}>{b.budget_type}</td>
                      <td style={cellStyle(T)}>{b.threshold}</td>
                      <td style={cellStyle(T)}>
                        <span style={{ padding: '2px 8px', borderRadius: 10, fontSize: 11,
                                       background: b.action === 'block' ? '#FF990022' : T.accentSoft,
                                       color: b.action === 'block' ? '#cc6600' : T.accent }}>
                          {b.action}
                        </span>
                      </td>
                      <td style={cellStyle(T)}>
                        <button onClick={() => handleToggle(b)} style={{ ...iconBtn(T), fontSize: 11 }}>
                          {b.enabled ? '✓ on' : '○ off'}
                        </button>
                      </td>
                      <td style={cellStyle(T)}>
                        <button onClick={() => handleDelete(b.id)} style={{ ...iconBtn(T), color: T.muted }} title="删除">
                          <I.trash/>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div style={{ fontSize: 11, color: T.muted, lineHeight: 1.6 }}>
            <p>📌 <b>R-16 优先级</b>：user 级预算覆盖 global 预算（user 有独立预算时忽略 global）</p>
            <p>📌 <b>R-23 实时</b>：admin 改完预算后下次查询立即生效（无 cache）</p>
            <p>📌 <b>R-21 守护</b>：'legacy' 是 v0.4.2 历史标记，不可作 agent_kind scope_value</p>
            <p>📌 <b>'block'</b>：仅允许配 (agent_kind, per_call_cost_usd)，防 fix_sql 死循环；其他组合用 'warn'</p>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

function Field({ T, label, children }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: T.muted, marginBottom: 4 }}>{label}</div>
      {children}
    </div>
  );
}

function inputStyle(T) {
  return {
    width: '100%', padding: '6px 10px', borderRadius: 6,
    border: `1px solid ${T.border}`, background: T.content, color: T.text,
    fontSize: 13, fontFamily: 'inherit',
  };
}

function cellStyle(T) {
  return { padding: '8px 12px', color: T.text, whiteSpace: 'nowrap' };
}
