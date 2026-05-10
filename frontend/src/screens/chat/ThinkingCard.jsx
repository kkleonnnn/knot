// v0.5.3: extracted from Chat.jsx L381-393 (ThinkingCard) + L767-859 (AgentThinkingPanel 侧边栏)
import { TypingDots } from '../../Shared.jsx';

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
  if (!visible) return null;

  const AGENTS = [
    { key: 'clarifier',   label: '理解问题', emoji: '💡' },
    { key: 'sql_planner', label: '生成 SQL', emoji: '🔍' },
    { key: 'presenter',   label: '整理洞察', emoji: '📊' },
  ];

  const getStatus = (key) => {
    const started = events.some(e => e.type === 'agent_start' && e.agent === key);
    const done    = events.some(e => e.type === 'agent_done'  && e.agent === key);
    if (!started) return 'pending';
    return done ? 'done' : 'thinking';
  };

  const getDoneOutput = (key) => {
    const ev = events.find(e => e.type === 'agent_done' && e.agent === key);
    return ev?.output || null;
  };

  const sqlSteps = events.filter(e => e.type === 'sql_step');

  return (
    <aside style={{
      width: 272, flexShrink: 0, height: '100%', overflowY: 'auto',
      borderLeft: `1px solid ${T.border}`, background: T.sidebar,
      padding: '16px 12px', display: 'flex', flexDirection: 'column', gap: 8,
    }} className="cb-sb">
      <div style={{ fontSize: 11.5, fontWeight: 600, color: T.muted, letterSpacing: '0.05em',
                    textTransform: 'uppercase', marginBottom: 4 }}>思考过程</div>

      {AGENTS.map(({ key, label, emoji }) => {
        const status = getStatus(key);
        const output = getDoneOutput(key);
        const isPending  = status === 'pending';
        const isThinking = status === 'thinking';
        const isDone     = status === 'done';

        return (
          <div key={key} style={{
            background: T.card, borderRadius: 8,
            border: `1px solid ${isThinking ? T.accent + '60' : T.border}`,
            padding: '10px 12px', opacity: isPending ? 0.45 : 1,
            transition: 'all .2s',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: output || (isThinking && key === 'sql_planner') ? 6 : 0 }}>
              <span style={{ fontSize: 13 }}>{emoji}</span>
              <span style={{ fontSize: 12.5, fontWeight: 500, color: T.text, flex: 1 }}>{label}</span>
              {isDone     && <span style={{ fontSize: 10, color: T.success || '#09AB3B', fontWeight: 600 }}>✓</span>}
              {isThinking && <TypingDots color={T.accent}/>}
              {isPending  && <span style={{ fontSize: 10, color: T.muted }}>○</span>}
            </div>

            {key === 'clarifier' && isDone && output?.refined_question && (
              <div style={{ fontSize: 11.5, color: T.subtext, lineHeight: 1.55 }}>
                <div style={{ color: T.muted, fontSize: 10.5, marginBottom: 2 }}>精确问题</div>
                <div style={{ color: T.text }}>{output.refined_question}</div>
                {output.approach && <div style={{ color: T.muted, marginTop: 4, fontSize: 10.5 }}>{output.approach}</div>}
              </div>
            )}

            {key === 'sql_planner' && (isThinking || isDone) && sqlSteps.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {sqlSteps.map((s, i) => (
                  <div key={i} style={{ fontSize: 11, color: T.muted, lineHeight: 1.45,
                                        paddingLeft: 8, borderLeft: `2px solid ${T.border}` }}>
                    {s.step > 0 && <span style={{ color: T.accent, fontWeight: 600, marginRight: 4 }}>S{s.step}</span>}
                    {s.thought ? s.thought.slice(0, 80) : s.action}
                    {s.thought && s.thought.length > 80 ? '…' : ''}
                  </div>
                ))}
              </div>
            )}

            {key === 'presenter' && isDone && output?.insight && (
              <div style={{ fontSize: 11.5, color: T.subtext, lineHeight: 1.5 }}>
                {output.confidence && output.confidence !== 'high' && (
                  <span style={{
                    fontSize: 10.5, fontWeight: 600, padding: '1px 5px', borderRadius: 4, marginRight: 6,
                    background: output.confidence === 'medium' ? '#FF990022' : T.accentSoft,
                    color: output.confidence === 'medium' ? '#FF9900' : T.accent,
                  }}>{output.confidence}</span>
                )}
                {output.insight.slice(0, 100)}{output.insight.length > 100 ? '…' : ''}
              </div>
            )}
          </div>
        );
      })}
    </aside>
  );
}
