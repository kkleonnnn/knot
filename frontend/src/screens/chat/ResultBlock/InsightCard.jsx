// v0.6.0.2 F3 — InsightCard 子组件抽出（v0.5.14 R-323 brandSoft 8% inset byte-equal）
// v0.5.14 R-227.5.1 OBSERVATION 装饰豁免延伸 sustained
// 字面与 RB_SVG.info 解耦 — 直接 inline info path（避免 import RB_SVG dict）
const INFO_PATH = 'M12 12m-10 0a10 10 0 1 0 20 0a10 10 0 1 0 -20 0M12 8v4M12 16h.01';

const SvgPath = ({ d, size = 14, fill = 'none' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={fill} stroke="currentColor"
       strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={d}/></svg>
);

export function InsightCard({ T, insight }) {
  if (!insight) return null;
  return (
    <div style={{
      background: `color-mix(in oklch, ${T.accent} 8%, transparent)`,
      border: `1px solid color-mix(in oklch, ${T.accent} 25%, transparent)`,
      borderRadius: 10, padding: '12px 14px',
      display: 'flex', gap: 10, alignItems: 'flex-start',
    }}>
      <span style={{ marginTop: 1, color: T.accent, flexShrink: 0 }}>
        <SvgPath d={INFO_PATH} size={14}/>
      </span>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 11, fontFamily: T.mono, color: T.accent, fontWeight: 600,
                      letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 4 }}>OBSERVATION</div>
        <div style={{ fontSize: 13, color: T.text, lineHeight: 1.6 }}>{insight}</div>
      </div>
    </div>
  );
}
