import { useState, useEffect } from 'react';
import { TagChip, pillBtn } from '../Shared.jsx';
import { toast, Spinner, Modal, ModalHeader } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { api } from '../api.js';

// v0.7.3 — LogicForm 审计屏（F3 read-only）：语义路径查询 + AI 如何理解（LogicForm）+ 编译 SQL +
// 命中/near-miss。镜像 AdminQueryHistory（CSS Grid list + drawer）。LogicForm/SQL 仅 admin 面（脱敏链）。

function _parseLF(json) {
  try { return JSON.parse(json || '{}'); } catch { return {}; }
}

function _lbl(T) {
  return { fontSize: 11, color: T.muted, marginBottom: 4, fontFamily: T.mono, textTransform: 'uppercase', letterSpacing: '0.06em' };
}
function _pre(T) {
  return { margin: 0, padding: 10, background: T.codeBg, borderRadius: 6, border: `1px solid ${T.border}`,
           fontSize: 11.5, fontFamily: T.mono, color: T.codeText, overflow: 'auto', maxHeight: 240,
           whiteSpace: 'pre-wrap', wordBreak: 'break-word' };
}

function LFRow({ T, k, v, kind }) {
  return (
    <div>
      <div style={_lbl(T)}>{k}</div>
      <div style={{ fontSize: 13, color: kind === 'warn' ? T.warn : T.text, lineHeight: 1.55, wordBreak: 'break-word' }}>{v}</div>
    </div>
  );
}

