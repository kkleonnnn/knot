// v0.5.3: extracted from Chat.jsx L115-196 (sendQuery SSE stream parsing)
// R-118 纯函数化：本模块**严禁含**新副作用 — 仅 fetch + reader.read + JSON.parse；
// 所有 React state 操作通过 callbacks 注入。
// R-127 错误边界平移点：error_kind / user_message / is_retryable 透传给 onError callback；
// final 事件透传给 onFinal callback；clarification_needed 透传给 onClarification。

/**
 * 启动一次 query-stream SSE 调用并把事件分发给 callbacks。
 *
 * @param {string} url      `/api/conversations/{conv_id}/query-stream`
 * @param {object} body     POST body（question + 可选 upload_id）
 * @param {string} token    Bearer token
 * @param {object} callbacks {
 *   onAgentEvent(ev)         agent_start / agent_done / sql_step / clarification_needed 都先送
 *   onClarification(ev)      仅 clarification_needed 触发
 *   onError(ev)              error 事件（含 v0.4.4 R-30 error_kind/user_message/is_retryable）
 *   onFinal(ev)              final 事件（含 v0.4.2 agent_costs / v0.4.3 budget_status / v0.4.4 错误占位）
 *   onException(err)         网络/解析异常兜底
 * }
 */
export async function runQueryStream(url, body, token, callbacks) {
  const { onAgentEvent, onClarification, onError, onFinal, onException } = callbacks;
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(await resp.text());

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let ev;
        try { ev = JSON.parse(line.slice(6)); } catch { continue; }

        if (ev.type === 'agent_start' || ev.type === 'agent_done' || ev.type === 'sql_step') {
          onAgentEvent(ev);
        }
        if (ev.type === 'clarification_needed') {
          onAgentEvent(ev);
          onClarification(ev);
        }
        if (ev.type === 'error') {
          // v0.4.4 R-30/R-33：error_translator 翻译产物（kind/user_message/is_retryable）透传
          onError(ev);
        }
        if (ev.type === 'final') {
          onFinal(ev);
        }
      }
    }
  } catch (err) {
    onException(err);
  }
}
