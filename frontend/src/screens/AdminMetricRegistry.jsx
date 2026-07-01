// v0.7.0 C5 — AdminMetricRegistry：语义层指标注册表 admin 屏（独立页）。
// ⚠️ ≠ AdminMetrics.jsx（内测健康 KPI 屏）；route admin-metric-registry / nav 指标注册表。
// UI v2 设计系统（镜像 AdminBudgets + tab_resources tokens：T.card/border/radius12 + brandSoft +
// pillBtn/FormRow/inputStyleMono/theadStyle）。CRUD → /api/admin/metrics-registry（C2 端点）。
// OOS-1：metric.catalog_id 水平切分（默认 1）；lineage v0.7.16 激活为派生定义 {op,left,right}（占比/人均）。
import { useState, useEffect } from 'react';
import { toast, Spinner } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { I, iconBtn, pillBtn, theadStyle, FormRow, inputStyleMono } from '../Shared.jsx';
import { api } from '../api.js';

// op/left/right = UI-only 派生字段（提交时组装 lineage JSON；编辑时从 lineage 反解）
const _EMPTY = {
  name: '', display: '', caliber: '', aliases: '',
  base_object: '', dimensions: '', date_column: '', unit: '', freshness_lag_days: 1, enabled: 1,
  op: '', left: '', right: '',
};
const _DERIVED_OPS = ['divide', 'multiply', 'add', 'subtract'];   // 与后端 _DERIVED_OPS / compile_helpers._OP_SQL 对齐
const GRID = '1.2fr 1.3fr 1.8fr 0.6fr 0.6fr 70px';

