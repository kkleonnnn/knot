// AddWidgetModal.jsx — v0.8.10 「添加组件」弹窗（基准 §5）：6 类型 chip + 指标名 + 周期 + SQL → 追加一个 tile。
// KNOT 真数据（approach a）：弹窗生成对应类型 tile；SQL 就地填（基准 mock 无数据，KNOT 需 SQL 才有真值）。
import { useState } from 'react';
import { Modal, ModalHeader, toast } from '../../utils.jsx';
import { api } from '../../api.js';

// 6 类型（基准 .dc.html 图标 path，viewBox 24 / stroke 1.6 / 无填充）
const TYPES = [
  { v: 'stat', label: '单值', d: 'M8 6h8M12 6v12M9 18h6' },
  { v: 'pair', label: '单值+趋势', d: 'M5 5v14M9 15l3-3 2 2 5-6' },
  { v: 'trend', label: '趋势图', d: 'M3 16l5-5 4 3 8-9M17 5h4v4' },
  { v: 'donut', label: '占比环', el: <><circle cx="12" cy="12" r="8" /><path d="M12 12V4M12 12l7 3" /></> },
  { v: 'bars', label: '排行榜', d: 'M4 7h11M4 12h16M4 17h7' },
  { v: 'table', label: '明细表', el: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 10h18M9 4v16" /></> },
];
const PERIODS = ['近 7 日', '近 14 日', '近 30 日', '今日', '本周', '本月'];

export function AddWidgetModal({ T, report, onClose, onSaved }) {
  const [type, setType] = useState('stat');
  const [metric, setMetric] = useState('');
  const [period, setPeriod] = useState(PERIODS[0]);
  const [sql, setSql] = useState('');
  const [saving, setSaving] = useState(false);
  const fld = { width: '100%', height: 38, padding: '0 12px', background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 8, color: T.text, fontSize: 13, fontFamily: T.sans, outline: 'none' };

  const save = async () => {
    if (!metric.trim()) { toast('指标名称必填', true); return; }
    if (!sql.trim()) { toast('SQL 必填（KNOT 组件需真数据）', true); return; }
    const existing = (report.tiles || []).map((t) => ({
      id: t.id, tile_type: t.tile_type, title: t.title, sql_text: t.sql_text,
      viz_config: (() => { try { return JSON.parse(t.viz_config || '{}'); } catch { return {}; } })(),
      grid_span: t.grid_span, sort_order: t.sort_order,
    }));
    const newTile = { tile_type: type, title: metric.trim(), sql_text: sql.trim(),
      viz_config: { period }, grid_span: 1, sort_order: existing.length };
    setSaving(true);
    try {
      await api.put(`/api/bi/reports/${report.id}`, { tiles: [...existing, newTile] });
      await api.post(`/api/bi/reports/${report.id}/refresh`);   // 跑新组件 SQL 出数
      toast('已添加到看板');
      onSaved();
      onClose();
    } catch (e) {
      toast(`添加失败：${e.message || e}`, true);
    } finally { setSaving(false); }
  };

  return (
    <Modal T={T} onClose={onClose} width={462}>
      <ModalHeader T={T} title="添加组件" subtitle="选组件类型 + 指标 + 周期 + SQL → 追加到看板" onClose={onClose} />
      <div className="cb-sb" style={{ padding: 20, maxHeight: '70vh', overflowY: 'auto' }}>
        <div style={{ fontSize: 12, color: T.subtext, marginBottom: 8, fontWeight: 500 }}>组件类型</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 16 }}>
          {TYPES.map((t) => {
            const on = type === t.v;
            return (
              <button key={t.v} onClick={() => setType(t.v)} style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, padding: '11px 6px', borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit',
                background: on ? `color-mix(in oklch, ${T.accent} 8%, transparent)` : 'transparent',
                border: `1px solid ${on ? `color-mix(in oklch, ${T.accent} 45%, transparent)` : T.border}`,
                color: on ? T.accent : T.subtext,
              }}>
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  {t.el || <path d={t.d} />}
                </svg>
                <span style={{ fontSize: 11.5 }}>{t.label}</span>
              </button>
            );
          })}
        </div>
        <div style={{ fontSize: 12, color: T.subtext, marginBottom: 5, fontWeight: 500 }}>指标名称</div>
        <input value={metric} onChange={(e) => setMetric(e.target.value)} placeholder="输入指标，如：注册用户数 / 充值金额" style={{ ...fld, marginBottom: 14 }} />
        <div style={{ fontSize: 12, color: T.subtext, marginBottom: 5, fontWeight: 500 }}>数据周期</div>
        <select value={period} onChange={(e) => setPeriod(e.target.value)} style={{ ...fld, marginBottom: 14, cursor: 'pointer' }}>
          {PERIODS.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <div style={{ fontSize: 12, color: T.subtext, marginBottom: 5, fontWeight: 500 }}>SQL（只读；存前校验）</div>
        <textarea value={sql} onChange={(e) => setSql(e.target.value)} rows={4} spellCheck={false}
          placeholder={'SELECT sta_date, reg_user_num\nFROM ohx_ads.ads_operation_report_daily\nORDER BY sta_date DESC LIMIT 8'}
          style={{ width: '100%', background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 8, padding: '9px 11px', fontSize: 13, color: T.text, fontFamily: T.mono, resize: 'vertical' }} />
        <div style={{ fontSize: 11, color: T.muted, marginTop: 6 }}>列映射（值列/日期列等）添加后在「编辑」里细调。</div>
      </div>
      <div style={{ padding: '14px 20px', borderTop: `1px solid ${T.border}`, display: 'flex', justifyContent: 'flex-end' }}>
        <button onClick={save} disabled={saving} style={{ padding: '8px 18px', borderRadius: 8, border: 'none', background: T.accent, color: T.sendFg, fontSize: 13, fontWeight: 500, fontFamily: 'inherit', cursor: saving ? 'default' : 'pointer', opacity: saving ? 0.6 : 1, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
          {saving ? '添加中…' : '添加到看板'}
        </button>
      </div>
    </Modal>
  );
}
