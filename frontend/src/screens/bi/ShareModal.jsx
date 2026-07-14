// ShareModal.jsx — v0.8.15 分享：玻璃弹窗（镜像 AddWidgetModal chrome）。
// 流程：离屏重建报表快照节点（light T，D7）→ 多选 admin 白名单投递目标 → captureNodeToPng →
//   POST /api/bi/reports/{id}/share（base64 PNG + target_ids + caption）→ per-target 结果。
// 视觉 = 组装既有玻璃组件（Modal/ModalHeader + AddWidgetModal 同款 field/button style）；0 新视觉参数。
import { useEffect, useMemo, useRef, useState } from 'react';
import { Modal, ModalHeader, toast, getAppearance } from '../../utils.jsx';
import { buildTheme } from '../../Shared.jsx';
import { api } from '../../api.js';
import { captureNodeToPng } from './snapshot.js';
import { SnapshotDashboard } from './SnapshotDashboard.jsx';
import { SnapshotTable } from './SnapshotTable.jsx';

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(',')[1] || '');
    r.onerror = () => reject(new Error('图片读取失败'));
    r.readAsDataURL(blob);
  });
}

export function ShareModal({ T, report, activeTileId, onClose }) {
  // D7：快照恒 light 主题（IM 里浅底更清晰）；沿用用户外观的 hue/style
  const lightT = useMemo(() => buildTheme(false, getAppearance()), []);
  const snapRef = useRef(null);
  const [targets, setTargets] = useState(null);   // null = loading
  const [sel, setSel] = useState(() => new Set());
  const [caption, setCaption] = useState(report.title || '');
  const [sending, setSending] = useState(false);
  const [results, setResults] = useState(null);

  useEffect(() => {
    api.get('/api/bi/share/targets')
      .then((d) => setTargets(Array.isArray(d) ? d : []))
      .catch((e) => { toast(`投递目标加载失败：${e.message || e}`, true); setTargets([]); });
  }, []);

  const toggle = (id) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  const doShare = async () => {
    if (!sel.size) { toast('请选择至少一个投递目标', true); return; }
    if (!snapRef.current) return;
    setSending(true);
    try {
      const blob = await captureNodeToPng(snapRef.current, { background: lightT.bg });
      const image_png = await blobToBase64(blob);
      const out = await api.post(`/api/bi/reports/${report.id}/share`,
        { image_png, target_ids: [...sel], caption: caption.trim() });
      setResults(out.results || []);
      toast(out.ok_count === out.total ? `已分享到 ${out.ok_count} 个目标`
        : `分享 ${out.ok_count}/${out.total} 成功`, out.ok_count !== out.total);
    } catch (e) {
      toast(`分享失败：${e.message || e}`, true);
    } finally { setSending(false); }
  };

  const fld = { width: '100%', height: 38, padding: '0 12px', background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 8, color: T.text, fontSize: 13, fontFamily: T.sans, outline: 'none', boxSizing: 'border-box' };
  const platLabel = (p) => (p === 'tg' ? 'Telegram' : p === 'lark' ? 'Lark' : p);

  return (
    <Modal T={T} onClose={onClose} width={462}>
      <ModalHeader T={T} title="分享报表" subtitle="快照 PNG → 投递到管理员配置的 Lark / Telegram 群" onClose={onClose} />
      <div className="cb-sb" style={{ padding: 20, maxHeight: '70vh', overflowY: 'auto' }}>
        <div style={{ fontSize: 12, color: T.subtext, marginBottom: 8, fontWeight: 500 }}>投递目标</div>
        {targets === null ? (
          <div style={{ fontSize: 12.5, color: T.muted, padding: '8px 0' }}>加载中…</div>
        ) : targets.length === 0 ? (
          <div style={{ fontSize: 12.5, color: T.muted, padding: '10px 12px', border: `1px solid ${T.border}`, borderRadius: 8 }}>
            暂无投递目标 —— 管理员在「BI 设置 → 分享」里添加 Lark/Telegram 群。
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 16 }}>
            {targets.map((t) => {
              const on = sel.has(t.id);
              return (
                <label key={t.id} style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 8, cursor: 'pointer',
                  background: on ? `color-mix(in oklch, ${T.accent} 8%, transparent)` : 'transparent',
                  border: `1px solid ${on ? `color-mix(in oklch, ${T.accent} 45%, transparent)` : T.border}`,
                }}>
                  <input type="checkbox" checked={on} onChange={() => toggle(t.id)} style={{ accentColor: T.accent, width: 15, height: 15 }} />
                  <span style={{ flex: 1, fontSize: 13, color: T.text }}>{t.name}</span>
                  <span style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono, letterSpacing: '0.03em' }}>{platLabel(t.platform)}</span>
                </label>
              );
            })}
          </div>
        )}
        <div style={{ fontSize: 12, color: T.subtext, marginBottom: 5, fontWeight: 500 }}>附言（caption）</div>
        <input value={caption} onChange={(e) => setCaption(e.target.value)} maxLength={200}
          placeholder="随图发送的说明文字（默认报表名）" style={{ ...fld, marginBottom: 6 }} />
        <div style={{ fontSize: 11, color: T.muted }}>
          仪表盘整盘截图；报表 ≤50 行。图片浅色主题、发到管理员策展的群。
        </div>
        {results && (
          <div style={{ marginTop: 14, borderTop: `1px solid ${T.border}`, paddingTop: 12, display: 'flex', flexDirection: 'column', gap: 5 }}>
            {results.map((r) => (
              <div key={r.id} style={{ fontSize: 12.5, color: r.ok ? T.success : T.warn, display: 'flex', gap: 8 }}>
                <span>{r.ok ? '✓' : '✗'}</span><span style={{ color: T.text }}>{r.name}</span>
                {!r.ok && r.error && <span style={{ color: T.muted, fontSize: 11 }}>{r.error}</span>}
              </div>
            ))}
          </div>
        )}
      </div>
      <div style={{ padding: '14px 20px', borderTop: `1px solid ${T.border}`, display: 'flex', justifyContent: 'flex-end' }}>
        <button onClick={doShare} disabled={sending || !sel.size} style={{
          padding: '8px 18px', borderRadius: 8, border: 'none', background: T.accent, color: T.sendFg, fontSize: 13, fontWeight: 500,
          fontFamily: 'inherit', cursor: sending || !sel.size ? 'default' : 'pointer', opacity: sending || !sel.size ? 0.6 : 1,
          boxShadow: !sending && sel.size ? (T.glow || 'none') : 'none',
        }}>
          {sending ? '生成并发送中…' : '截图并分享'}
        </button>
      </div>
      {/* 离屏快照源节点（脱流 0 尺寸；light T；captureNodeToPng 截此） */}
      <div ref={snapRef} aria-hidden="true" style={{ position: 'fixed', left: -99999, top: 0, pointerEvents: 'none' }}>
        {report.report_type === 'dashboard'
          ? <SnapshotDashboard T={lightT} report={report} />
          : <SnapshotTable T={lightT} report={report} activeTileId={activeTileId} />}
      </div>
    </Modal>
  );
}
