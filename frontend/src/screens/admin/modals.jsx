// v0.5.3: extracted from Admin.jsx L571-773 (UserFormModal + SourceFormModal + FewShotModal)
// 3 个 dumb modal 组件 — 接收 data + onClose + onSave 回调；state 由子文件管理（R-124 无全局状态）。
// v0.5.24: 视觉重构 — Hex 偿还 4 处（白色字面 → T.sendFg）+ Checkbox svg check + R-365 Shared 0 改 sustained
// v0.5.x 视觉重构收官 PATCH
import { useState } from 'react';
import { I, pillBtn } from '../../Shared.jsx';
import { toast, Modal, ModalHeader, Input, Select, Spinner } from '../../utils.jsx';
import { api } from '../../api.js';

export function UserFormModal({ T, data, sources, onClose, onSave }) {
  const isEdit = !!data;
  const [form, setForm] = useState({
    username: data?.username || '',
    password: '',
    display_name: data?.display_name || '',
    role: data?.role || 'analyst',
    source_ids: new Set(data?.source_ids?.map(Number) || []),
  });
  const [loading, setLoading] = useState(false);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const toggleSource = (id) => {
    const next = new Set(form.source_ids);
    next.has(id) ? next.delete(id) : next.add(id);
    set('source_ids', next);
  };

  const submit = async () => {
    if (!isEdit && (!form.username.trim() || !form.password)) { toast('账号和密码必填', true); return; }
    setLoading(true);
    try {
      const source_ids = [...form.source_ids];
      if (isEdit) {
        const up = { source_ids };
        if (form.display_name) up.display_name = form.display_name;
        if (form.role) up.role = form.role;
        if (form.password) up.password = form.password;
        await api.put(`/api/admin/users/${data.id}`, up);
      } else {
        const body = { username: form.username, password: form.password, display_name: form.display_name, role: form.role };
        await api.post('/api/admin/users', body);
        const users = await api.get('/api/admin/users');
        const created = users.find(u => u.username === form.username);
        if (created && source_ids.length) await api.put(`/api/admin/users/${created.id}`, { source_ids });
      }
      toast(isEdit ? '已更新' : '已创建');
      onSave(); onClose();
    } catch (e) { toast(String(e), true); }
    finally { setLoading(false); }
  };

  return (
    <Modal T={T} onClose={onClose} width={500}>
      <ModalHeader T={T} title={isEdit ? '编辑账号' : '新建账号'} onClose={onClose}/>
      <div style={{ padding: '16px 20px', maxHeight: '70vh', overflowY: 'auto' }} className="cb-sb">
        <Input T={T} label="账号" value={form.username} onChange={v => set('username', v)} required={!isEdit} placeholder="username"/>
        <Input T={T} label={isEdit ? '新密码（留空不修改）' : '密码'} value={form.password} onChange={v => set('password', v)} type="password" required={!isEdit} placeholder="••••••••"/>
        <Input T={T} label="显示名称" value={form.display_name} onChange={v => set('display_name', v)} placeholder="张三" optional/>
        <Select T={T} label="角色" value={form.role} onChange={v => set('role', v)} options={[{ value: 'analyst', label: 'analyst — 分析师' }, { value: 'admin', label: 'admin — 管理员' }]}/>
        <div style={{ height: 1, background: T.border, margin: '12px 0' }}/>
        <div style={{ fontSize: 12, color: T.muted, marginBottom: 8 }}>数据源（可多选，查询时自动合并表结构）</div>
        {(sources || []).length === 0
          ? <div style={{ fontSize: 12, color: T.muted }}>暂无数据源，请先在「数据源」标签页创建</div>
          : <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {(sources || []).map(s => {
                const checked = form.source_ids.has(s.id);
                return (
                  <label key={s.id} onClick={() => toggleSource(s.id)} style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px',
                    borderRadius: 7, cursor: 'pointer',
                    background: checked ? T.accentSoft : T.content,
                    border: `1px solid ${checked ? T.accent : T.border}`,
                  }}>
                    {/* v0.5.24 Checkbox svg check — 替代 unicode tick + 白色 hex 字面（R-484 sustained） */}
                    <span style={{ width: 15, height: 15, borderRadius: 3, flexShrink: 0, border: `1.5px solid ${checked ? T.accent : T.border}`, background: checked ? T.accent : 'transparent', display: 'grid', placeItems: 'center' }}>
                      {checked && (
                        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke={T.sendFg} strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="20 6 9 17 4 12"/>
                        </svg>
                      )}
                    </span>
                    <span style={{ fontSize: 13, color: T.text, flex: 1 }}>{s.name}</span>
                    <span style={{ fontSize: 11, color: T.muted, fontFamily: T.mono }}>{s.db_database}</span>
                  </label>
                );
              })}
            </div>
        }
      </div>
      <div style={{ padding: '12px 20px', borderTop: `1px solid ${T.border}`, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={onClose} style={pillBtn(T)}>取消</button>
        {/* v0.5.24 R-484 Spinner color hex 偿还 — 白色字面 → T.sendFg */}
        <button onClick={submit} disabled={loading} style={pillBtn(T, true)}>
          {loading ? <Spinner size={12} color={T.sendFg}/> : '保存'}
        </button>
      </div>
    </Modal>
  );
}

