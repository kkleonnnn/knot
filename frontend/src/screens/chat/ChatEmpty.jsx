// v0.5.3: extracted from Chat.jsx L302-335 (ChatEmpty 空对话状态)
// R-126 brand：'KNOT 可能出错' 提示文字逐字保留。
import { I } from '../../Shared.jsx';
import { Composer } from './Composer.jsx';

export function ChatEmpty({ T, user, question, setQuestion, loading, onSubmit, onKeyDown,
                           activeUpload, setActiveUpload, onUpload }) {
  const firstName = user?.display_name?.split(' ')[0] || user?.username || '你';
  const suggestions = [
    '今天的订单总量是多少？',
    '最近 7 天每日 GMV 趋势',
    '新用户注册数量（本月）',
    '查看数据库有哪些表',
  ];
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '24px 28px' }}>
      <div style={{ width: '100%', maxWidth: 640, textAlign: 'center', marginBottom: 22 }}>
        <div style={{ fontSize: 28, fontWeight: 600, color: T.text, letterSpacing: '-0.02em', marginBottom: 8 }}>Hi {firstName}</div>
        <div style={{ fontSize: 14, color: T.subtext }}>今天想了解哪部分业务数据？</div>
      </div>
      <Composer T={T} value={question} onChange={setQuestion} loading={loading}
                onSubmit={onSubmit} onKeyDown={onKeyDown}
                                activeUpload={activeUpload} setActiveUpload={setActiveUpload} onUpload={onUpload}/>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8, marginTop: 14, maxWidth: 640, width: '100%' }}>
        {suggestions.map((s, i) => (
          <button key={i} onClick={() => setQuestion(s)} style={{
            display: 'flex', alignItems: 'center', gap: 10, padding: '11px 13px',
            border: `1px solid ${T.border}`, borderRadius: 8,
            cursor: 'pointer', background: T.content, textAlign: 'left',
            color: T.subtext, fontSize: 12.5, fontFamily: 'inherit',
          }}>
            <I.sparkle style={{ color: T.accent, flexShrink: 0 }}/>
            {s}
          </button>
        ))}
      </div>
      <div style={{ marginTop: 20, fontSize: 11, color: T.muted }}>KNOT 可能出错 · 关键结果请核对原始数据</div>
    </div>
  );
}
