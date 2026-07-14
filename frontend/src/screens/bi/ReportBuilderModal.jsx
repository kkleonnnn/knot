// ReportBuilderModal.jsx — v0.8.5 (②a) admin 报表 builder（新建/编辑）。
// v0.8.7 ①：BI 只留 2 类 —— 报表（tabbed，1+ 页每页一 SQL；单页=普通表格）+ 仪表盘（结构化 tiles）。
//   「宽表」转遗留：不再新建，仅编辑既有 wide_table 报表时选项可见（覆盖层公式随之遗留）。
// SQL 存前经后端 doris.is_safe_sql 校验（D7；非只读 → 400 → toast）。
// 报表：TileBuilder tableOnly（每页一 SQL + 拖拽排序）。仪表盘：TileBuilder（每 tile 一 SQL + 类型 + viz + 排序）+ 洞察。
import { useState } from 'react';
import { Modal, ModalHeader, Input, Select, toast } from '../../utils.jsx';
import { api } from '../../api.js';
import { TileBuilder } from './TileBuilder.jsx';

const _parse = (s, d) => { try { return s ? JSON.parse(s) : d; } catch { return d; } };

export function ReportBuilderModal({ T, editing, folders = [], dataSources = [], onClose, onSaved }) {
  const [title, setTitle] = useState(editing ? editing.title : '');
  const [sqlText, setSqlText] = useState(editing ? (editing.sql_text || '') : '');
  const [dataSourceId, setDataSourceId] = useState(editing && editing.data_source_id != null ? String(editing.data_source_id) : '');
  const [folderId, setFolderId] = useState(editing && editing.folder_id != null ? String(editing.folder_id) : '');
  const [overlay, setOverlay] = useState(() => (editing ? _parse(editing.overlay_config, []) : []));
  const [reportType, setReportType] = useState(editing ? (editing.report_type || 'wide_table') : 'tabbed');
  const isLegacyWide = editing && editing.report_type === 'wide_table';   // v0.8.7 ①：宽表遗留（仅编辑既有时可选）
  // 仪表盘：结构化 tiles（viz_config 由 JSON 串 → 对象供编辑）+ 报表级 insight
  const [tiles, setTiles] = useState(() => (editing && Array.isArray(editing.tiles)
    ? editing.tiles.map((t) => ({ ...t, viz_config: _parse(t.viz_config, {}) })) : []));
  const [insight, setInsight] = useState(() => (_parse(editing && editing.dashboard_config, {}).insight || ''));
  const [saving, setSaving] = useState(false);
  const isDash = reportType === 'dashboard';
  const isTabbed = reportType === 'tabbed';
  const isTiled = isDash || isTabbed;       // 两者都 tile 承载 → 共用 TileBuilder + 报表级 SQL 名义占位

  const dsOpts = [{ value: '', label: '（不绑定 / 稍后设）' },
    ...dataSources.map((d) => ({ value: String(d.id), label: d.name || d.label || `#${d.id}` }))];
  const folderOpts = [{ value: '', label: '（不归入文件夹）' },
    ...folders.map((f) => ({ value: String(f.id), label: f.name }))];

  const addCell = () => setOverlay((o) => [...o, { row: 1, col: 'A', kind: 'text', value: '' }]);
  const updCell = (i, patch) => setOverlay((o) => o.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  const rmCell = (i) => setOverlay((o) => o.filter((_, j) => j !== i));

  const save = async () => {
    if (!title.trim()) { toast('标题必填', true); return; }
    if (!isTiled && !sqlText.trim()) { toast('SQL 必填', true); return; }
    // column_config 不在本 builder 编辑 → 省略（编辑时保留、新建时默认 null）
    const body = {
      title, report_type: reportType,
      // dashboard/tabbed 报表级 SQL 为名义占位（S1，tiles/页 各自带 SQL）；wide_table 用直写 SQL
      sql_text: isTiled ? (sqlText.trim() || 'SELECT 1') : sqlText,
      data_source_id: dataSourceId ? Number(dataSourceId) : null,
      folder_id: folderId ? Number(folderId) : null,
    };
    if (isTiled) {
      body.tiles = tiles;                          // 后端 diff-by-id 同步 + 每 tile SQL 校验
      if (isDash) body.dashboard_config = { insight: insight || '' };   // insight 仅仪表盘底部
    } else {
      body.overlay_config = overlay;
    }
    setSaving(true);
    try {
      if (editing) await api.put(`/api/bi/reports/${editing.id}`, body);
      else await api.post('/api/bi/reports', body);
      toast(editing ? '已保存' : '已创建');
      onSaved();
      onClose();
    } catch (e) {
      toast(`保存失败：${e.message || e}`, true);
    } finally { setSaving(false); }
  };

  const cellField = () => ({
    padding: '5px 7px', borderRadius: 6, border: `1px solid ${T.inputBorder}`,
    background: T.inputBg, color: T.text, fontSize: 12, fontFamily: T.sans,
  });

  return (
    <Modal T={T} onClose={onClose} width={620}>
      <ModalHeader T={T} title={editing ? '编辑报表' : (isDash ? '新建仪表盘' : '新建报表')}
        subtitle={isDash ? '每板块一条只读 SQL + 类型（KPI / 折线 / 圆盘 / 横条 / 表）+ 拖拽排序 / 占列'
          : isTabbed ? '每页一条只读 SQL + 拖拽排序（单页=表格，多页=日/周/月式）；列注释表头随各页 SQL'
          : 'admin 直写 SQL（只读校验）；覆盖层可插文本 / Excel 式公式（宽表遗留）'} onClose={onClose} />
      <div className="cb-sb" style={{ padding: 20, maxHeight: '70vh', overflowY: 'auto' }}>
        <Input T={T} label="标题" value={title} onChange={setTitle} placeholder={isDash ? '合约交易总览 · 仪表盘' : isTabbed ? '运营日报（日/周/月）' : '平台日汇总 · 宽表'} required />
        <Select T={T} label="报表类型" value={reportType} onChange={setReportType}
          options={[{ value: 'tabbed', label: '报表（表格 · 可多页，每页一条 SQL）' },
            { value: 'dashboard', label: '仪表盘（KPI / 图表 板块布局）' },
            // 宽表遗留：仅编辑既有 wide_table 报表时可见（不再新建）
            ...(isLegacyWide ? [{ value: 'wide_table', label: '宽表（遗留 · SQL + 覆盖层）' }] : [])]} />
        <Select T={T} label="数据源" value={dataSourceId} onChange={setDataSourceId} options={dsOpts} />
        <Select T={T} label="文件夹" value={folderId} onChange={setFolderId} options={folderOpts} />
        {/* 报表级 SQL 仅宽表（dashboard 报表级 SQL 名义占位，SQL 落每 tile — S1）*/}
        {!isTiled && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12, color: T.subtext, marginBottom: 5, fontWeight: 500 }}>SQL（只读；列别名 → 表头）</div>
          <textarea value={sqlText} onChange={(e) => setSqlText(e.target.value)} rows={6} spellCheck={false}
            placeholder={'SELECT dt AS 日期, coin AS 币种, bal AS 余额\nFROM dwd_daily\nORDER BY dt DESC'}
            style={{
              width: '100%', background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 7,
              padding: '9px 11px', fontSize: 13, color: T.text, fontFamily: T.mono, resize: 'vertical',
            }} />
        </div>
        )}

        {/* 宽表：覆盖层编辑（D3「插入」= 文本 / 公式）*/}
        {!isTiled && (
        <div style={{ marginTop: 4 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ fontSize: 12, color: T.subtext, fontWeight: 500 }}>覆盖层单元格（插入文本 / 公式，如 <code style={{ fontFamily: T.mono }}>=SUMIF(B1:B9,"USDT",C1:C9)</code>）</span>
            <button onClick={addCell} style={{ border: `1px solid ${T.border}`, background: 'transparent', color: T.accent, borderRadius: 6, padding: '3px 9px', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>+ 单元格</button>
          </div>
          {overlay.map((c, i) => (
            <div key={i} style={{ display: 'flex', gap: 6, marginBottom: 6, alignItems: 'center' }}>
              <input value={c.col} onChange={(e) => updCell(i, { col: e.target.value.toUpperCase() })} placeholder="列(A)" style={{ ...cellField(), width: 48 }} />
              <input type="number" value={c.row} onChange={(e) => updCell(i, { row: Number(e.target.value) })} placeholder="行" style={{ ...cellField(), width: 56 }} />
              <select value={c.kind} onChange={(e) => updCell(i, { kind: e.target.value })} style={{ ...cellField(), width: 78, cursor: 'pointer' }}>
                <option value="text">文本</option>
                <option value="formula">公式</option>
              </select>
              <input value={c.value} onChange={(e) => updCell(i, { value: e.target.value })}
                placeholder={c.kind === 'formula' ? '=SUMIF(...)' : '文本'}
                style={{ ...cellField(), flex: 1, fontFamily: c.kind === 'formula' ? T.mono : T.sans }} />
              <button onClick={() => rmCell(i)} title="删除" style={{ border: 'none', background: 'transparent', color: T.muted, cursor: 'pointer', fontSize: 15 }}>×</button>
            </div>
          ))}
        </div>
        )}

        {/* 仪表盘/多页表：结构化 tile builder（dashboard=网格 tiles / tabbed=表页签，tableOnly 锁 table 类型）+ 仅仪表盘有底部洞察 */}
        {isTiled && (
        <>
          <TileBuilder T={T} tiles={tiles} onChange={setTiles} tableOnly={isTabbed} />
          {isDash && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 12, color: T.subtext, marginBottom: 5, fontWeight: 500 }}>洞察（底部 AI 生成位；可留空）</div>
            <textarea value={insight} onChange={(e) => setInsight(e.target.value)} rows={2} spellCheck={false}
              placeholder="一句话结论（展示在仪表盘底部洞察卡）"
              style={{ width: '100%', background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 7, padding: '9px 11px', fontSize: 13, color: T.text, fontFamily: T.sans, resize: 'vertical' }} />
          </div>
          )}
        </>
        )}
      </div>
      <div style={{ padding: '14px 20px', borderTop: `1px solid ${T.border}`, display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <button onClick={onClose} style={{ padding: '8px 16px', borderRadius: 7, border: `1px solid ${T.border}`, background: 'transparent', color: T.subtext, cursor: 'pointer', fontFamily: 'inherit', fontSize: 13 }}>取消</button>
        <button onClick={save} disabled={saving} style={{ padding: '8px 18px', borderRadius: 7, border: 'none', background: T.accent, color: T.sendFg, cursor: saving ? 'default' : 'pointer', fontFamily: 'inherit', fontSize: 13, fontWeight: 650, opacity: saving ? 0.6 : 1 }}>
          {saving ? '保存中…' : (editing ? '保存' : '创建')}
        </button>
      </div>
    </Modal>
  );
}