export function AdminLogicFormScreen({ T, user, onToggleTheme, onNavigate, onLogout }) {
  const [rows, setRows] = useState(null);   // null = loading
  const [openItem, setOpenItem] = useState(null);
  const [editLF, setEditLF] = useState('');         // F4 修正：可编辑 LogicForm
  const [correctRes, setCorrectRes] = useState(null);
  const [correcting, setCorrecting] = useState(false);
  const [rerunRes, setRerunRes] = useState(null);   // F4 re-run：真执行结果（临时，不写会话）
  const [rerunning, setRerunning] = useState(false);

  useEffect(() => {
    api.get('/api/admin/logicform-audit')
       .then(d => setRows(Array.isArray(d) ? d : []))
       .catch(e => { toast(`加载失败: ${e.message}`, true); setRows([]); });
  }, []);

  function openRow(r) {
    setOpenItem(r);
    setEditLF(JSON.stringify(_parseLF(r.logicform_json), null, 2));   // 预填可编辑 LogicForm
    setCorrectRes(null);
    setRerunRes(null);
  }

  async function handleRerun(auditId) {
    // F4 真执行（R-SL-43/44）：重编译 + 原用户 engine + execute_query；rows 临时返回不写会话
    setRerunning(true);
    try {
      const res = await api.post(`/api/admin/logicform-audit/${auditId}/rerun`);
      setRerunRes(res);
      toast(res.ok ? `执行完成（${res.row_count ?? 0} 行）` : '执行失败（见下）', !res.ok);
    } catch (e) {
      toast(`执行失败: ${e.message}`, true);
    } finally {
      setRerunning(false);
    }
  }

  async function handleCorrect() {
    let parsed;
    try { parsed = JSON.parse(editLF); } catch { toast('LogicForm JSON 格式错误', true); return; }
    setCorrecting(true);
    try {
      const res = await api.post(`/api/admin/logicform-audit/${openItem.id}/correct`, { logicform: parsed });
      setCorrectRes(res);                            // ok:true → 修正 SQL；ok:false → compile_error
      toast(res.ok ? '重编译成功（确定性 SQL）' : '编译失败（见下）', !res.ok);
    } catch (e) {
      toast(`修正失败: ${e.message}`, true);
    } finally {
      setCorrecting(false);
    }
  }

  const insetBg = `color-mix(in oklch, ${T.accent} 8%, transparent)`;
  const gridCols = '150px 1fr 100px 80px';

  return (
    <AppShell T={T} user={user} active="admin-logicform"
              onToggleTheme={onToggleTheme} onNavigate={onNavigate} onLogout={onLogout}
              topbarTitle="LogicForm 审计">
      <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}>

        {/* 说明 — brandSoft inset borderLeft 25%（视觉铁律）*/}
        <div style={{ padding: '10px 14px', background: insetBg,
          borderLeft: `2px solid color-mix(in oklch, ${T.accent} 25%, transparent)`,
          fontSize: 12, color: T.subtext, lineHeight: 1.55 }}>
          语义层确定性路径查询审计 —— AI 把问题理解成的 LogicForm + 编译 SQL。
          <b style={{ color: T.text }}>命中</b> = 走确定性编译；
          <b style={{ color: T.warn }}>回退</b> = 解析出 LogicForm 但编译歧义，已安全回退 LLM（near-miss 诊断）。
        </div>

        {rows === null ? (
          <div style={{ padding: 60, textAlign: 'center' }}><Spinner color={T.accent}/></div>
        ) : rows.length === 0 ? (
          <div style={{ padding: 60, textAlign: 'center', color: T.muted, fontSize: 13 }}>
            暂无语义路径查询（KNOT_SEMANTIC_LAYER off 或无命中/near-miss）
          </div>
        ) : (
          <div style={{ background: T.content, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: gridCols, padding: '10px 14px',
              borderBottom: `1px solid ${T.border}`, background: insetBg, fontSize: 11, color: T.subtext,
              fontFamily: T.mono, textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 500 }}>
              <div>时间</div><div>问题</div><div>路径</div><div>Catalog</div>
            </div>
            {rows.map(r => (
              <div key={r.id} onClick={() => openRow(r)} style={{ display: 'grid', gridTemplateColumns: gridCols,
                alignItems: 'center', padding: '10px 14px', borderBottom: `1px solid ${T.borderSoft}`,
                fontSize: 12.5, cursor: 'pointer' }}>
                <div style={{ color: T.muted, fontFamily: T.mono, fontSize: 11, minWidth: 0, overflow: 'hidden' }}>{r.created_at}</div>
                <div style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: T.text }}>
                  {r.question || `#msg ${r.message_id}`}
                </div>
                <div>{r.hit ? <TagChip T={T} kind="success">命中</TagChip> : <TagChip T={T} kind="warn">回退</TagChip>}</div>
                <div style={{ fontFamily: T.mono, fontSize: 11, color: T.subtext }}>#{r.catalog_id}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {openItem && (
        <Modal T={T} onClose={() => setOpenItem(null)} width={680}>
          <ModalHeader T={T} title={openItem.hit ? '命中 · 确定性编译' : '回退 · near-miss'}
                       subtitle={openItem.created_at} onClose={() => setOpenItem(null)}/>
          <div style={{ padding: '16px 20px', maxHeight: '70vh', overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <LFRow T={T} k="问题" v={openItem.question || '—'}/>
            {/* F4 修正：可编辑 LogicForm → 重编译（原 catalog R-SL-40）→ 看修正 SQL */}
            <div>
              <div style={_lbl(T)}>LogicForm（AI 理解 · 可改 → 重编译）</div>
              <textarea value={editLF} onChange={e => setEditLF(e.target.value)} spellCheck={false}
                        style={{ ..._pre(T), width: '100%', minHeight: 120, resize: 'vertical', boxSizing: 'border-box' }}/>
              <div style={{ display: 'flex', gap: 8, marginTop: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <button onClick={handleCorrect} disabled={correcting} style={{ ...pillBtn(T, true), padding: '6px 14px' }}>
                  {correcting ? <><Spinner size={11} color={T.sendFg}/> 重编译中…</> : '重编译（确定性）'}
                </button>
                <span style={{ fontSize: 11, color: T.muted }}>改 dimension/filter 等 → 看修正 SQL（比改 SQL 友好）</span>
              </div>
              {correctRes && correctRes.ok ? (
                <div style={{ marginTop: 10 }}>
                  <div style={_lbl(T)}>修正后 SQL（确定性 · 已落审计血缘 is_corrected）</div>
                  <pre style={_pre(T)}>{correctRes.sql}</pre>
                  {/* F4 真执行：原用户 engine + execute_query（DQL-only）→ rows 临时（不写会话）*/}
                  <button onClick={() => handleRerun(correctRes.audit_id)} disabled={rerunning}
                          style={{ ...pillBtn(T, false), padding: '6px 14px', marginTop: 8 }}>
                    {rerunning ? <><Spinner size={11} color={T.accent}/> 执行中…</> : '执行看数据（真实执行 · 验证修正）'}
                  </button>
                </div>
              ) : correctRes && !correctRes.ok ? (
                <div style={{ marginTop: 8, fontSize: 12, color: T.warn }}>编译失败：{correctRes.compile_error}</div>
              ) : null}
              {rerunRes && rerunRes.ok && !rerunRes.db_error ? (
                <div style={{ marginTop: 10 }}>
                  <div style={_lbl(T)}>执行结果（{rerunRes.row_count} 行 · 临时 · 不写用户会话）</div>
                  {rerunRes.rows && rerunRes.rows.length ? (
                    <div style={{ overflow: 'auto', maxHeight: 240, border: `1px solid ${T.border}`, borderRadius: 6 }}>
                      <table style={{ borderCollapse: 'collapse', fontSize: 12, width: '100%' }}>
                        <thead><tr>{Object.keys(rerunRes.rows[0]).map(k => (
                          <th key={k} style={{ padding: '6px 10px', textAlign: 'left', background: insetBg, color: T.subtext, fontFamily: T.mono, fontSize: 11, whiteSpace: 'nowrap' }}>{k}</th>
                        ))}</tr></thead>
                        <tbody>{rerunRes.rows.map((row, i) => (
                          <tr key={i}>{Object.values(row).map((v, j) => (
                            <td key={j} style={{ padding: '6px 10px', borderTop: `1px solid ${T.borderSoft}`, color: T.text, whiteSpace: 'nowrap' }}>{String(v)}</td>
                          ))}</tr>
                        ))}</tbody>
                      </table>
                    </div>
                  ) : <div style={{ fontSize: 12, color: T.muted }}>无数据</div>}
                </div>
              ) : rerunRes && (rerunRes.db_error || !rerunRes.ok) ? (
                <div style={{ marginTop: 8, fontSize: 12, color: T.warn }}>{rerunRes.db_error || rerunRes.error || rerunRes.compile_error}</div>
              ) : null}
            </div>
            {openItem.hit && openItem.sql ? (
              <div>
                <div style={_lbl(T)}>原编译 SQL（确定性）</div>
                <pre style={_pre(T)}>{openItem.sql}</pre>
              </div>
            ) : null}
            {!openItem.hit ? <LFRow T={T} k="回退原因（near-miss）" v={openItem.compile_error_reason || '—'} kind="warn"/> : null}
            <LFRow T={T} k="Catalog / message" v={`catalog #${openItem.catalog_id} · message #${openItem.message_id}`}/>
            {openItem.is_corrected ? <LFRow T={T} k="修正来源" v={`原 message #${openItem.parent_message_id}`}/> : null}
          </div>
        </Modal>
      )}
    </AppShell>
  );
}
