"""anthropic_native — 直连 Anthropic SDK（v0.3.2 sync + v0.4.4 async）。

v0.4.4 R-31：实现 AsyncLLMAdapter.acomplete()；R-30 错误标准化抛领域异常
（不再裸 RuntimeError，便于 services/error_translator 映射）。
"""
from __future__ import annotations

import anthropic

from bi_agent.adapters.llm.base import LLMAdapter, LLMRequest, LLMResponse
from bi_agent.models.errors import LLMAuthError, LLMNetworkError, LLMRateLimitError


class AnthropicAdapter:
    """实现 LLMAdapter (sync) + AsyncLLMAdapter (async) 双 Protocol。"""

    def complete(self, req: LLMRequest) -> LLMResponse:
        client_kwargs = {"api_key": req.api_key, "timeout": 90.0}
        if req.base_url:
            client_kwargs["base_url"] = req.base_url
        client = anthropic.Anthropic(**client_kwargs)

        system_block = self._build_system_block(req)

        try:
            response = client.messages.create(
                model=req.model_key,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                system=system_block,
                messages=req.messages,
            )
        except anthropic.AuthenticationError as e:
            raise LLMAuthError("Anthropic API Key 无效或已过期") from e
        except anthropic.RateLimitError as e:
            raise LLMRateLimitError("Anthropic API 调用频率超限") from e
        except Exception as e:
            raise LLMNetworkError(f"Anthropic 调用失败: {str(e)[:200]}") from e

        return LLMResponse(
            text=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    async def acomplete(self, req: LLMRequest) -> LLMResponse:
        """v0.4.4 R-31：真异步 — anthropic.AsyncAnthropic（SDK 自带，0 新依赖）。"""
        client_kwargs = {"api_key": req.api_key, "timeout": 90.0}
        if req.base_url:
            client_kwargs["base_url"] = req.base_url
        client = anthropic.AsyncAnthropic(**client_kwargs)

        system_block = self._build_system_block(req)

        try:
            response = await client.messages.create(
                model=req.model_key,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                system=system_block,
                messages=req.messages,
            )
        except anthropic.AuthenticationError as e:
            raise LLMAuthError("Anthropic API Key 无效或已过期") from e
        except anthropic.RateLimitError as e:
            raise LLMRateLimitError("Anthropic API 调用频率超限") from e
        except Exception as e:
            raise LLMNetworkError(f"Anthropic 调用失败: {str(e)[:200]}") from e

        return LLMResponse(
            text=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    @staticmethod
    def _build_system_block(req: LLMRequest) -> list:
        """共享 system_block 构造逻辑（含 ephemeral cache_control）。"""
        block: list = [{"type": "text", "text": req.system}]
        if req.enable_prompt_cache:
            block[0]["cache_control"] = {"type": "ephemeral"}
        return block


# Verify Protocol fit at import time（开发时即报错而非运行时）
_check: LLMAdapter = AnthropicAdapter()
