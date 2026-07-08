// WideTableReport.jsx — v0.8.5 (②a) 宽表报表（单 SQL）。v0.8.7：表体核心抽到 <WideTable>（页签复用）。
// 本组件 = 装饰性 sheet 页签（日/周/月，视觉态；单 SQL 报表数据不随页切换）+ WideTable 表体。
// 真·多页表（每页一条 SQL）见 TabbedTableReport（report_type='tabbed'）。
import { useMemo, useState } from 'react';
import { WideTable } from './WideTable.jsx';

const SHEETS = ['日汇总', '周汇总', '月汇总'];

export function WideTableReport({ T, report }) {
  const [tab, setTab] = useState(0);
  const rows = useMemo(() => { try { return JSON.parse(report.last_run_rows_json || '[]'); } catch { return []; } }, [report.last_run_rows_json]);
  const cfg = useMemo(() => { try { return report.column_config ? JSON.parse(report.column_config) : {}; } catch { return {}; } }, [report.column_config]);
  const overlay = useMemo(() => { try { return report.overlay_config ? JSON.parse(report.overlay_config) : []; } catch { return []; } }, [report.overlay_config]);

  // 页签接缝（kk 修）：表体保完整上边框；选中标签 border(l/t/r) + border-bottom=bg（仅咬脚下 1px）+
  // margin-bottom:-1 骑到上边框上；未选中 border-bottom:none + margin-bottom:0 落在上边框上（线可见）。
  const tabStyle = (on) => ({
    padding: '8px 16px', background: on ? T.bg : T.content, border: `1px solid ${T.border}`,
    borderBottom: on ? `1px solid ${T.bg}` : 'none', marginBottom: on ? -1 : 0, borderRadius: '7px 7px 0 0',
    color: on ? T.accent : T.subtext, fontSize: 12.5, fontFamily: T.sans, cursor: 'pointer', fontWeight: on ? 600 : 500,
  });

  // 空报表（未跑）不显示装饰页签，只出「暂无数据」—— 保 ②a 抽 WideTable 前行为（复核 minor 修）
  const isEmpty = !rows.length && !overlay.length;
  return (
    <div>
      {!isEmpty && (
        <div style={{ display: 'flex', alignItems: 'flex-end' }}>
          {SHEETS.map((s, i) => (
            <button key={s} onClick={() => setTab(i)} style={tabStyle(i === tab)}>{s}</button>
          ))}
        </div>
      )}
      <WideTable T={T} rows={rows} cfg={cfg} overlay={overlay} />
    </div>
  );
}
