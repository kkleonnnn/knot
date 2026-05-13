// v0.5.3: extracted from Chat.jsx L337-379 (ChatConversation 会话主视图)
// v0.5.31 #37 avatar → KnotMark；#40 thinking panel 永显（demo grid 一直保留右栏）
import { KnotMark } from '../../Shared.jsx';
import { ResultBlock } from './ResultBlock.jsx';
import { ThinkingCard, AgentThinkingPanel } from './ThinkingCard.jsx';
import { Composer } from './Composer.jsx';

export function ChatConversation({ T, messages, scrollRef, loading, question, setQuestion,
                                  onSubmit, onKeyDown, onCopy, onDownload, onPin, onRetry,
                                  agentEvents, activeUpload, setActiveUpload, onUpload }) {
  return (
    <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
        <div ref={scrollRef} className="cb-sb" style={{ flex: 1, overflowY: 'auto', padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          {messages.map((msg, i) => (
            <div key={msg.id || i} className="cb-fadein">
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
                {/* v0.5.38 — borderTopRightRadius 4 → 12 统一四角（资深反馈"右上和其他三个角不一致"）*/}
                <div style={{
                  background: T.chipBg, border: `1px solid ${T.chipBorder}`, color: T.text,
                  padding: '10px 14px', borderRadius: 12,
                  fontSize: 14, maxWidth: 520,
                }}>{msg.question}</div>
              </div>
              <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                {/* v0.5.31 #37 — avatar → KnotMark（demo thinking.jsx L91-93 byte-equal；删 T.accent bg + I.sparkle） */}
                <div style={{ marginTop: 2, flexShrink: 0 }}>
                  <KnotMark T={T} size={26}/>
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
      {/* v0.5.31 #40 — Thinking panel 永显（demo grid 208/1fr/320 三列；删 showPanel 条件渲染） */}
      <AgentThinkingPanel T={T} events={agentEvents} visible={true}/>
    </div>
  );
}
