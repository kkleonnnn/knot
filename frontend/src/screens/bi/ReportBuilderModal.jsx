// ReportBuilderModal.jsx — v0.8.5 (②a) admin 报表 builder（新建/编辑；报表类型 = 宽表 / 仪表盘）。
// SQL 存前经后端 doris.is_safe_sql 校验（D7；非只读 → 400 → toast）。
// 宽表：overlay 单元格编辑（「插入」= 公式覆盖 D3）。仪表盘：板块布局 JSON（KPI / vol / donut / bars / miniRows / insight）。
import { useState } from 'react';
import { Modal, ModalHeader, Input, Select, toast } from '../../utils.jsx';
import { api } from '../../api.js';

const _parse = (s, d) => { try { return s ? JSON.parse(s) : d; } catch { return d; } };

export function ReportBuilderModal({ T, editing, folders = [], dataSources = [], onClose, onSaved }) {
  const [title, setTitle] = useState(editing ? editing.title : '');
  const [sqlText, setSqlText] = useState(editing ? (editing.sql_text || '') : '');
  const [dataSourceId, setDataSourceId] = useState(editing && editing.data_source_id != null ? String(editing.data_source_id) : '');
  const [folderId, setFolderId] = useState(editing && editing.folder_id != null ? String(editing.folder_id) : '');
  const [overlay, setOverlay] = useState(() => (editing ? _parse(editing.overlay_config, []) : []));
  const [reportType, setReportType] = useState(editing ? (editing.report_type || 'wide_table') : 'wide_table');
  const [dashJson, setDashJson] = useState(() =>
    (editing && editing.dashboard_config ? JSON.stringify(_parse(editing.dashboard_config, {}), null, 2) : ''));
  const [saving, setSaving] = useState(false);
  const isDash = reportType === 'dashboard';

  const dsOpts = [{ value: '', label: '（不绑定 / 稍后设）' },
    ...dataSources.map((d) => ({ value: String(d.id), label: d.name || d.label || `#${d.id}` }))];
  const folderOpts = [{ value: '', label: '未归档' },
    ...folders.map((f) => ({ value: String(f.id), label: f.name }))];

  const addCell = () => setOverlay((o) => [...o, { row: 1, col: 'A', kind: 'text', value: '' }]);
  const updCell = (i, patch) => setOverlay((o) => o.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  const rmCell = (i) => setOverlay((o) => o.filter((_, j) => j !== i));

  const save = async () => {
    if (!title.trim() || !sqlText.trim()) { toast('标题和 SQL 必填', true); return; }
    // column_config 不在本 builder 编辑 → 省略（编辑时保留、新建时默认 null）
    const body = {
      title, report_type: reportType, sql_text: sqlText,
      data_source_id: dataSourceId ? Number(dataSourceId) : null,
      folder_id: folderId ? Number(folderId) : null,
    };
    if (isDash) {
      let dc;
      try { dc = dashJson.trim() ? JSON.parse(dashJson) : {}; }
      catch { toast('仪表盘配置 JSON 格式有误', true); return; }
      body.dashboard_config = dc;
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
      <ModalHeader T={T} title={editing ? '编辑报表' : (isDash ? '新建仪表盘报表' : '新建宽表报表')}
        subtitle={isDash ? 'admin 直写 SQL（只读校验）+ 板块布局 JSON（KPI / 折线 / 环形 / 横条 / 迷你表）'
          : 'admin 直写 SQL（只读校验）；覆盖层可插文本 / Excel 式公式'} onClose={onClose} />
      <div className="cb-sb" style={{ padding: 20, maxHeight: '70vh', overflowY: 'auto' }}>
        <Input T={T} label="标题" value={title} onChange={setTitle} placeholder={isDash ? '合约交易总览 · 仪表盘' : '平台日汇总 · 宽表'} required />
        <Select T={T} label="报表类型" value={reportType} onChange={setReportType}
          options={[{ value: 'wide_table', label: '宽表（SQL + 列注释表头 + 覆盖层）' },
            { value: 'dashboard', label: '仪表盘（KPI / 图表 板块布局）' }]} />
        <Select T={T} label="数据源" value={dataSourceId} onChange={setDataSourceId} options={dsOpts} />
        <Select T={T} label="文件夹" value={folderId} onChange={setFolderId} options={folderOpts} />
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12, color: T.subtext, marginBottom: 5, fontWeight: 500 }}>SQL（只读；列别名 → 表头）</div>
          <textarea value={sqlText} onChange={(e) => setSqlText(e.target.value)} rows={6} spellCheck={false}
            placeholder={'SELECT dt AS 日期, coin AS 币种, bal AS 余额\nFROM dwd_daily\nORDER BY dt DESC'}
            style={{
              width: '100%', background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 7,
              padding: '9px 11px', fontSize: 12.5, color: T.text, fontFamily: T.mono, resize: 'vertical',
            }} />
        </div>

        {/* 宽表：覆盖层编辑（D3「插入」= 文本 / 公式）*/}
        {!isDash && (
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

        {/* 仪表盘：板块布局 JSON（KPI / vol / donut / bars / miniRows / insight）*/}
        {isDash && (
        <div style={{ marginTop: 4 }}>
          <div style={{ fontSize: 12, color: T.subtext, marginBottom: 5, fontWeight: 500 }}>板块布局（JSON）</div>
          <textarea value={dashJson} onChange={(e) => setDashJson(e.target.value)} rows={12} spellCheck={false}
            placeholder={'{\n  "kpis": [{"label":"今日交易量","value":"84.2","unit":"亿","main":true,"hint":"环比 +12.4%"}],\n  "volTitle": "近 14 日（亿元）", "vol": [62,70,58,...],\n  "donutTitle": "多空占比", "donut": [{"name":"多头","value":54},{"name":"空头","value":46}], "donutBig": "54%", "donutSub": "多头占比",\n  "barsTitle": "各品种交易量", "bars": [{"label":"BTC 永续","value":38,"valueLabel":"¥38.0亿"}],\n  "miniTitle": "最近强平", "miniRows": [{"time":"09:12","symbol":"BTC 永续","side":"多","notional":"¥182万","status":"已强平"}],\n  "insight": "……"\n}'}
            style={{
              width: '100%', background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 7,
              padding: '9px 11px', fontSize: 12, color: T.text, fontFamily: T.mono, resize: 'vertical', lineHeight: 1.55,
            }} />
          <div style={{ fontSize: 11, color: T.muted, marginTop: 5 }}>字段：kpis[]（label/value/unit/main/hint）· vol[] + volTitle · donut[] + donutBig/donutSub/donutTitle · bars[]（label/value/valueLabel）+ barsTitle · miniRows[] + miniCols/miniTitle · insight。缺省板块自动隐藏。</div>
        </div>
        )}
      </div>
      <div style={{ padding: '14px 20px', borderTop: `1px solid ${T.border}`, display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <button onClick={onClose} style={{ padding: '8px 16px', borderRadius: 7, border: `1px solid ${T.border}`, background: 'transparent', color: T.subtext, cursor: 'pointer', fontFamily: 'inherit', fontSize: 13 }}>取消</button>
        <button onClick={save} disabled={saving} style={{ padding: '8px 18px', borderRadius: 7, border: 'none', background: T.accent, color: T.sendFg, cursor: saving ? 'default' : 'pointer', fontFamily: 'inherit', fontSize: 13, fontWeight: 600, opacity: saving ? 0.6 : 1 }}>
          {saving ? '保存中…' : (editing ? '保存' : '创建')}
        </button>
      </div>
    </Modal>
  );
}
