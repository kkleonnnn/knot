// ScheduleModal.jsx — v0.8.17 (②c) 定时刷新配置弹窗（玻璃；镜像 ShareModal chrome）。
// per-report 定时刷新（节奏 + 触发时刻）→ PUT /api/bi/reports/{id}/schedule；回显 next_run/last_fire +
// fire 历史台账（避 monitors 孤儿 triggers 教训）。视觉 = 组装既有 Modal/Select/字段/按钮；0 新视觉参数。
import { useEffect, useState } from 'react';
import { Modal, ModalHeader, Select, toast } from '../../utils.jsx';
import { api } from '../../api.js';

const CADENCE_OPTS = [
  { value: 'daily', label: '每天' },
  { value: 'hourly', label: '每小时' },
  { value: 'every_n_hours', label: '每 N 小时' },
];
const STATUS_LABEL = { ok: '成功', error: '出错', no_engine: '无引擎', skipped: '跳过' };

export function ScheduleModal({ T, report, onClose }) {
  const [enabled, setEnabled] = useState(false);
  const [cadence, setCadence] = useState('daily');
  const [runAt, setRunAt] = useState('08:00');
  const [intervalHours, setIntervalHours] = useState('6');
  const [sched, setSched] = useState(undefined);   // undefined=loading · null=无 · obj=已配
  const [fires, setFires] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get(`/api/bi/reports/${report.id}/schedule`).then((s) => {
      setSched(s || null);
      if (s) {
        setEnabled(!!s.enabled);
        setCadence(s.cadence || 'daily');
        if (s.run_at_hhmm) setRunAt(s.run_at_hhmm);
        if (s.interval_hours) setIntervalHours(String(s.interval_hours));
      }
    }).catch(() => setSched(null));
    api.get(`/api/bi/reports/${report.id}/schedule/fires`)
      .then((f) => setFires(Array.isArray(f) ? f : [])).catch(() => {});
  }, [report.id]);

  const save = async () => {
    setSaving(true);
    try {
      const body = { enabled, cadence };
      if (cadence === 'daily') body.run_at_hhmm = runAt.trim();
      if (cadence === 'every_n_hours') body.interval_hours = parseInt(intervalHours, 10) || 1;
      setSched(await api.put(`/api/bi/reports/${report.id}/schedule`, body));
      toast(enabled ? '定时已保存' : '定时已停用');
    } catch (e) {
      toast(`保存失败：${e.message || e}`, true);
    } finally { setSaving(false); }
  };

  const fld = { width: '100%', height: 38, padding: '0 12px', background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 8, color: T.text, fontSize: 13, fontFamily: T.sans, outline: 'none', boxSizing: 'border-box' };
  const ro = { fontSize: 12, color: T.muted, fontFamily: T.mono };

  return (
    <Modal T={T} onClose={onClose} width={462}>
      <ModalHeader T={T} title="定时刷新" subtitle="按节奏自动重跑报表冻结 SQL，保持数据新鲜" onClose={onClose} />
      <div className="cb-sb" style={{ padding: 20, maxHeight: '70vh', overflowY: 'auto' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, cursor: 'pointer' }}>
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)}
            style={{ accentColor: T.accent, width: 15, height: 15 }} />
          <span style={{ fontSize: 13, color: T.text }}>启用定时刷新</span>
        </label>
        <Select T={T} label="节奏" value={cadence} onChange={setCadence} options={CADENCE_OPTS} />
        {cadence === 'daily' && (
          <>
            <div style={{ fontSize: 12, color: T.subtext, marginBottom: 5, fontWeight: 500 }}>触发时刻（Asia/Shanghai）</div>
            <input value={runAt} onChange={(e) => setRunAt(e.target.value)} placeholder="08:00" style={{ ...fld, marginBottom: 12 }} />
          </>
        )}
        {cadence === 'every_n_hours' && (
          <>
            <div style={{ fontSize: 12, color: T.subtext, marginBottom: 5, fontWeight: 500 }}>间隔（小时）</div>
            <input value={intervalHours} onChange={(e) => setIntervalHours(e.target.value.replace(/[^0-9]/g, ''))}
              placeholder="6" style={{ ...fld, marginBottom: 12 }} />
          </>
        )}
        <div style={{ fontSize: 11, color: T.muted, marginBottom: 12 }}>
          仅重跑冻结 SQL 刷新快照（不推送、不调 AI）。建议每日在上游数据更新后（如 08:00）触发。
        </div>
        {sched && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, borderTop: `1px solid ${T.border}`, paddingTop: 10 }}>
            <div style={ro}>下次触发：{sched.next_run_at || '—'}</div>
            <div style={ro}>上次触发：{sched.last_fired_at || '—'}</div>
          </div>
        )}
        {fires.length > 0 && (
          <div style={{ marginTop: 12, borderTop: `1px solid ${T.border}`, paddingTop: 10 }}>
            <div style={{ fontSize: 12, color: T.subtext, marginBottom: 6, fontWeight: 500 }}>最近触发</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {fires.slice(0, 8).map((f) => (
                <div key={f.id} style={{ fontSize: 11.5, color: f.status === 'ok' ? T.success : T.warn, display: 'flex', gap: 8 }}>
                  <span style={{ fontFamily: T.mono, color: T.muted }}>{f.fired_at}</span>
                  <span>{STATUS_LABEL[f.status] || f.status}</span>
                  {f.error && <span style={{ color: T.muted }}>{f.error}</span>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      <div style={{ padding: '14px 20px', borderTop: `1px solid ${T.border}`, display: 'flex', justifyContent: 'flex-end' }}>
        <button onClick={save} disabled={saving} style={{
          padding: '8px 18px', borderRadius: 8, border: 'none', background: T.accent, color: T.sendFg, fontSize: 13, fontWeight: 500,
          fontFamily: 'inherit', cursor: saving ? 'default' : 'pointer', opacity: saving ? 0.6 : 1, boxShadow: T.glow || 'none',
        }}>
          {saving ? '保存中…' : '保存'}
        </button>
      </div>
    </Modal>
  );
}
