// tab_bi.jsx — v0.8.12 C1 BI 设置专属 tab（目录管理 / 目录权限 / da-asst）。
// 从 BI 齿轮进设置时显示（Shell backMode==='bi' 过滤 nav 只留 全局项 + 这 3 项）。自包含 fetch，保 Admin.jsx 精简。
// C1：容器 + 目录只读列表 + 权限/da-asst 说明位；C2 补目录增删改排、C4 补权限矩阵、C5 补 da-asst key。
import { useState, useEffect } from 'react';
import { api } from '../../api.js';

function Panel({ T, title, desc, children }) {
  return (
    <div style={{ maxWidth: 760 }}>
      <h2 style={{ fontSize: 16, fontWeight: 600, color: T.text, margin: '0 0 4px' }}>{title}</h2>
      {desc && <p style={{ fontSize: 12.5, color: T.subtext, margin: '0 0 18px', lineHeight: 1.6 }}>{desc}</p>}
      {children}
    </div>
  );
}

const soon = (T, txt) => <p style={{ fontSize: 12, color: T.muted, marginTop: 14 }}>{txt}</p>;

export function TabBI({ T, tab }) {
  const [folders, setFolders] = useState([]);
  useEffect(() => {
    if (tab === 'bi-directory') api.get('/api/bi/folders').then((f) => setFolders(f || [])).catch(() => {});
  }, [tab]);

  if (tab === 'bi-directory') {
    return (
      <Panel T={T} title="报表目录管理" desc="BI 报表目录的新建 / 重命名 / 删除 / 排序。">
        {folders.length === 0
          ? <div style={{ fontSize: 13, color: T.muted }}>暂无目录。</div>
          : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {folders.map((f) => (
                <div key={f.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', border: `1px solid ${T.border}`, borderRadius: 8 }}>
                  <span style={{ fontSize: 13, color: T.text }}>{f.name}</span>
                  {f.parent_id != null && <span style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono }}>子目录</span>}
                </div>
              ))}
            </div>
          )}
        {soon(T, '（重命名 / 删除 / 排序编辑：C2）')}
      </Panel>
    );
  }
  if (tab === 'bi-permissions') {
    return (
      <Panel T={T} title="目录访问权限" desc="按角色 × 目录（未分组逐报表）授予 定时 / 编辑 / 导出 / 分享 权限；admin 全权。">
        {soon(T, '权限矩阵编辑：C4（后端 RBAC 已就绪）。')}
      </Panel>
    );
  }
  return (
    <Panel T={T} title="da-asst 数据分析助手" desc="BI 报表解读的模型驱动。留空则复用平台 OpenRouter key + 默认模型。">
      {soon(T, '可选 API key / 模型设置：C5。')}
    </Panel>
  );
}
