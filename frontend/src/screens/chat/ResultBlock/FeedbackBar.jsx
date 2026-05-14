// v0.6.0.3 F-A — 用户对单条回答的 +1/-1 反馈条
// 抽出原因：ResultBlock LIMIT 280；feedback + Modal 合计 ~90 行超限
// M-A1 复用 Shared I.thumbsUp/Down；M-A4 复用 utils.jsx Modal/ModalHeader（非新建 FeedbackModal）
import { useState } from 'react';
import { I, iconBtn } from '../../../Shared.jsx';
import { Modal, ModalHeader, toast } from '../../../utils.jsx';

export function FeedbackBar({ T, mid, initialScore, onFeedback, suppress }) {
  const [score, setScore] = useState(initialScore ?? null);
  const [modalOpen, setModalOpen] = useState(false);
  const [comment, setComment] = useState('');
  if (suppress) return null;
  if (typeof mid !== 'number' || mid <= 0 || !onFeedback) return null;
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: T.muted }}>
        <span style={{ fontFamily: T.mono, letterSpacing: '0.04em' }}>这条回答有用吗？</span>
        <button
          onClick={async () => {
            const ok = await onFeedback(mid, 1, '');
            if (ok) { setScore(1); toast('感谢反馈'); }
          }}
          disabled={score === 1}
          title="有用"
          style={{
            ...iconBtn(T),
            color: score === 1 ? T.success : T.muted,
            cursor: score === 1 ? 'default' : 'pointer',
          }}>
          <I.thumbsUp/>
        </button>
        <button
          onClick={() => setModalOpen(true)}
          disabled={score === -1}
          title="可以改进"
          style={{
            ...iconBtn(T),
            color: score === -1 ? T.warn : T.muted,
            cursor: score === -1 ? 'default' : 'pointer',
          }}>
          <I.thumbsDown/>
        </button>
      </div>
      {modalOpen && (
        <Modal onClose={() => setModalOpen(false)}>
          <ModalHeader T={T} title="可以改进的地方？" onClose={() => setModalOpen(false)}/>
          <div style={{ padding: '4px 24px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <textarea
              value={comment}
              onChange={e => setComment(e.target.value.slice(0, 500))}
              placeholder="可选 · 哪里有问题？SQL 错了 / 解读不准 / 图表不对 ..."
              rows={4}
              style={{
                width: '100%', padding: '10px 12px', resize: 'vertical',
                border: `1px solid ${T.border}`, borderRadius: 8,
                background: T.content, color: T.text,
                fontFamily: 'inherit', fontSize: 13, lineHeight: 1.5,
                boxSizing: 'border-box',
              }}/>
            <div style={{ fontSize: 11, color: T.muted, fontFamily: T.mono, textAlign: 'right' }}>
              {comment.length}/500
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button
                onClick={() => { setModalOpen(false); setComment(''); }}
                style={{
                  padding: '8px 14px', borderRadius: 6, border: `1px solid ${T.border}`,
                  background: 'transparent', color: T.text, fontSize: 13, cursor: 'pointer',
                  fontFamily: 'inherit',
                }}>取消</button>
              <button
                onClick={async () => {
                  const ok = await onFeedback(mid, -1, comment.trim());
                  if (ok) {
                    setScore(-1);
                    setModalOpen(false);
                    setComment('');
                    toast('已记录，谢谢反馈');
                  }
                }}
                style={{
                  padding: '8px 14px', borderRadius: 6, border: 'none',
                  background: T.accent, color: T.sendFg, fontSize: 13, fontWeight: 500,
                  cursor: 'pointer', fontFamily: 'inherit',
                }}>提交</button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
