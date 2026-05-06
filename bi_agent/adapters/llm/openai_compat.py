"""openai_compat — OpenAI-compatible HTTP（覆盖 GPT / Gemini / DeepSeek / Ollama / vLLM）。

所有走 chat.completions API 的 provider 都用本 adapter；只是 base_url 不同。
v0.3.2 私有部署预留：vLLM (http://host:8000/v1) 和 Ollama (http://localhost:11434/v1)
直接复用本 adapter，无需新增文件。
"""
from __future__ import annotations

import openai

from bi_agent.adapters.llm.base import LLMAdapter, LLMRequest, LLMResponse


class OpenAICompatAdapter:
    """实现 LLMAdapter Protocol。"""

    def __init__(self, provider_label: str = "openai"):
        # provider_label 仅用于错误消息上下文（无业务影响）
        self._label = provider_label

    def complete(self, req: LLMRequest) -> LLMResponse:
        client = openai.OpenAI(
            api_key=req.api_key,
            base_url=req.base_url or None,
            timeout=90.0,
        )

        try:
            response = client.chat.completions.create(
                model=req.model_key,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                messages=[{"role": "system", "content": req.system}, *req.messages],
            )
        except openai.AuthenticationError:
            raise RuntimeError(f"{self._label} API Key 无效")
        except openai.RateLimitError:
            raise RuntimeError(f"{self._label} 调用频率超限")
        except openai.APIConnectionError:
            raise RuntimeError(f"无法连接到 {self._label} API")
        except Exception as e:
            raise RuntimeError(f"{self._label} 调用失败: {str(e)[:200]}")

        text = response.choices[0].message.content or ""
        it = response.usage.prompt_tokens if response.usage else 0
        ot = response.usage.completion_tokens if response.usage else 0
        return LLMResponse(text=text, input_tokens=it, output_tokens=ot)


_check: LLMAdapter = OpenAICompatAdapter()
