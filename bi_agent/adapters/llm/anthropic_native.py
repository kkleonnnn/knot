"""anthropic_native — 直连 Anthropic SDK（messages API + ephemeral cache_control）。"""
from __future__ import annotations

import anthropic

from bi_agent.adapters.llm.base import LLMAdapter, LLMRequest, LLMResponse


class AnthropicAdapter:
    """实现 LLMAdapter Protocol。"""

    def complete(self, req: LLMRequest) -> LLMResponse:
        client_kwargs = {"api_key": req.api_key, "timeout": 90.0}
        if req.base_url:
            client_kwargs["base_url"] = req.base_url
        client = anthropic.Anthropic(**client_kwargs)

        system_block: list = [{"type": "text", "text": req.system}]
        if req.enable_prompt_cache:
            system_block[0]["cache_control"] = {"type": "ephemeral"}

        try:
            response = client.messages.create(
                model=req.model_key,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                system=system_block,
                messages=req.messages,
            )
        except anthropic.AuthenticationError:
            raise RuntimeError("Anthropic API Key 无效或已过期")
        except anthropic.RateLimitError:
            raise RuntimeError("Anthropic API 调用频率超限，请稍后再试")
        except Exception as e:
            raise RuntimeError(f"Anthropic 调用失败: {str(e)[:200]}")

        return LLMResponse(
            text=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )


# Verify Protocol fit at import time（开发时即报错而非运行时）
_check: LLMAdapter = AnthropicAdapter()
