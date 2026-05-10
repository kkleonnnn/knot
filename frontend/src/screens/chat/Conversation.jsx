// v0.5.3: extracted from Chat.jsx L337-379 (ChatConversation 会话主视图)
import { I } from '../../Shared.jsx';  // noqa: F401  保留 Shared import 风格一致
import { ResultBlock } from './ResultBlock.jsx';
import { ThinkingCard, AgentThinkingPanel } from './ThinkingCard.jsx';
import { Composer } from './Composer.jsx';

// I 未直接使用，但 import 与原 Chat.jsx 一致风格保留；如 lint 报警可移除
// （sparkle icon 在内部 div 内嵌使用 — 见 L19）
export function ChatConversation({ T, messages, scrollRef, loading, question, setQuestion,
                                  onSubmit, onKeyDown, onCopy, onDownload, onPin, onRetry,
                                  agentEvents, activeUpload, setActiveUpload, onUpload }) {
  const showPanel = agentEvents.length > 0;
  return (
    <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
        <div ref={scrollRef} className="cb-sb" style={{ flex: 1, overflowY: 'auto', padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          {messages.map((msg, i) => (
            <div key={msg.id || i} className="cb-fadein">
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
                <div style={{
                  background: T.chipBg, border: `1px solid ${T.chipBorder}`, color: T.text,
                  padding: '10px 14px', borderRadius: 12, borderTopRightRadius: 4,
                  fontSize: 14, maxWidth: 520,
                }}>{msg.question}</div>
              </div>
              <div style={{ display: 'flex', gap: 10 }}>
                <div style={{ width: 26, height: 26, borderRadius: 6, flexShrink: 0, background: T.accent, color: '#fff', display: 'grid', placeItems: 'center', boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.25)' }}>
                  <I.sparkle width="14" height="14"/>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  {msg.loading
                    ? <ThinkingCard T={T} agentEvents={agentEvents}/>
                    : <ResultBlock T={T} msg={msg} onCopy={onCopy} onDownload={onDownload}
                                   onPin={onPin} onRetry={onRetry}
                                   onFollowup={(q) => setQuestion(q)}/>}
                </div>
              </div>
            </div>
          ))}
        </div>
        <div style={{ padding: '10px 28px 18px', background: `linear-gradient(to top, ${T.content} 80%, ${T.content}00)` }}>
          <div style={{ maxWidth: 800, margin: '0 auto' }}>
            <Composer T={T} value={question} onChange={setQuestion} loading={loading}
                      onSubmit={onSubmit} onKeyDown={onKeyDown}
                                            activeUpload={activeUpload} setActiveUpload={setActiveUpload} onUpload={onUpload}
                      placeholder="继续追问…"/>
          </div>
        </div>
      </div>
      {showPanel && <AgentThinkingPanel T={T} events={agentEvents} visible={showPanel}/>}
    </div>
  );
}
