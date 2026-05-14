// v0.6.0.2 F2 — TableContainer 子组件抽出（chart + table 复合容器）
// v0.5.38 thead 底色 T.bg gray sustained（资深反馈"底色改成灰色"）
// v0.5.14 R-327 thead 删 uppercase + letter-spacing normal — 注：原版 ResultBlock 仍 uppercase（与 R-327 范围不同）
// v0.5.13 R-302.5 业务 emoji 豁免 sustained
import { I, iconBtn, LineChart, BarChart, PieChart } from '../../../Shared.jsx';

const CHART_BTNS = [
  { id: 'line', label: '折线' },
  { id: 'bar',  label: '柱状' },
  { id: 'pie',  label: '饼图' },
];

export function TableContainer({ T, rows, cols, labelCols, numericCols, chartable, isMetric, isDetail, isRetention,
                                  showChart, chartData, pieData, chartType, setChartType, activeType,
                                  isDateLike, msg, onDownload, exportMessageCsv }) {
  return (
    <>
      {showChart && (
        <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '12px 12px 10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <span style={{ fontSize: 11, color: T.muted, fontFamily: T.mono }}>{labelCols[0]} · {numericCols[0]}</span>
            <div style={{ display: 'flex', gap: 3 }}>
              {CHART_BTNS.map(btn => (
                <button key={btn.id} onClick={() => setChartType(btn.id)} style={{
                  padding: '3px 9px', borderRadius: 5, fontSize: 11, fontFamily: 'inherit', cursor: 'pointer',
                  background: activeType === btn.id ? T.accent : 'transparent',
                  color: activeType === btn.id ? T.sendFg : T.muted,
                  border: `1px solid ${activeType === btn.id ? T.accent : T.border}`,
                  transition: 'all .15s',
                }}>{btn.label}</button>
              ))}
            </div>
          </div>
          {activeType === 'line' && <LineChart data={chartData} stroke={T.accent} fill labelColor={T.muted} gridColor={T.borderSoft} width={640} height={190}/>}
          {activeType === 'bar'  && <BarChart  data={chartData} color={T.accent} labelColor={T.muted} gridColor={T.borderSoft} width={640} height={210}/>}
          {activeType === 'pie'  && <PieChart  data={pieData} width={640} height={210} labelColor={T.muted}/>}
        </div>
      )}
      <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ padding: '10px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: `1px solid ${T.border}` }}>
          <span style={{ fontSize: 12, color: T.muted, fontFamily: T.mono }}>{rows.length} 行 · {cols.length} 列</span>
          {isDetail && msg.id
            ? <button onClick={() => exportMessageCsv(msg.id)} style={{ ...iconBtn(T), gap: 4, fontSize: 11 }} title="导出 CSV"><I.dl/></button>
            : <button onClick={() => onDownload(rows, msg.question)} style={{ ...iconBtn(T), gap: 4, fontSize: 11 }} title="下载 CSV"><I.dl/></button>}
        </div>
        <div className="cb-sb" style={{ overflowX: 'auto', maxHeight: 280 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              {/* v0.5.38 全站表头底色 brandSoft 8% → T.bg gray sustained */}
              <tr style={{ background: T.bg }}>
                {cols.map(c => <th key={c} style={{ padding: '8px 12px', textAlign: 'left', color: T.muted, fontFamily: T.mono, fontWeight: 500, fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}`, whiteSpace: 'nowrap' }}>{c}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 100).map((row, ri) => (
                <tr key={ri} style={{ borderBottom: ri < rows.length - 1 ? `1px solid ${T.borderSoft}` : 'none' }}>
                  {cols.map(c => <td key={c} style={{ padding: '8px 12px', color: T.text, whiteSpace: 'nowrap', fontFamily: typeof row[c] === 'number' ? T.mono : 'inherit' }}>{row[c] === null || row[c] === undefined ? <span style={{ color: T.muted }}>—</span> : String(row[c])}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
