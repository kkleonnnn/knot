// v0.6.0.2 F5 — ErrorBanner 子组件抽出（v0.4.4 R-28 banner 优先级 sustained）
// v0.5.13 R-302.5 emoji 业务豁免 7 类 kind sustained — emoji 字面 byte-equal 保留
// getErrorKindMeta helper 集中迁移到本文件
export const ERROR_KIND_ICONS = {
  budget_exceeded: '🛑', config_missing: '🔧', llm_failed: '🤖',
  sql_invalid: '🚫', sql_exec_failed: '⚠️', data_unavailable: '📡', unknown: '❌',
};
export const ERROR_KIND_TITLES = {
  budget_exceeded: '预算超限', config_missing: '配置缺失', llm_failed: 'AI 服务异常',
  sql_invalid: 'SQL 不合规', sql_exec_failed: 'SQL 执行失败',
  data_unavailable: '数据源不可用', unknown: '系统错误',
};

export const getErrorKindMeta = (T, kind) => {
  const isCritical = kind === 'budget_exceeded' || kind === 'sql_invalid' || kind === 'unknown';
  const baseColor = isCritical ? T.accent : T.warn;
  return {
    icon: ERROR_KIND_ICONS[kind] || ERROR_KIND_ICONS.unknown,
    title: ERROR_KIND_TITLES[kind] || ERROR_KIND_TITLES.unknown,
    color: baseColor,
    bg: `color-mix(in oklch, ${baseColor} 13%, transparent)`,
  };
};

export function ErrorBanner({ T, error, error_kind, user_message, is_retryable, onRetry, question }) {
  const errMeta = getErrorKindMeta(T, error_kind);
  return (
    <div style={{
      padding: '10px 14px', borderRadius: 8,
      background: errMeta.bg, border: `1px solid ${errMeta.color}`,
      color: errMeta.color, fontSize: 12.5,
      display: 'flex', alignItems: 'flex-start', gap: 10,
    }}>
      <span style={{ fontSize: 16, lineHeight: 1.2 }}>{errMeta.icon}</span>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 500, marginBottom: 2 }}>{errMeta.title}</div>
        <div style={{ opacity: 0.9 }}>{user_message || error}</div>
      </div>
      {is_retryable && onRetry && (
        <button onClick={() => onRetry(question)} style={{
          padding: '4px 10px', borderRadius: 5, fontSize: 11,
          border: '1px solid currentColor', background: 'transparent', color: 'inherit',
          cursor: 'pointer', fontFamily: 'inherit', flexShrink: 0,
        }}>重试</button>
      )}
    </div>
  );
}
