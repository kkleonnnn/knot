// v0.6.0.2 F6 — TokenMeter 子组件抽出（v0.5.14 R-325 inline stat + svg ↑↓ byte-equal）
// v0.5.13 R-306/315 撤回（v0.5.14 红线撤回首例 sustained）— 不复用 TokenPill helper
const ARROW_UP_PATH = 'M12 19V5M5 12l7-7 7 7';
const ARROW_DOWN_PATH = 'M12 5v14M19 12l-7 7-7-7';

const SvgPath = ({ d, size = 14, fill = 'none' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={fill} stroke="currentColor"
       strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={d}/></svg>
);

export function TokenMeter({ T, input_tokens, output_tokens, cost_usd, confidence, recovery_attempt }) {
  if (!(input_tokens > 0 || output_tokens > 0)) return null;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 11, fontFamily: T.mono, color: T.muted, paddingLeft: 2, flexWrap: 'wrap' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        <SvgPath d={ARROW_UP_PATH} size={10}/> {input_tokens?.toLocaleString()} tok
      </span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        <SvgPath d={ARROW_DOWN_PATH} size={10}/> {output_tokens?.toLocaleString()} tok
      </span>
      {cost_usd > 0 && <span>$ {cost_usd?.toFixed(5)}</span>}
      {confidence && (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4,
                       color: confidence === 'high' ? T.success : confidence === 'medium' ? T.warn : T.accent }}>
          <span style={{ width: 4, height: 4, borderRadius: '50%', background: 'currentColor' }}/>
          {confidence}
        </span>
      )}
      {recovery_attempt > 0 && (
        <span title="自纠正次数（fan-out reject + fix_sql retry）"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: T.warn }}>
          ↻ {recovery_attempt}
        </span>
      )}
    </div>
  );
}
