// SkillPanelPlaceholder.jsx — v0.8.5 (②a) BI 右栏 da-asst 占位（③ 真接）。
// 占位壳 + 缩进/展开（点 3 的交互形态先占位；da-asst 嵌入形态 = ③ 最大设计决策）。
export function SkillPanelPlaceholder({ T, collapsed, onToggle }) {
  if (collapsed) {
    return (
      <button onClick={onToggle} title="展开数据分析"
        style={{
          width: 32, flexShrink: 0, alignSelf: 'stretch', border: `1px solid ${T.border}`,
          borderRadius: 12, background: T.card, color: T.subtext, cursor: 'pointer',
          display: 'grid', placeItems: 'center', fontFamily: T.sans, fontSize: 12,
        }}>
        <span style={{ writingMode: 'vertical-rl', letterSpacing: '0.1em' }}>数据分析 «</span>
      </button>
    );
  }
  return (
    <aside style={{
      width: 300, flexShrink: 0, border: `1px solid ${T.border}`, borderRadius: 12,
      background: T.card, display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      <div style={{
        height: 48, padding: '0 14px', flexShrink: 0, display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', borderBottom: `1px solid ${T.border}`,
      }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: T.text }}>数据分析</span>
        <button onClick={onToggle} title="收起面板"
          style={{ border: 'none', background: 'transparent', color: T.subtext, cursor: 'pointer', fontSize: 15 }}>»</button>
      </div>
      <div style={{ flex: 1, display: 'grid', placeItems: 'center', padding: 24, textAlign: 'center' }}>
        <div>
          <div style={{
            width: 40, height: 40, margin: '0 auto 12px', borderRadius: 10,
            background: T.accentSoft, display: 'grid', placeItems: 'center',
          }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={T.accent} strokeWidth="1.6"
                 strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3a4 4 0 0 1 4 4c0 1.5-.8 2.5-1.5 3.2M12 3a4 4 0 0 0-4 4c0 1.5.8 2.5 1.5 3.2M9.5 21h5M12 14v7" />
              <circle cx="12" cy="7" r="1" fill={T.accent} />
            </svg>
          </div>
          <div style={{ fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 4 }}>数据分析助手</div>
          <div style={{ fontSize: 12, color: T.muted, lineHeight: 1.6 }}>
            即将上线 —— 基于本报表的可交互解读 / 出报告（da-asst）。
          </div>
        </div>
      </div>
      <div style={{ padding: '10px 14px', borderTop: `1px solid ${T.border}`, fontSize: 11, color: T.muted, textAlign: 'center' }}>
        仅解读 · 不改写报表
      </div>
    </aside>
  );
}
