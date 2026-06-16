import { inputStyleField, pageBtnStyle } from '../../Shared.jsx';

// v0.6.3.2 C5 — AdminAudit 子组件拆分（dumb presentational）
// R-61 强制分页：默认 50 / 上限 200（与后端一致）
const _PAGE_SIZES = [50, 100, 200];

// v0.5.32 Pagination 对齐 demo audit.jsx L149-154 — "1 - 8 / 12,408" 简洁字面 + 左 range / 右 buttons
// R-430 翻页边界 disabled（page===1 上一页 / items.length<size 下一页）
export function AuditPagination({ T, items, page, size, setPage, setSize }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: T.muted }}>
      <span style={{ fontFamily: T.mono }}>
        {items.length === 0 ? '0 / 0' : `${(page - 1) * size + 1} - ${(page - 1) * size + items.length}`}
      </span>
      <div style={{ flex: 1 }}/>
      <select value={size} onChange={e => { setSize(parseInt(e.target.value)); setPage(1); }}
              style={{...inputStyleField(T), width: 'auto', height: 28, fontSize: 11.5}}>
        {_PAGE_SIZES.map(s => <option key={s} value={s}>{s} / 页</option>)}
      </select>
      <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1}
              style={pageBtnStyle(T, page === 1)}>‹ 上一页</button>
      <button onClick={() => setPage(page + 1)} disabled={items.length < size}
              style={pageBtnStyle(T, items.length < size)}>下一页 ›</button>
    </div>
  );
}
