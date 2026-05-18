import asyncio
import os
from typing import Any, Dict, Optional

from ai_agent_service import AIAgentService

from .utils import parse_json_object


class LiteLLMClient:
    """Thin wrapper that forces the configured GigaChat Lite API model."""

    _parallel_semaphore = None
    _parallel_limit = None

    def __init__(self, *, tracer=None):
        self.model = "GigaChat-2"
        self.ai_agent = AIAgentService(provider="gigachat", default_model=self.model, tracer=tracer)

    async def json_call(
        self,
        *,
        prompt: str,
        session_id: Optional[str],
        message_id: Optional[int],
        caller_service: str,
        prompt_slug: str,
        max_tokens: int = 500,
        temperature: float = 0.1,
    ) -> Dict[str, Any]:
        response, usage = await self._call_with_retry(
            prompt=prompt,
            session_id=session_id,
            message_id=message_id,
            caller_service=caller_service,
            prompt_slug=prompt_slug,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        parsed = parse_json_object(response)
        if not parsed and (response or "").strip():
            retry_prompt = (
                prompt
                + "\n\nПредыдущий ответ был невалидным JSON. "
                "Верни только строгий JSON по схеме из задания: ключи в двойных кавычках, "
                "строки в двойных кавычках, без Markdown и текста вне JSON."
            )
            response, usage = await self._call_with_retry(
                prompt=retry_prompt,
                session_id=session_id,
                message_id=message_id,
                caller_service=f"{caller_service}.retry_json_contract",
                prompt_slug=prompt_slug,
                max_tokens=max_tokens,
                temperature=0.0,
            )
            parsed = parse_json_object(response)
        parsed["_raw_response"] = response
        parsed["_usage"] = usage
        return parsed

    async def text_call(
        self,
        *,
        prompt: str,
        session_id: Optional[str],
        message_id: Optional[int],
        caller_service: str,
        prompt_slug: str,
        max_tokens: int = 300,
        temperature: float = 0.2,
    ) -> str:
        response, _usage = await self._call_with_retry(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            session_id=session_id,
            message_id=message_id,
            caller_service=caller_service,
            prompt_slug=prompt_slug,
        )
        return (response or "").strip()

    async def _call_with_retry(
        self,
        *,
        prompt: str,
        session_id: Optional[str],
        message_id: Optional[int],
        caller_service: str,
        prompt_slug: str,
        max_tokens: int,
        temperature: float,
    ):
        last_exc = None
        for delay in (0, 1.0, 2.0):
            if delay:
                await asyncio.sleep(delay)
            try:
                semaphore = self._get_parallel_semaphore()
                if semaphore is None:
                    return await self._call_llm_once(
                        prompt=prompt,
                        session_id=session_id,
                        message_id=message_id,
                        caller_service=caller_service,
                        prompt_slug=prompt_slug,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                async with semaphore:
                    return await self._call_llm_once(
                        prompt=prompt,
                        session_id=session_id,
                        message_id=message_id,
                        caller_service=caller_service,
                        prompt_slug=prompt_slug,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
            except Exception as exc:
                last_exc = exc
                if "429" not in str(exc) and "Too Many Requests" not in str(exc):
                    raise
        raise last_exc

    @classmethod
    def _get_parallel_semaphore(cls):
        raw_limit = os.getenv("GIGACHAT_MAX_PARALLEL_REQUESTS", "6")
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            limit = 6
        if limit <= 0:
            return None
        if cls._parallel_semaphore is None or cls._parallel_limit != limit:
            cls._parallel_limit = limit
            cls._parallel_semaphore = asyncio.Semaphore(limit)
        return cls._parallel_semaphore

    async def _call_llm_once(
        self,
        *,
        prompt: str,
        session_id: Optional[str],
        message_id: Optional[int],
        caller_service: str,
        prompt_slug: str,
        max_tokens: int,
        temperature: float,
    ):
        return await self.ai_agent.call_llm(
            prompt=prompt,
            provider="gigachat",
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            session_id=session_id,
            message_id=message_id,
            caller_service=caller_service,
            prompt_slug=prompt_slug,
            prompt_source="runtime_generated",
        )
