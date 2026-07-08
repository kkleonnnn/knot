// TileBuilder.jsx — v0.8.6 (②b) 结构化 tile builder：add / type / SQL / viz 列映射 / grid_span / 拖拽 reorder。
// 手写 HTML5 draggable（R-186 无 DnD 库）。每 tile 一条只读 SQL（存前后端 is_safe_sql 校验）。
// viz_config 逐类型字段（列名手填，对齐 admin SQL 别名）；KPI valueCol 显式持久化（C-3）。
import { useState } from 'react';
import { ColumnConfigEditor } from './ColumnConfigEditor.jsx';
import { OverlayEditor } from './OverlayEditor.jsx';

const TYPES = [
  { v: 'kpi', label: '单数值 KPI' },
  { v: 'line', label: '折线' },
  { v: 'donut', label: '圆盘' },
  { v: 'bar', label: '横条' },
  { v: 'table', label: '表格' },
];

export function TileBuilder({ T, tiles, onChange, tableOnly = false }) {
  const [drag, setDrag] = useState(null);
  const [open, setOpen] = useState({});   // v0.8.9 折叠：{`${i}c`:列配置, `${i}o`:公式行} 默认收起 → 页签紧凑好拖
  const toggle = (k) => setOpen((o) => ({ ...o, [k]: !o[k] }));
  const fld = { padding: '5px 7px', borderRadius: 6, border: `1px solid ${T.inputBorder}`, background: T.inputBg, color: T.text, fontSize: 12, fontFamily: T.sans };
  const secBtn = { display: 'flex', alignItems: 'center', gap: 5, width: '100%', textAlign: 'left', marginTop: 6, padding: '4px 2px', border: 'none', borderTop: `1px solid ${T.border}`, background: 'transparent', color: T.subtext, cursor: 'pointer', fontFamily: 'inherit', fontSize: 11.5 };
  const caret = (on) => <span style={{ display: 'inline-block', transform: on ? 'rotate(90deg)' : 'none', transition: 'transform .12s', color: T.muted }}>▸</span>;
  const snapColCount = (t) => { try { const r = JSON.parse(t.last_run_rows_json || '[]'); return r.length ? Object.keys(r[0]).length : 0; } catch { return 0; } };
  const upd = (i, patch) => onChange(tiles.map((t, j) => (j === i ? { ...t, ...patch } : t)));
  const updViz = (i, patch) => upd(i, { viz_config: { ...(tiles[i].viz_config || {}), ...patch } });
  const add = () => onChange([...tiles, { tile_type: tableOnly ? 'table' : 'kpi', title: '', sql_text: '', viz_config: {}, grid_span: 1, sort_order: tiles.length }]);
  const rm = (i) => onChange(tiles.filter((_, j) => j !== i).map((t, k) => ({ ...t, sort_order: k })));
  const reorder = (from, to) => {
    if (from == null || from === to) return;
    const next = [...tiles];
    const [m] = next.splice(from, 1);
    next.splice(to, 0, m);
    onChange(next.map((t, k) => ({ ...t, sort_order: k })));
  };

  return (
    <div style={{ marginTop: 4 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontSize: 12, color: T.subtext, fontWeight: 500 }}>{tableOnly ? '页签（拖拽排序 · 每页一条只读 SQL）' : '板块（拖拽排序 · 每块一条只读 SQL）'}</span>
        <button onClick={add} style={{ border: `1px solid ${T.border}`, background: 'transparent', color: T.accent, borderRadius: 6, padding: '3px 9px', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>{tableOnly ? '+ 页' : '+ 板块'}</button>
      </div>
      {tiles.map((t, i) => {
        const viz = t.viz_config || {};
        return (
          <div key={i} draggable onDragStart={() => setDrag(i)} onDragOver={(e) => e.preventDefault()}
            onDrop={() => { reorder(drag, i); setDrag(null); }}
            style={{ border: `1px solid ${T.border}`, borderRadius: 8, padding: 10, marginBottom: 8, background: T.card, opacity: drag === i ? 0.5 : 1 }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 6 }}>
              <span title="拖拽排序" style={{ cursor: 'grab', color: T.muted, fontSize: 14, flexShrink: 0 }}>⠿</span>
              {!tableOnly && (
                <select value={t.tile_type} onChange={(e) => upd(i, { tile_type: e.target.value })} style={{ ...fld, cursor: 'pointer' }}>
                  {TYPES.map((x) => <option key={x.v} value={x.v}>{x.label}</option>)}
                </select>
              )}
              <input value={t.title || ''} onChange={(e) => upd(i, { title: e.target.value })} placeholder={tableOnly ? '页签名（日汇总 / 周汇总…）' : '板块标题'} style={{ ...fld, flex: 1 }} />
              {!tableOnly && (
                <select value={t.grid_span || 1} onChange={(e) => upd(i, { grid_span: Number(e.target.value) })} title="占列宽" style={{ ...fld, cursor: 'pointer' }}>
                  <option value={1}>1 列</option><option value={2}>2 列</option><option value={3}>3 列</option>
                </select>
              )}
              <button onClick={() => rm(i)} title={tableOnly ? '删除页' : '删除板块'} style={{ border: 'none', background: 'transparent', color: T.muted, cursor: 'pointer', fontSize: 15, flexShrink: 0 }}>×</button>
            </div>
            <textarea value={t.sql_text || ''} onChange={(e) => upd(i, { sql_text: e.target.value })} rows={2} spellCheck={false}
              placeholder="SELECT ...（只读；存前校验）"
              style={{ width: '100%', ...fld, fontFamily: T.mono, resize: 'vertical', marginBottom: 6 }} />
            {t.tile_type === 'kpi' && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <input value={viz.valueCol || ''} onChange={(e) => updViz(i, { valueCol: e.target.value })} placeholder="值列名 valueCol（必填）" style={{ ...fld, flex: 1 }} />
                <input value={viz.suffix || ''} onChange={(e) => updViz(i, { suffix: e.target.value })} placeholder="后缀(亿/万)" style={{ ...fld, width: 84 }} />
                <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, color: T.subtext }}>
                  <input type="checkbox" checked={!!viz.main} onChange={(e) => updViz(i, { main: e.target.checked })} /> 主指标
                </label>
              </div>
            )}
            {(t.tile_type === 'donut' || t.tile_type === 'bar') && (
              <div style={{ display: 'flex', gap: 6 }}>
                <input value={viz.labelCol || ''} onChange={(e) => updViz(i, { labelCol: e.target.value })} placeholder="标签列 labelCol" style={{ ...fld, flex: 1 }} />
                <input value={viz.valueCol || ''} onChange={(e) => updViz(i, { valueCol: e.target.value })} placeholder="值列 valueCol" style={{ ...fld, flex: 1 }} />
              </div>
            )}
            {t.tile_type === 'line' && (
              <div style={{ fontSize: 11, color: T.muted }}>首列为 X 轴，其余数值列为系列</div>
            )}
            {t.tile_type === 'table' && (
              <>
                {/* v0.8.9 #1：列配置默认收起（26 列不撑爆卡片 → 页签好拖）；点开编辑 */}
                <button onClick={() => toggle(`${i}c`)} style={secBtn}>{caret(open[`${i}c`])} 列配置（{snapColCount(t)} 列）</button>
                {open[`${i}c`] && <ColumnConfigEditor T={T} tile={t} viz={viz} onChange={(columns) => updViz(i, { columns })} />}
                {/* v0.8.9 #2：公式行（表头↔数据之间的聚合/筛选行，formula.js） */}
                <button onClick={() => toggle(`${i}o`)} style={secBtn}>{caret(open[`${i}o`])} 公式行（{(viz.overlay || []).length} 单元格）</button>
                {open[`${i}o`] && <OverlayEditor T={T} tile={t} viz={viz} overlay={viz.overlay || []} onChange={(overlay) => updViz(i, { overlay })} />}
              </>
            )}
          </div>
        );
      })}
      {!tiles.length && <div style={{ padding: 16, textAlign: 'center', color: T.muted, fontSize: 12 }}>点「+ 板块」添加第一个仪表盘板块。</div>}
    </div>
  );
}
