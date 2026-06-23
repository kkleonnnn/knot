import { useState, useEffect } from 'react';
import { TagChip } from '../../Shared.jsx';
import { toast, Spinner } from '../../utils.jsx';
import { api } from '../../api.js';

// v0.7.5 — LogicForm 版本历史 + diff（read-only）。版本链（原始 is_corrected=0 + 历次修正）时间线 +
// 选 2 版本 diff。⭐ 保真度（R-SL-56）：LogicForm（存的 canonical_json）= 忠实历史源（diff 主体）；
// SQL = 当前重编译渲染（分层：hit「当前重编译」/ near-miss 显存 reason / hit-now-fails「当前编译失败」）。

const _LF_FIELDS = ['metrics', 'dimensions', 'filters', 'time', 'order_by', 'limit'];

function _parse(j) { try { return JSON.parse(j || '{}'); } catch { return {}; } }
function _fmt(v) { return v === undefined ? '—' : (typeof v === 'object' ? JSON.stringify(v) : String(v)); }
function _lbl(T) { return { fontSize: 10.5, color: T.muted, fontFamily: T.mono, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 3 }; }
function _pre(T) { return { margin: 0, padding: 8, background: T.codeBg, borderRadius: 6, border: `1px solid ${T.border}`, fontSize: 11, fontFamily: T.mono, color: T.codeText, overflow: 'auto', maxHeight: 160, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }; }

function _kindTag(T, v) {
  if (v.kind === 'near_miss') return <TagChip T={T} kind="warn">回退</TagChip>;
  if (v.kind === 'hit_recompile_failed') return <TagChip T={T} kind="warn">当前编译失败</TagChip>;
  return <TagChip T={T} kind="success">命中</TagChip>;
}

export function LogicFormHistory({ T, auditId }) {
  const [versions, setVersions] = useState(null);   // null = loading
  const [sel, setSel] = useState([]);               // 选中 diff 的 version index（≤2）

  // 父以 key={auditId} 强制 remount → fresh useState（loading + 清选择）；effect 仅异步 fetch（避 set-state-in-effect）
  useEffect(() => {
    api.get(`/api/admin/logicform-audit/${auditId}/history`)
       .then(d => setVersions(Array.isArray(d) ? d : []))
       .catch(e => { toast(`版本历史加载失败: ${e.message}`, true); setVersions([]); });
  }, [auditId]);

  function toggle(i) {
    setSel(s => s.includes(i) ? s.filter(x => x !== i) : (s.length >= 2 ? [s[1], i] : [...s, i]));
  }

  if (versions === null) return <div style={{ padding: 16, textAlign: 'center' }}><Spinner color={T.accent}/></div>;
  if (!versions.length) return <div style={{ fontSize: 12, color: T.muted }}>无版本记录（仅语义命中/near-miss/修正有侧表行）</div>;

  const [a, b] = sel.map(i => _parse(versions[i] && versions[i].logicform_json));
  const showDiff = sel.length === 2;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {versions.map((v, i) => (
          <div key={v.audit_id} onClick={() => toggle(i)} style={{ display: 'flex', alignItems: 'center', gap: 8,
            padding: '6px 10px', borderRadius: 6, cursor: 'pointer',
            border: `1px solid ${sel.includes(i) ? T.accent : T.border}`,
            background: sel.includes(i) ? `color-mix(in oklch, ${T.accent} 8%, transparent)` : 'transparent' }}>
            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.subtext }}>{v.is_corrected ? '修正' : '原始'}</span>
            {_kindTag(T, v)}
            <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.muted, marginLeft: 'auto' }}>{v.created_at}</span>
          </div>
        ))}
      </div>
      <div style={{ fontSize: 11, color: T.muted }}>点选 2 版本看 diff —— LogicForm = 忠实历史；SQL = 当前重编译</div>

      {showDiff && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div>
            <div style={_lbl(T)}>LogicForm diff（忠实历史源）</div>
            {_LF_FIELDS.map(f => {
              const va = _fmt(a && a[f]), vb = _fmt(b && b[f]);
              const changed = va !== vb;
              return (
                <div key={f} style={{ display: 'flex', gap: 8, fontSize: 12, padding: '2px 0' }}>
                  <span style={{ width: 84, fontFamily: T.mono, fontSize: 11, color: T.subtext, flexShrink: 0 }}>{f}</span>
                  <span style={{ flex: 1, minWidth: 0, color: changed ? T.warn : T.muted, textDecoration: changed ? 'line-through' : 'none', wordBreak: 'break-word' }}>{va}</span>
                  <span style={{ color: T.muted, flexShrink: 0 }}>→</span>
                  <span style={{ flex: 1, minWidth: 0, color: changed ? T.success : T.muted, fontWeight: changed ? 500 : 400, wordBreak: 'break-word' }}>{vb}</span>
                </div>
              );
            })}
          </div>
          {sel.map(i => {
            const v = versions[i];
            return (
              <div key={v.audit_id}>
                <div style={_lbl(T)}>{v.is_corrected ? '修正' : '原始'} SQL（当前重编译，非历史实跑）</div>
                {v.kind === 'hit' ? <pre style={_pre(T)}>{v.sql}</pre> : (
                  <div style={{ fontSize: 12, color: T.warn }}>
                    {v.kind === 'near_miss' ? `回退原因（历史 near-miss）: ${v.reason}` : `当前编译失败（口径可能已变更）: ${v.reason}`}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
