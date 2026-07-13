// InsightCard.jsx — v0.8.5 (②a) 报表底部洞察卡（brandSoft 8% + AI 生成 标签）。
// v0.8.11 kk：剔除左侧 3px accent borderLeft（视觉太重）→ 仅 brandSoft 底 + 细描边。
export function InsightCard({ T, text }) {
  if (!text) return null;
  return (
    <div style={{
      marginTop: 18, padding: '14px 16px', borderRadius: 10,
      background: 'color-mix(in oklch, ' + T.accent + ' 8%, transparent)',
      border: `1px solid ${T.borderSoft}`,
    }}>
      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, color: T.accent, fontWeight: 600, marginBottom: 6 }}>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M9 18h6M10 21h4M12 3a6 6 0 0 1 4 10.5c-.7.6-1 1-1 2H9c0-1-.3-1.4-1-2A6 6 0 0 1 12 3z" /></svg>
        洞察 · AI 生成
      </div>
      <div style={{ fontSize: 12.5, color: T.subtext, lineHeight: 1.7 }}>{text}</div>
    </div>
  );
}
