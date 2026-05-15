// v0.5.10 (C5+) Home 屏复刻；R-227.5 字面分流装饰 "knot · ready" 小写 vs 声明 "KNOT 可能出错" 大写
// v0.5.30 #33 — suggestion icons 改 demo "spark"/"flow" 风格（Q2 VRP 局部例外 — Shared 无 spark/flow）
import { I } from '../../Shared.jsx';
import { Composer } from './Composer.jsx';

// v0.5.30 #33 — demo ui.jsx spark/flow path byte-equal
const SparkIcon = (p) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M12 3v6M12 15v6M3 12h6M15 12h6"/></svg>;
const FlowIcon  = (p) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...p}><circle cx="6" cy="6" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="12" cy="18" r="2"/><path d="M8 6h8M7 7l4 9M17 7l-4 9"/></svg>;

export function ChatEmpty({ T, user, question, setQuestion, loading, onSubmit, onKeyDown,
                           activeUpload, setActiveUpload, onUpload }) {
  const firstName = user?.display_name?.split(' ')[0] || user?.username || '你';
  const suggestions = [
    { Icon: SparkIcon, text: '今天的合约交易总量是多少？' },
    { Icon: FlowIcon,  text: '最近 7 天每日平台总盈亏趋势' },
    { Icon: I.users,   text: '新用户注册数量（本月）' },
    { Icon: I.db,      text: '查看数据库有哪些表' },
  ];
  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      padding: '0 80px', paddingBottom: '10vh',
    }}>
      <div style={{ width: '100%', maxWidth: 720, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <div style={{
          fontSize: 11, color: T.accent, fontFamily: T.mono,
          letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 18,
          display: 'inline-flex', alignItems: 'center', gap: 8,
        }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%', background: T.accent,
            boxShadow: `0 0 0 4px color-mix(in oklch, ${T.accent} 13%, transparent)`,
          }}/>
          knot · ready
        </div>
        <h1 style={{
          fontSize: 36, fontWeight: 600, color: T.text,
          letterSpacing: '-0.035em', lineHeight: 1.15,
          margin: 0, textAlign: 'center',
          wordBreak: 'keep-all', maxWidth: 640,
        }}>
          Hi {firstName}，今天想<span style={{
            color: T.accent, display: 'inline-block', minWidth: '1.2em',
          }}>解</span>哪个结？
        </h1>
        <p style={{
          fontSize: 14, color: T.subtext, margin: '12px 0 28px',
          textAlign: 'center', lineHeight: 1.6, maxWidth: 560,
        }}>
          描述你的业务问题，KNOT 会澄清意图 → 生成 SQL → 整理洞察
        </p>
        <Composer T={T} value={question} onChange={setQuestion} loading={loading}
                  onSubmit={onSubmit} onKeyDown={onKeyDown}
                  activeUpload={activeUpload} setActiveUpload={setActiveUpload} onUpload={onUpload}/>
        <div style={{
          width: '100%', marginTop: 16,
          display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 10,
        }}>
          {suggestions.map((s, i) => {
            const Icon = s.Icon;
            return (
              <button key={i} onClick={() => setQuestion(s.text)} style={{
                flex: '1 1 280px', minWidth: 0, height: 44, padding: '0 14px',
                display: 'inline-flex', alignItems: 'center', gap: 10,
                background: T.content, border: `1px solid ${T.border}`, borderRadius: 10,
                cursor: 'pointer', textAlign: 'left',
                color: T.subtext, fontSize: 13, fontFamily: 'inherit',
              }}>
                <span style={{ color: T.accent, display: 'flex', flexShrink: 0 }}><Icon/></span>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.text}</span>
              </button>
            );
          })}
        </div>
        <div style={{
          marginTop: 28, fontSize: 11, color: T.muted,
          fontFamily: T.mono, letterSpacing: '0.04em',
        }}>
          KNOT 可能出错 · 关键结果请核对原始数据
        </div>
        {/* v0.6.1 R-PA-PB-1：窄场景宣告 — 简要 hint，详 README §能做不能做 */}
        <div style={{
          marginTop: 6, fontSize: 10.5, color: T.muted, opacity: 0.7,
          letterSpacing: '0.02em',
        }}>
          当前支持 SELECT 类查询 · 复杂归因 / 跨域分析 / 动作触发等场景见 README
        </div>
      </div>
    </div>
  );
}
