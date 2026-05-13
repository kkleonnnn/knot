// v0.5.42 — AdminBudgets 重写：demo budget.jsx 单 global config 模式
// 替代 v0.4.3 multi-scope CRUD UI（后端 multi-scope endpoints 保留向后兼容，但 UI 不暴露）
// 5 字段 app_settings KV：月度 token 上限 / 单次对话上限 / 告警阈值 / 默认模型 / 限流策略
import { useState, useEffect } from 'react';
import { toast, Spinner } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { pillBtn } from '../Shared.jsx';
import { api } from '../api.js';

// demo budget.jsx L34-43 Row helper byte-equal
function Row({ T, label, hint, children, last }) {
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '180px 1fr', gap: 24, alignItems: 'flex-start',
      padding: '14px 0',
      borderBottom: last ? 'none' : `1px solid ${T.border}`,
    }}>
      <div>
        <div style={{ fontSize: 13, fontWeight: 500, color: T.text }}>{label}</div>
        {hint && <div style={{ fontSize: 11, color: T.muted, marginTop: 4, lineHeight: 1.4 }}>{hint}</div>}
      </div>
      <div>{children}</div>
    </div>
  );
}

// 输入框 style — demo L45-50 byte-equal
const inpStyle = (T) => ({
  height: 34, padding: '0 12px', fontSize: 13,
  background: T.inputBg, color: T.text,
  border: `1px solid ${T.inputBorder}`, borderRadius: 8,
  fontFamily: T.mono, outline: 'none',
});

// stat label / value 复用风格
const statLabelStyle = (T) => ({ fontSize: 11, color: T.muted, fontFamily: T.mono, letterSpacing: '0.06em', textTransform: 'uppercase' });

