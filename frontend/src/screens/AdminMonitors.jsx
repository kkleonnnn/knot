// v0.7.7 C5 — AdminMonitors：事件/规则/动作监控 admin 屏（端到端 vertical slice）。
// 定义指标异动监控（事件 metric+comparator+threshold / 规则 阈值 / 动作 webhook）→「立即检查」→ 命中 fire + 留痕。
// ⚠️「立即检查」受 KNOT_SEMANTIC_LAYER flag（off → 不 fire，R-SL-77）；webhook 独立 allowlist（R-SL-69）。
// UI v2 镜像 AdminMetricRegistry（CRUD）。route admin-monitors（避撞 AdminMetrics/MetricRegistry/LogicForm）。
import { useState, useEffect } from 'react';
import { toast, Spinner } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { I, iconBtn, pillBtn, theadStyle, FormRow, inputStyleMono } from '../Shared.jsx';
import { api } from '../api.js';

const _EMPTY = { name: '', metric_name: '', comparator: 'lt', threshold: 0, baseline_period: '',
                 time_window: 'today', action_type: 'webhook', action_target: '', enabled: 1 };
const COMPARATORS = ['gt', 'lt', 'gte', 'lte', 'eq', 'pct_change_gt', 'pct_change_lt'];
const GRID = '1.1fr 0.9fr 1.3fr 0.7fr 0.5fr 70px';

