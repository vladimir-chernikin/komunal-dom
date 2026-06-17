import asyncio
import json
import os
import threading
from typing import Any, Dict, Optional

import httpx

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

    async def function_call(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        function_name: str,
        function_description: str,
        parameters: Dict[str, Any],
        session_id: Optional[str],
        message_id: Optional[int],
        caller_service: str,
        prompt_slug: str,
        max_tokens: int = 300,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        response_payload, usage = await self._function_call_with_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            function_name=function_name,
            function_description=function_description,
            parameters=parameters,
            session_id=session_id,
            message_id=message_id,
            caller_service=caller_service,
            prompt_slug=prompt_slug,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        choice = (response_payload.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        function_call = message.get("function_call") or {}
        arguments = function_call.get("arguments")
        if isinstance(arguments, dict):
            parsed = dict(arguments)
        elif isinstance(arguments, str) and arguments.strip():
            try:
                parsed = json.loads(arguments)
            except Exception:
                parsed = parse_json_object(arguments)
        else:
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}
        parsed["_raw_response"] = json.dumps(
            {
                "finish_reason": choice.get("finish_reason"),
                "message": message,
            },
            ensure_ascii=False,
        )
        parsed["_usage"] = usage
        parsed["_finish_reason"] = choice.get("finish_reason")
        parsed["_function_call_name"] = function_call.get("name")
        return parsed

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
                semaphore = await self._acquire_parallel_slot()
                try:
                    return await self._call_llm_once(
                        prompt=prompt,
                        session_id=session_id,
                        message_id=message_id,
                        caller_service=caller_service,
                        prompt_slug=prompt_slug,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                finally:
                    if semaphore is not None:
                        semaphore.release()
            except Exception as exc:
                last_exc = exc
                if "429" not in str(exc) and "Too Many Requests" not in str(exc):
                    raise
        raise last_exc

    async def _function_call_with_retry(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        function_name: str,
        function_description: str,
        parameters: Dict[str, Any],
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
                semaphore = await self._acquire_parallel_slot()
                try:
                    return await self._function_call_once(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        function_name=function_name,
                        function_description=function_description,
                        parameters=parameters,
                        session_id=session_id,
                        message_id=message_id,
                        caller_service=caller_service,
                        prompt_slug=prompt_slug,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                finally:
                    if semaphore is not None:
                        semaphore.release()
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
            cls._parallel_semaphore = threading.BoundedSemaphore(limit)
        return cls._parallel_semaphore

    async def _acquire_parallel_slot(self):
        semaphore = self._get_parallel_semaphore()
        if semaphore is None:
            return None
        await asyncio.to_thread(semaphore.acquire)
        return semaphore

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

    async def _function_call_once(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        function_name: str,
        function_description: str,
        parameters: Dict[str, Any],
        session_id: Optional[str],
        message_id: Optional[int],
        caller_service: str,
        prompt_slug: str,
        max_tokens: int,
        temperature: float,
    ):
        access_token = await self.ai_agent._get_gigachat_token()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt or ""},
                {"role": "user", "content": user_prompt or ""},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "functions": [
                {
                    "name": function_name,
                    "description": function_description,
                    "parameters": parameters,
                }
            ],
            "function_call": {"name": function_name},
        }
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.post(
                "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
                json=payload,
            )
        if response.status_code != 200:
            raise Exception(f"GigaChat API error {response.status_code}: {response.text}")
        result = response.json()
        usage = result.get("usage", {}) or {}
        total_tokens = usage.get("total_tokens", 0)
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cost_per_1k = self.ai_agent.GIGACHAT_PRICES.get(self.model, 0)
        total_cost = (total_tokens / 1000) * cost_per_1k
        usage_info = {
            "provider": "gigachat",
            "model": self.model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_rub": round(total_cost, 4),
            "cost_per_1k_tokens": cost_per_1k,
        }
        self.ai_agent._update_statistics("gigachat", total_tokens, total_cost)
        log_prompt = (
            f"SYSTEM:\n{system_prompt or ''}\n\n"
            f"USER:\n{user_prompt or ''}\n\n"
            f"FUNCTION {function_name}:\n"
            f"{json.dumps({'description': function_description, 'parameters': parameters}, ensure_ascii=False)}"
        )
        await self.ai_agent._save_statistics_to_db(
            provider="gigachat",
            model=self.model,
            prompt=log_prompt,
            response=json.dumps(result, ensure_ascii=False),
            usage_info=usage_info,
            session_id=session_id,
            message_id=message_id,
            caller_service=caller_service,
            prompt_slug=prompt_slug,
            prompt_source="function_call",
        )
        return result, usage_info