export function AdminMetricRegistryScreen({ T, user, onToggleTheme, onNavigate, onLogout }) {
  const [metrics, setMetrics] = useState(null);   // null = loading
  const [draft, setDraft] = useState(_EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);

  function load() {
    api.get('/api/admin/metrics-registry')
       .then(d => setMetrics(Array.isArray(d) ? d : []))
       .catch(e => { toast(`指标加载失败: ${e.message}`, true); setMetrics([]); });
  }
  useEffect(() => { load(); }, []);

  function handleEdit(m) {
    setEditingId(m.id);
    let op = '', left = '', right = '';                  // 从 lineage JSON 反解派生字段
    try { const lin = m.lineage && JSON.parse(m.lineage); if (lin && lin.op) { op = lin.op; left = lin.left || ''; right = lin.right || ''; } } catch { /* 非派生 */ }
    setDraft({
      name: m.name, display: m.display || '', caliber: m.caliber || '', aliases: m.aliases || '',
      base_object: m.base_object || '', dimensions: m.dimensions || '', date_column: m.date_column || '',
      unit: m.unit || '',
      freshness_lag_days: m.freshness_lag_days ?? 1, enabled: m.enabled ?? 1,
      op, left, right,
    });
  }
  function handleReset() { setEditingId(null); setDraft(_EMPTY); }

  async function handleSave() {
    const isDerived = draft.op && draft.left.trim() && draft.right.trim();   // op+左右 齐 → 派生
    if (!draft.name.trim() || (!draft.caliber.trim() && !isDerived)) {
      toast('指标名必填；口径 或 派生定义（运算 + 左右指标）二选一', true); return;
    }
    // 组装 lineage（派生 → JSON {op,left,right}；否则空）；op/left/right 是 UI-only 不入 payload
    const lineage = isDerived ? JSON.stringify({ op: draft.op, left: draft.left.trim(), right: draft.right.trim() }) : '';
    const { op: _o, left: _l, right: _r, ...rest } = draft;
    const payload = { ...rest, lineage };
    setSaving(true);
    try {
      if (editingId) await api.put(`/api/admin/metrics-registry/${editingId}`, payload);
      else await api.post('/api/admin/metrics-registry', payload);
      toast(editingId ? '指标已更新' : '指标已创建');
      handleReset();
      load();
    } catch (e) {
      toast(`保存失败: ${e.message}`, true);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(m) {
    if (!confirm(`删除指标「${m.name}」？此操作不可撤销。`)) return;
    try {
      await api.del(`/api/admin/metrics-registry/${m.id}`);
      toast('指标已删除');
      load();
    } catch (e) {
      toast(`删除失败: ${e.message}`, true);
    }
  }

  return (
    <AppShell T={T} user={user} active="admin-metric-registry" sidebarContent={null}
              topbarTitle="指标注册表" onToggleTheme={onToggleTheme}
              onNavigate={onNavigate} onLogout={onLogout}>
      <div style={{ padding: '20px 28px 24px', overflowY: 'auto', flex: 1 }} className="cb-sb">
        <div style={{ maxWidth: 960, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* 创建 / 编辑 form */}
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: '4px 24px 20px' }}>
            <FormRow T={T} label="指标名" hint="英文标识，catalog 内唯一（如 gmv）">
              <input style={{ ...inputStyleMono(T), width: 280 }} value={draft.name}
                     onChange={e => setDraft({ ...draft, name: e.target.value })} placeholder="gmv"/>
            </FormRow>
            <FormRow T={T} label="显示名" hint="中文展示名（如 成交额 GMV）">
              <input style={{ ...inputStyleMono(T), width: 280, fontFamily: T.sans }} value={draft.display}
                     onChange={e => setDraft({ ...draft, display: e.target.value })} placeholder="成交额 GMV"/>
            </FormRow>
            <FormRow T={T} label="口径" hint="原子指标的 SQL 聚合表达式（口径单一真源）；派生指标留空、用下方派生定义">
              <input style={{ ...inputStyleMono(T), width: '100%', maxWidth: 560 }} value={draft.caliber}
                     onChange={e => setDraft({ ...draft, caliber: e.target.value })} placeholder="SUM(o.pay_amount)"/>
            </FormRow>
            <FormRow T={T} label="派生定义" hint="占比/人均 = 指标÷指标（左右填已定义指标名；与口径二选一；divide 自动除零保护）">
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <input style={{ ...inputStyleMono(T), width: 150 }} value={draft.left}
                       onChange={e => setDraft({ ...draft, left: e.target.value })} placeholder="gmv（左指标）"/>
                <select style={{ ...inputStyleMono(T), width: 110 }} value={draft.op}
                        onChange={e => setDraft({ ...draft, op: e.target.value })}>
                  <option value="">（无）</option>
                  {_DERIVED_OPS.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
                <input style={{ ...inputStyleMono(T), width: 150 }} value={draft.right}
                       onChange={e => setDraft({ ...draft, right: e.target.value })} placeholder="dau（右指标）"/>
              </div>
            </FormRow>
            <FormRow T={T} label="别名" hint='JSON 数组，自然语言匹配用（如 ["成交额","gmv"]）'>
              <input style={{ ...inputStyleMono(T), width: '100%', maxWidth: 560 }} value={draft.aliases}
                     onChange={e => setDraft({ ...draft, aliases: e.target.value })} placeholder='["成交额","gmv"]'/>
            </FormRow>
            <FormRow T={T} label="基础对象 / 维度 / 日期列" hint="base_object + dimensions（JSON）+ 日期列（时间窗注入用，如 sta_date；留空按维度名启发式推断）">
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <input style={{ ...inputStyleMono(T), width: 180 }} value={draft.base_object}
                       onChange={e => setDraft({ ...draft, base_object: e.target.value })} placeholder="orders"/>
                <input style={{ ...inputStyleMono(T), width: 240 }} value={draft.dimensions}
                       onChange={e => setDraft({ ...draft, dimensions: e.target.value })} placeholder='["date","city"]'/>
                <input style={{ ...inputStyleMono(T), width: 130 }} value={draft.date_column}
                       onChange={e => setDraft({ ...draft, date_column: e.target.value })} placeholder="sta_date"/>
              </div>
            </FormRow>
            <FormRow T={T} label="值格式 (unit)" hint="percentage = 显示 ×100 + %（费率/占比）；⚠️ 值须为 0-1 小数（如 0.0486 → 4.86%），严禁设在 caliber 已返百分数的指标上（双缩放）">
              <select style={{ ...inputStyleMono(T), width: 220 }} value={draft.unit}
                      onChange={e => setDraft({ ...draft, unit: e.target.value })}>
                <option value="">默认（千分位数字）</option>
                <option value="percentage">百分比（×100 + %）</option>
              </select>
            </FormRow>
            <FormRow T={T} label="数据延迟 / 启用" last>
              <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                <input type="number" min="0" style={{ ...inputStyleMono(T), width: 80 }} value={draft.freshness_lag_days}
                       onChange={e => setDraft({ ...draft, freshness_lag_days: parseInt(e.target.value) || 0 })}/>
                <span style={{ fontSize: 12, color: T.muted }}>天延迟</span>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: T.text, cursor: 'pointer' }}>
                  <input type="checkbox" checked={draft.enabled === 1}
                         onChange={e => setDraft({ ...draft, enabled: e.target.checked ? 1 : 0 })}/>
                  启用
                </label>
              </div>
            </FormRow>
            <div style={{ display: 'flex', gap: 8, marginTop: 18 }}>
              <button onClick={handleSave} disabled={saving} style={{ ...pillBtn(T, true), padding: '8px 16px' }}>
                {saving ? <><Spinner size={11} color={T.sendFg}/> 保存中…</> : (editingId ? '✓ 更新指标' : '✓ 新建指标')}
              </button>
              {editingId && <button onClick={handleReset} style={{ ...pillBtn(T), padding: '8px 16px' }}>取消编辑</button>}
            </div>
          </div>

          {/* 指标列表 */}
          {metrics === null ? (
            <div style={{ textAlign: 'center', padding: 32 }}><Spinner size={24} color={T.accent}/></div>
          ) : metrics.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 32, fontSize: 13, color: T.muted }}>暂无指标，使用上方表单创建第一个</div>
          ) : (
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden' }}>
              <div style={{ display: 'grid', gridTemplateColumns: GRID, padding: '9px 16px', ...theadStyle(T) }}>
                <div>指标名</div><div>显示名</div><div>口径</div><div>Catalog</div><div>状态</div><div></div>
              </div>
              {metrics.map((m, i) => (
                <div key={m.id} style={{ display: 'grid', gridTemplateColumns: GRID, padding: '11px 16px',
                  borderBottom: i < metrics.length - 1 ? `1px solid ${T.borderSoft}` : 'none',
                  alignItems: 'center', fontSize: 12.5, opacity: m.enabled ? 1 : 0.55 }}>
                  <div style={{ color: T.text, fontWeight: 500, fontFamily: T.mono, fontSize: 11.5, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.name}</div>
                  <div style={{ color: T.subtext, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.display || '—'}</div>
                  <div style={{ color: T.muted, fontFamily: T.mono, fontSize: 11, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.caliber}</div>
                  <div style={{ color: T.subtext, fontFamily: T.mono, fontSize: 11 }}>#{m.catalog_id}</div>
                  <div style={{ fontSize: 11.5, color: m.enabled ? T.success : T.muted, minWidth: 0 }}>{m.enabled ? '启用' : '禁用'}</div>
                  <div style={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
                    <button onClick={() => handleEdit(m)} style={iconBtn(T)} title="编辑"><I.pencil/></button>
                    <button onClick={() => handleDelete(m)} style={iconBtn(T)} title="删除"><I.x/></button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Info note — brandSoft inset borderLeft 25%（视觉铁律，镜像 AdminBudgets Rules note）*/}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4 }}>
            {[
              { tag: 'OOS-1 归属', body: '指标归属 catalog（水平切分命名空间）；同名指标可在不同 catalog 各自定义口径' },
              { tag: 'v0.7.1 编译', body: 'lineage / 派生依赖 v0.7.0 仅登记不解析；LogicForm 确定性编译 + 跨表 JOIN 留 v0.7.1+' },
            ].map((n, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '10px 14px',
                borderLeft: `2px solid color-mix(in oklch, ${T.accent} 25%, transparent)`, fontSize: 12, color: T.subtext, lineHeight: 1.55 }}>
                <span style={{
                  padding: '2px 8px', borderRadius: 4, background: `color-mix(in oklch, ${T.accent} 12%, transparent)`,
                  color: T.accent, fontSize: 11, fontWeight: 500, fontFamily: T.mono,
                  textTransform: 'uppercase', letterSpacing: '0.02em', flexShrink: 0,
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