export function AdminMonitorsScreen({ T, user, onToggleTheme, onNavigate, onLogout }) {
  const [monitors, setMonitors] = useState(null);   // null = loading
  const [draft, setDraft] = useState(_EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [checking, setChecking] = useState(false);
  const [checkRes, setCheckRes] = useState(null);

  function load() {
    api.get('/api/admin/monitors').then(d => setMonitors(Array.isArray(d) ? d : []))
       .catch(e => { toast(`监控加载失败: ${e.message}`, true); setMonitors([]); });
  }
  useEffect(() => { load(); }, []);

  function handleEdit(m) {
    setEditingId(m.id);
    setDraft({ name: m.name, metric_name: m.metric_name, comparator: m.comparator, threshold: m.threshold,
               baseline_period: m.baseline_period || '', time_window: m.time_window || '',
               action_type: m.action_type || 'webhook', action_target: m.action_target || '', enabled: m.enabled ?? 1 });
  }
  function handleReset() { setEditingId(null); setDraft(_EMPTY); }

  async function handleSave() {
    if (!draft.name.trim() || !draft.metric_name.trim() || !draft.action_target.trim()) {
      toast('监控名 + 指标 + webhook URL 必填', true); return;
    }
    setSaving(true);
    try {
      if (editingId) await api.put(`/api/admin/monitors/${editingId}`, draft);
      else await api.post('/api/admin/monitors', draft);
      toast(editingId ? '监控已更新' : '监控已创建'); handleReset(); load();
    } catch (e) { toast(`保存失败: ${e.message}`, true); } finally { setSaving(false); }
  }
  async function handleDelete(m) {
    if (!confirm(`删除监控「${m.name}」？`)) return;
    try { await api.del(`/api/admin/monitors/${m.id}`); toast('监控已删除'); load(); }
    catch (e) { toast(`删除失败: ${e.message}`, true); }
  }
  async function handleCheckNow() {
    setChecking(true); setCheckRes(null);
    try {
      const res = await api.post('/api/admin/monitors/check-now');
      setCheckRes(res);
      toast(res.ok ? `检查完成：${res.fired || 0}/${res.evaluated || 0} 命中触发` : (res.detail || '未执行'), !res.ok);
    } catch (e) { toast(`检查失败: ${e.message}`, true); } finally { setChecking(false); }
  }

  const inp = (k, ph, w) => (
    <input style={{ ...inputStyleMono(T), width: w }} value={draft[k]}
           onChange={e => setDraft({ ...draft, [k]: e.target.value })} placeholder={ph}/>
  );

  return (
    <AppShell T={T} user={user} active="admin-monitors" sidebarContent={null}
              topbarTitle="指标监控" onToggleTheme={onToggleTheme} onNavigate={onNavigate} onLogout={onLogout}>
      <div style={{ padding: '20px 28px 24px', overflowY: 'auto', flex: 1 }} className="cb-sb">
        <div style={{ maxWidth: 960, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* 创建 / 编辑 form */}
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: '4px 24px 20px' }}>
            <FormRow T={T} label="监控名 / 指标" hint="监控名（catalog 内唯一）+ 引用 metric.name">
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>{inp('name', 'gmv 日异动', 220)}{inp('metric_name', 'gmv', 160)}</div>
            </FormRow>
            <FormRow T={T} label="条件" hint="comparator + threshold（阈值或环比变化 %）">
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <select style={{ ...inputStyleMono(T), width: 160 }} value={draft.comparator}
                        onChange={e => setDraft({ ...draft, comparator: e.target.value })}>
                  {COMPARATORS.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
                <input type="number" style={{ ...inputStyleMono(T), width: 120 }} value={draft.threshold}
                       onChange={e => setDraft({ ...draft, threshold: parseFloat(e.target.value) || 0 })} placeholder="-20"/>
              </div>
            </FormRow>
            <FormRow T={T} label="当期 / 基准期" hint="time_resolver 枚举（如 today；环比类填基准期如 last_period）">
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>{inp('time_window', 'today', 200)}{inp('baseline_period', '环比基准期（阈值类留空）', 240)}</div>
            </FormRow>
            <FormRow T={T} label="webhook URL" hint="动作目标（须在 KNOT_WEBHOOK_ALLOWED_HOSTS 内 · 独立 allowlist）">
              {inp('action_target', 'https://hooks.example.com/...', '100%')}
            </FormRow>
            <FormRow T={T} label="启用" last>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: T.text, cursor: 'pointer' }}>
                <input type="checkbox" checked={draft.enabled === 1}
                       onChange={e => setDraft({ ...draft, enabled: e.target.checked ? 1 : 0 })}/> 启用
              </label>
            </FormRow>
            <div style={{ display: 'flex', gap: 8, marginTop: 18 }}>
              <button onClick={handleSave} disabled={saving} style={{ ...pillBtn(T, true), padding: '8px 16px' }}>
                {saving ? <><Spinner size={11} color={T.sendFg}/> 保存中…</> : (editingId ? '✓ 更新监控' : '✓ 新建监控')}
              </button>
              {editingId && <button onClick={handleReset} style={{ ...pillBtn(T), padding: '8px 16px' }}>取消编辑</button>}
              <button onClick={handleCheckNow} disabled={checking} style={{ ...pillBtn(T), padding: '8px 16px', marginLeft: 'auto' }}>
                {checking ? <><Spinner size={11} color={T.accent}/> 检查中…</> : '⚡ 立即检查'}
              </button>
            </div>
          </div>

          {/* 立即检查结果（端到端：事件评估 → 命中 → 动作）*/}
          {checkRes && (
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: '12px 16px', fontSize: 12.5 }}>
              <div style={{ fontWeight: 500, color: T.text, marginBottom: checkRes.results?.length ? 8 : 0 }}>
                {checkRes.ok ? `检查完成：${checkRes.fired || 0}/${checkRes.evaluated || 0} 命中` : `未执行：${checkRes.detail || ''}`}
              </div>
              {(checkRes.results || []).map(r => (
                <div key={r.monitor_id} style={{ display: 'flex', gap: 8, padding: '3px 0', color: T.subtext }}>
                  <span style={{ color: r.status === 'fired' ? T.warn : r.status === 'skipped' ? T.muted : T.success, fontFamily: T.mono, width: 70 }}>{r.status}</span>
                  <span style={{ minWidth: 0, flex: 1 }}>{r.name} · {r.detail}</span>
                </div>
              ))}
            </div>
          )}

          {/* 监控列表 */}
          {monitors === null ? (
            <div style={{ textAlign: 'center', padding: 32 }}><Spinner size={24} color={T.accent}/></div>
          ) : monitors.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 32, fontSize: 13, color: T.muted }}>暂无监控，使用上方表单创建第一个</div>
          ) : (
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden' }}>
              <div style={{ display: 'grid', gridTemplateColumns: GRID, padding: '9px 16px', ...theadStyle(T) }}>
                <div>监控名</div><div>指标</div><div>条件</div><div>动作</div><div>状态</div><div></div>
              </div>
              {monitors.map((m, i) => (
                <div key={m.id} style={{ display: 'grid', gridTemplateColumns: GRID, padding: '11px 16px',
                  borderBottom: i < monitors.length - 1 ? `1px solid ${T.borderSoft}` : 'none',
                  alignItems: 'center', fontSize: 12.5, opacity: m.enabled ? 1 : 0.55 }}>
                  <div style={{ color: T.text, fontWeight: 500, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.name}</div>
                  <div style={{ color: T.subtext, fontFamily: T.mono, fontSize: 11, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.metric_name}</div>
                  <div style={{ color: T.muted, fontFamily: T.mono, fontSize: 11, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.comparator} {m.threshold}</div>
                  <div style={{ color: T.subtext, fontFamily: T.mono, fontSize: 11 }}>{m.action_type}</div>
                  <div style={{ fontSize: 11.5, color: m.enabled ? T.success : T.muted }}>{m.enabled ? '启用' : '禁用'}</div>
                  <div style={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
                    <button onClick={() => handleEdit(m)} style={iconBtn(T)} title="编辑"><I.pencil/></button>
                    <button onClick={() => handleDelete(m)} style={iconBtn(T)} title="删除"><I.x/></button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Info note — brandSoft inset borderLeft 25%（视觉铁律）*/}
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '10px 14px', marginTop: 4,
            borderLeft: `2px solid color-mix(in oklch, ${T.accent} 25%, transparent)`, fontSize: 12, color: T.subtext, lineHeight: 1.55 }}>
            <span style={{ padding: '2px 8px', borderRadius: 4, background: `color-mix(in oklch, ${T.accent} 12%, transparent)`,
              color: T.accent, fontSize: 11, fontWeight: 500, fontFamily: T.mono, textTransform: 'uppercase', flexShrink: 0 }}>诚实</span>
            <span>「立即检查」手动触发（无定时）；命中即发 webhook（受 KNOT_SEMANTIC_LAYER flag + 独立 allowlist）。定时主动监控留后续刀。</span>
          </div>

        </div>
      </div>
    </AppShell>
  );
}