export function SourceFormModal({ T, data, onClose, onSave }) {
  const isEdit = !!data;
  const [form, setForm] = useState({
    name: data?.name || '',
    description: data?.description || '',
    db_host: data?.db_host || '',
    db_port: data?.db_port || 9030,
    db_user: data?.db_user || '',
    db_password: '',
    db_database: data?.db_database || '',
    db_type: data?.db_type || 'doris',
  });
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const testConn = async () => {
    setTesting(true); setTestResult(null);
    try {
      const d = await api.post('/api/db/test', form);
      setTestResult(d);
    } catch (e) { setTestResult({ connected: false, message: String(e) }); }
    finally { setTesting(false); }
  };

  const submit = async () => {
    if (!form.name.trim() || !form.db_host.trim()) { toast('名称和主机必填', true); return; }
    setLoading(true);
    try {
      const body = { ...form, db_port: Number(form.db_port) };
      if (isEdit) await api.put(`/api/admin/datasources/${data.id}`, body);
      else await api.post('/api/admin/datasources', body);
      toast(isEdit ? '已更新' : '已添加');
      onSave(); onClose();
    } catch (e) { toast(String(e), true); }
    finally { setLoading(false); }
  };

  return (
    <Modal T={T} onClose={onClose} width={480}>
      <ModalHeader T={T} title={isEdit ? '编辑数据源' : '添加数据源'} onClose={onClose}/>
      <div style={{ padding: '16px 20px', maxHeight: '70vh', overflowY: 'auto' }} className="cb-sb">
        <Input T={T} label="名称" value={form.name} onChange={v => set('name', v)} required placeholder="trading_core"/>
        <Input T={T} label="说明" value={form.description} onChange={v => set('description', v)} optional placeholder="交易核心库"/>
        <Select T={T} label="数据库类型" value={form.db_type} onChange={v => set('db_type', v)} options={[{ value: 'doris', label: 'Apache Doris' }, { value: 'mysql', label: 'MySQL' }, { value: 'clickhouse', label: 'ClickHouse' }]}/>
        <Input T={T} label="Host" value={form.db_host} onChange={v => set('db_host', v)} required placeholder="127.0.0.1" mono/>
        <Input T={T} label="Port" value={String(form.db_port)} onChange={v => set('db_port', v)} required placeholder="9030" mono/>
        <Input T={T} label="User" value={form.db_user} onChange={v => set('db_user', v)} required placeholder="root" mono/>
        <Input T={T} label="Password" value={form.db_password} onChange={v => set('db_password', v)} type="password" placeholder={isEdit ? '留空不修改' : '••••••••'} optional={isEdit}/>
        <Input T={T} label="Database" value={form.db_database} onChange={v => set('db_database', v)} required placeholder="mydb 或 ohx_ods,ohx_dwd" mono/>
        <div style={{ fontSize: 11.5, color: T.muted, marginTop: -6 }}>多个库用英文逗号分隔，查询时可跨库使用 库名.表名</div>
        {/* R-302.5 emoji 业务豁免 sustained — ✓/✗ 是 testResult 业务状态指示器 */}
        {testResult && (
          <div style={{ padding: '8px 12px', borderRadius: 6, background: testResult.connected ? T.successSoft : T.accentSoft, color: testResult.connected ? T.success : T.accent, fontSize: 12.5, marginBottom: 12 }}>
            {testResult.connected ? '✓ ' : '✗ '}{testResult.message}
          </div>
        )}
      </div>
      <div style={{ padding: '12px 20px', borderTop: `1px solid ${T.border}`, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={testConn} disabled={testing} style={pillBtn(T)}>
          {testing ? <><Spinner size={11}/> 测试中…</> : <><I.wifi/> 测试连接</>}
        </button>
        <button onClick={onClose} style={pillBtn(T)}>取消</button>
        {/* v0.5.24 R-484 Spinner color hex 偿还 */}
        <button onClick={submit} disabled={loading} style={pillBtn(T, true)}>
          {loading ? <Spinner size={12} color={T.sendFg}/> : '保存'}
        </button>
      </div>
    </Modal>
  );
}

export function FewShotModal({ T, data, onClose, onSave }) {
  const isEdit = !!data;
  const [form, setForm] = useState({
    question: data?.question || '',
    sql: data?.sql || '',
    type: data?.type || '',
    is_active: data?.is_active ?? 1,
  });
  const [loading, setLoading] = useState(false);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!form.question.trim() || !form.sql.trim()) { toast('question / sql 必填', true); return; }
    setLoading(true);
    try {
      if (isEdit) await api.put(`/api/few-shots/${data.id}`, form);
      else await api.post('/api/few-shots', form);
      toast(isEdit ? '已更新' : '已创建');
      onSave(); onClose();
    } catch (e) { toast(String(e), true); }
    finally { setLoading(false); }
  };

  return (
    <Modal T={T} onClose={onClose} width={560}>
      <ModalHeader T={T} title={isEdit ? '编辑 Few-shot' : '新建 Few-shot'} onClose={onClose}/>
      <div style={{ padding: '16px 20px', maxHeight: '70vh', overflowY: 'auto' }} className="cb-sb">
        <Input T={T} label="问题" value={form.question} onChange={v => set('question', v)} required placeholder="昨天的订单总数"/>
        <div style={{ fontSize: 12, color: T.subtext, marginBottom: 4 }}>SQL</div>
        <textarea value={form.sql} onChange={e => set('sql', e.target.value)} placeholder="SELECT ..."
          style={{ width: '100%', minHeight: 120, resize: 'vertical', background: T.inputBg, color: T.text,
                   fontFamily: T.mono, fontSize: 12, border: `1px solid ${T.inputBorder}`, borderRadius: 7,
                   padding: '8px 10px', outline: 'none', boxSizing: 'border-box', marginBottom: 12 }}/>
        <Input T={T} label="类型 type" value={form.type} onChange={v => set('type', v)} optional
               placeholder="aggregation · rank · join · …"/>
        <Select T={T} label="状态" value={String(form.is_active)} onChange={v => set('is_active', Number(v))}
                options={[{ value: '1', label: '启用' }, { value: '0', label: '禁用' }]}/>
      </div>
      <div style={{ padding: '12px 20px', borderTop: `1px solid ${T.border}`, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={onClose} style={pillBtn(T)}>取消</button>
        {/* v0.5.24 R-484 Spinner color hex 偿还 */}
        <button onClick={submit} disabled={loading} style={pillBtn(T, true)}>
          {loading ? <Spinner size={12} color={T.sendFg}/> : '保存'}
        </button>
      </div>
    </Modal>
  );
}
