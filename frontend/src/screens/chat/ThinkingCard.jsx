// v0.5.3 extracted from Chat.jsx；v0.5.12 (C5+) Thinking 屏复刻 R-266~R-291
// R-227.5.1 单字母装饰豁免：K/N/O letter chip 是导航标识，不构成完整 KNOT 字面
import { TypingDots } from '../../Shared.jsx';

// letter chip K/N/O 22×22 Inter 800 flex 居中（R-277/R-289）
function LetterChip({ T, letter }) {
  return (
    <span style={{
      width: 22, height: 22, borderRadius: 5,
      background: T.accent, color: T.sendFg,
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 11, fontWeight: 800,
      fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
      flexShrink: 0,
    }}>{letter}</span>
  );
}

// done 态 svg checkmark 11×11 stroke 2.5（R-281）
function DoneCheck({ T }) {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke={T.success}
         strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  );
}

export function ThinkingCard({ T, agentEvents = [] }) {
  const AGENT_LABELS = { clarifier: '理解问题', sql_planner: '生成 SQL', presenter: '整理洞察' };
  const lastStart = [...agentEvents].reverse().find(e => e.type === 'agent_start');
  const label = lastStart ? AGENT_LABELS[lastStart.agent] || lastStart.label : '正在思考';
  return (
    <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '13px 16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: T.subtext }}>
        <TypingDots color={T.accent}/>
        <span>{agentEvents.length > 0 ? `${label}…` : '正在生成 SQL…'}</span>
      </div>
    </div>
  );
}

export function AgentThinkingPanel({ T, events, visible }) {
  // R-290 SSE 兜底：visible 控制 + events 空/异常 optional chaining
  if (!visible) return null;
  const safeEvents = Array.isArray(events) ? events : [];

  // AGENTS 扩 letter/name 字段（R-227.5.1 装饰豁免 K/N/O）
  const AGENTS = [
    { key: 'clarifier',   label: '理解问题', letter: 'K', name: 'Knowledge' },
    { key: 'sql_planner', label: '生成 SQL', letter: 'N', name: 'Nexus' },
    { key: 'presenter',   label: '整理洞察', letter: 'O', name: 'Objective' },
  ];

  const getStatus = (key) => {
    const started = safeEvents.some(e => e?.type === 'agent_start' && e?.agent === key);
    const done    = safeEvents.some(e => e?.type === 'agent_done'  && e?.agent === key);
    if (!started) return 'pending';
    return done ? 'done' : 'thinking';
  };
  const getDoneOutput = (key) => {
    const ev = safeEvents.find(e => e?.type === 'agent_done' && e?.agent === key);
    return ev?.output || null;
  };
  const sqlSteps = safeEvents.filter(e => e?.type === 'sql_step');
  const doneCount = AGENTS.filter(({ key }) => getStatus(key) === 'done').length;

  return (
    // Panel 320 (R-276)；R-288 Conversation 0 改前置已确认（无 margin-right 字面）
    <aside style={{
      width: 320, flexShrink: 0, height: '100%', overflowY: 'auto',
      borderLeft: `1px solid ${T.border}`, background: T.sidebar,
      display: 'flex', flexDirection: 'column',
    }} className="cb-sb">
      {/* Header step count + transition cubic-bezier (R-280/R-287) */}
      <div style={{
        padding: '14px 18px', borderBottom: `1px solid ${T.border}`,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: T.text }}>思考过程</span>
        <span style={{
          marginLeft: 'auto', fontSize: 10, color: T.muted, fontFamily: T.mono,
          letterSpacing: '0.06em',
          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        }}>{doneCount}/{AGENTS.length} STEPS</span>
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
      {AGENTS.map(({ key, label, letter, name }) => {
        const status = getStatus(key);
        const output = getDoneOutput(key);
        const isPending  = status === 'pending';
        const isThinking = status === 'thinking';
        const isDone     = status === 'done';
        return (
          // 卡片 bg T.content + radius 10 + padding 12 (R-279/R-283)
          // isThinking border 用 color-mix(oklch) 替代 alpha 拼接（R-286）
          <div key={key} style={{
            background: T.content, borderRadius: 10,
            border: `1px solid ${isThinking ? `color-mix(in oklch, ${T.accent} 38%, transparent)` : T.border}`,
            padding: 12, opacity: isPending ? 0.45 : 1,
            transition: 'all .2s',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: output || (isThinking && key === 'sql_planner') ? 8 : 0 }}>
              <LetterChip T={T} letter={letter}/>
              <span style={{ fontSize: 10, fontFamily: T.mono, color: T.muted,
                             letterSpacing: '0.08em', textTransform: 'uppercase' }}>{name}</span>
              <span style={{ fontSize: 12.5, fontWeight: 500, color: T.text, flex: 1, marginLeft: 4 }}>{label}</span>
              {isDone     && <DoneCheck T={T}/>}
              {isThinking && <TypingDots color={T.accent}/>}
              {isPending  && <span style={{ fontSize: 10, color: T.muted }}>○</span>}
            </div>

            {key === 'clarifier' && isDone && output?.refined_question && (
              <div style={{ fontSize: 11.5, color: T.subtext, lineHeight: 1.55 }}>
                <div style={{ color: T.muted, fontSize: 10.5, marginBottom: 2 }}>精确问题</div>
                <div style={{ color: T.text }}>{output.refined_question}</div>
                {output?.approach && <div style={{ color: T.muted, marginTop: 4, fontSize: 10.5 }}>{output.approach}</div>}
              </div>
            )}

            {key === 'sql_planner' && (isThinking || isDone) && sqlSteps.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {sqlSteps.map((s, i) => {
                  const text = (s?.thought ? s.thought.slice(0, 120) : s?.action) || '';
                  const truncated = s?.thought && s.thought.length > 120;
                  return (
                    <div key={i} style={{ display: 'flex', gap: 8, fontSize: 11.5, color: T.muted, lineHeight: 1.55 }}>
                      {s?.step > 0 && <span style={{
                        flexShrink: 0, fontSize: 10, fontFamily: T.mono, color: T.accent, fontWeight: 600,
                        padding: '0 5px', height: 16, display: 'inline-flex', alignItems: 'center',
                        background: T.accentSoft, borderRadius: 3,
                      }}>S{s.step}</span>}
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{text}{truncated ? '…' : ''}</span>
                    </div>
                  );
                })}
              </div>
            )}

            {key === 'presenter' && isDone && output?.insight && (
              <div style={{ fontSize: 11.5, color: T.subtext, lineHeight: 1.5 }}>
                {output?.confidence && output.confidence !== 'high' && (
                  <span style={{
                    fontSize: 10.5, fontWeight: 600, padding: '1px 5px', borderRadius: 4, marginRight: 6,
                    background: output.confidence === 'medium'
                      ? `color-mix(in oklch, ${T.warn} 13%, transparent)` : T.accentSoft,
                    color: output.confidence === 'medium' ? T.warn : T.accent,
                  }}>{output.confidence}</span>
                )}
                {output.insight.slice(0, 100)}{output.insight.length > 100 ? '…' : ''}
              </div>
            )}
          </div>
        );
      })}
      </div>
    </aside>
  );
}