export function AdminBudgetsScreen({ T, user, onToggleTheme, onNavigate, onLogout }) {
  // v0.5.42 — 5 字段单 form state + Hero stats
  const [cfg, setCfg] = useState(null);  // { monthly_token_cap, per_conv_token_cap, warn_pct, default_model, rate_limit_per_min }
  const [saving, setSaving] = useState(false);
  const [bstats, setBstats] = useState(null);  // { tokens_used, cost_usd, usage_pct, cap }
  const [models, setModels] = useState([]);    // 可选模型列表

  useEffect(() => {
    api.get('/api/admin/budget-config').then(setCfg).catch(e => toast(`配置加载失败: ${e.message}`, true));
    api.get('/api/admin/budgets-stats').then(setBstats).catch(() => {});
    api.get('/api/admin/models').then(d => setModels(Array.isArray(d) ? d : [])).catch(() => {});
  }, []);

  async function handleSave() {
    if (!cfg) return;
    setSaving(true);
    try {
      await api.put('/api/admin/budget-config', cfg);
      toast('配置已保存');
      // 重新拉 stats 以刷新 cap / usage_pct
      api.get('/api/admin/budgets-stats').then(setBstats).catch(() => {});
    } catch (e) {
      toast(`保存失败: ${e.message}`, true);
    } finally {
      setSaving(false);
    }
  }

  function handleReset() {
    if (!confirm('恢复默认配置？当前未保存改动将丢失。')) return;
    setCfg({
      monthly_token_cap: 500000,
      per_conv_token_cap: 40000,
      warn_pct: 80,
      default_model: 'claude-haiku-4-5',
      rate_limit_per_min: 20,
    });
  }

  // 结算日 = 下月 1 号 MM-DD（demo 06-01 byte-equal 结构）
  const billingDay = (() => {
    const d = new Date(); d.setMonth(d.getMonth() + 1); d.setDate(1);
    return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  })();

  return (
    <AppShell T={T} user={user} active="admin-budgets" sidebarContent={null}
              topbarTitle="预算配置" onToggleTheme={onToggleTheme}
              onNavigate={onNavigate} onLogout={onLogout}>
      <div style={{ padding: '20px 28px 24px', overflowY: 'auto', flex: 1 }} className="cb-sb">
        <div style={{ maxWidth: 960, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Hero usage card — demo budget.jsx L57-87 byte-equal */}
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: '20px 24px' }}>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 32, marginBottom: 14, flexWrap: 'wrap' }}>
              <div style={{ minWidth: 0 }}>
                <div style={statLabelStyle(T)}>本月已用 token</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 4 }}>
                  <span style={{ fontSize: 36, fontWeight: 700, letterSpacing: '-0.02em', fontFamily: T.sans, lineHeight: 1, color: T.text }}>
                    {bstats ? bstats.tokens_used.toLocaleString() : '—'}
                  </span>
                  <span style={{ fontSize: 14, color: T.muted }}>
                    {bstats && bstats.cap ? `/ ${bstats.cap.toLocaleString()}` : '/ —'}
                  </span>
                  {bstats && bstats.usage_pct !== null && (
                    <span style={{ padding: '2px 8px', borderRadius: 4, background: `color-mix(in oklch, ${T.accent} 12%, transparent)`, color: T.accent, fontSize: 11, fontWeight: 500, fontFamily: T.mono, textTransform: 'uppercase', letterSpacing: '0.02em' }}>
                      {bstats.usage_pct}%
                    </span>
                  )}
                </div>
              </div>
              <div style={{ flex: 1, borderLeft: `1px solid ${T.border}`, paddingLeft: 24, minWidth: 0 }}>
                <div style={statLabelStyle(T)}>预计花费</div>
                <div style={{ fontSize: 24, fontWeight: 600, fontFamily: T.sans, marginTop: 4, color: T.text }}>
                  {bstats ? `$ ${bstats.cost_usd.toFixed(4)}` : '—'}
                </div>
              </div>
              <div style={{ borderLeft: `1px solid ${T.border}`, paddingLeft: 24, minWidth: 0 }}>
                <div style={statLabelStyle(T)}>结算日</div>
                <div style={{ fontSize: 24, fontWeight: 600, fontFamily: T.mono, marginTop: 4, color: T.text }}>{billingDay}</div>
              </div>
            </div>
            {/* progress bar — width from usage_pct（demo L78-86 byte-equal）*/}
            <div style={{ height: 8, background: T.bg, border: `1px solid ${T.border}`, borderRadius: 99, overflow: 'hidden' }}>
              <div style={{
                width: bstats && bstats.usage_pct !== null ? `${Math.min(100, bstats.usage_pct)}%` : '0%',
                height: '100%',
                background: T.accent,
                transition: 'width 0.3s ease-in-out',
                opacity: bstats && bstats.usage_pct !== null ? 1 : 0.5,
              }}/>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: T.muted, marginTop: 8, fontFamily: T.mono }}>
              <span>0</span>
              <span>{bstats && bstats.cap ? Math.round(bstats.cap * 0.5).toLocaleString() : '50%'}</span>
              <span>{bstats && bstats.cap ? bstats.cap.toLocaleString() : '100%'}</span>
            </div>
          </div>

          {/* config form — demo L89-126 byte-equal 5 字段 Row */}
          {!cfg ? (
            <div style={{ textAlign: 'center', padding: 32 }}><Spinner size={24} color={T.accent}/></div>
          ) : (
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: '4px 24px 20px' }}>
              <Row T={T} label="月度 token 上限" hint="单组织全局上限，超出后所有调用降级">
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input type="number" style={{ ...inpStyle(T), width: 200 }}
                         value={cfg.monthly_token_cap}
                         onChange={e => setCfg({ ...cfg, monthly_token_cap: parseInt(e.target.value) || 0 })}/>
                  <span style={{ fontSize: 12, color: T.muted }}>tokens / 月</span>
                </div>
              </Row>
              <Row T={T} label="单次对话上限" hint="一次 conversation 内累计 token，超出后阻断追问">
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input type="number" style={{ ...inpStyle(T), width: 200 }}
                         value={cfg.per_conv_token_cap}
                         onChange={e => setCfg({ ...cfg, per_conv_token_cap: parseInt(e.target.value) || 0 })}/>
                  <span style={{ fontSize: 12, color: T.muted }}>tokens</span>
                </div>
              </Row>
              <Row T={T} label="告警阈值" hint="超过该百分比时，在用户首页顶部显示提醒">
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input type="number" min="0" max="100" style={{ ...inpStyle(T), width: 100 }}
                         value={cfg.warn_pct}
                         onChange={e => setCfg({ ...cfg, warn_pct: parseInt(e.target.value) || 0 })}/>
                  <span style={{ fontSize: 12, color: T.muted }}>%</span>
                </div>
              </Row>
              <Row T={T} label="默认模型" hint="新对话默认走该模型，可在 API & 模型 页配置">
                <select value={cfg.default_model}
                        onChange={e => setCfg({ ...cfg, default_model: e.target.value })}
                        style={{ ...inpStyle(T), width: 280, fontFamily: T.sans, cursor: 'pointer' }}>
                  <option value={cfg.default_model}>{cfg.default_model}</option>
                  {models.filter(m => m.enabled !== false && m.model_id !== cfg.default_model).map(m => (
                    <option key={m.model_id} value={m.model_id}>{m.name} · {m.provider}</option>
                  ))}
                </select>
              </Row>
              <Row T={T} label="限流策略" hint="单用户每分钟最多请求次数，防止 SQL planner 死循环" last>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input type="number" min="1" style={{ ...inpStyle(T), width: 100 }}
                         value={cfg.rate_limit_per_min}
                         onChange={e => setCfg({ ...cfg, rate_limit_per_min: parseInt(e.target.value) || 0 })}/>
                  <span style={{ fontSize: 12, color: T.muted }}>req / min · 用户</span>
                </div>
              </Row>
              <div style={{ display: 'flex', gap: 8, marginTop: 18 }}>
                <button onClick={handleSave} disabled={saving}
                        style={{ ...pillBtn(T, true), padding: '8px 16px' }}>
                  {saving ? <><Spinner size={11} color={T.sendFg}/> 保存中…</> : '✓ 保存配置'}
                </button>
                <button onClick={handleReset} style={{ ...pillBtn(T), padding: '8px 16px' }}>重置</button>
              </div>
            </div>
          )}

          {/* Rules note — demo L128-140 byte-equal 2 条 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4 }}>
            {[
              { tag: 'R-16 优先级', body: '单次对话上限 ≤ 月度上限。当两者冲突时，以更小者为准' },
              { tag: 'R-23 实时',   body: 'budget.update 写入后，新建对话立即生效；已开启对话保留旧上限至结束' },
            ].map((n, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '10px 14px',
                borderLeft: `2px solid color-mix(in oklch, ${T.accent} 25%, transparent)`, fontSize: 12, color: T.subtext, lineHeight: 1.55 }}>
                <span style={{
                  padding: '2px 8px', borderRadius: 4,
                  background: `color-mix(in oklch, ${T.accent} 12%, transparent)`,
                  color: T.accent,
                  fontSize: 11, fontWeight: 500, fontFamily: T.mono,
                  textTransform: 'uppercase', letterSpacing: '0.02em',
                  flexShrink: 0,
                }}>{n.tag}</span>
                <span>{n.body}</span>
              </div>
            ))}
          </div>

        </div>
      </div>
    </AppShell>
  );
}
