// v0.6.0.2 F4 — BudgetBanner 子组件抽出（v0.4.3 R-16~23 budget 状态映射 byte-equal）
// v0.5.13 R-304 emoji → SvgPath shield/triangle byte-equal
// v0.4.3 R-20 sessionStorage 降噪逻辑保留在父组件（dismissKey 父级管控）
const SHIELD_PATH = 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z';
const TRIANGLE_PATH = 'M12 3L2 21h20L12 3zM12 10v6M12 18v.01';

const SvgPath = ({ d, size = 14, fill = 'none' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={fill} stroke="currentColor"
       strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={d}/></svg>
);

export function BudgetBanner({ T, budget_status, budget_meta, onDismiss }) {
  if (!budget_meta) return null;
  return (
    <div style={{
      padding: '10px 14px', borderRadius: 8,
      background: budget_status === 'block'
        ? T.accentSoft
        : `color-mix(in oklch, ${T.warn} 13%, transparent)`,
      border: `1px solid ${budget_status === 'block' ? T.accent : T.warn}`,
      color: budget_status === 'block' ? T.accent : T.warn,
      fontSize: 12.5, display: 'flex', alignItems: 'center', gap: 10,
    }}>
      <SvgPath d={budget_status === 'block' ? SHIELD_PATH : TRIANGLE_PATH} size={16}/>
      <span style={{ flex: 1 }}>
        {budget_status === 'block' ? '预算已达硬阈值（block）' : '预算告警'}：
        本月已用 <strong>{budget_meta.percentage}%</strong> 配额（${budget_meta.current?.toFixed(4)} / ${budget_meta.threshold?.toFixed(2)} {budget_meta.budget_type}）
      </span>
      <button onClick={onDismiss} style={{
        padding: '4px 10px', borderRadius: 5, fontSize: 11,
        border: '1px solid currentColor', background: 'transparent', color: 'inherit',
        cursor: 'pointer', fontFamily: 'inherit',
      }}>本会话不再提醒</button>
    </div>
  );
}
