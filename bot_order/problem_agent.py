import re
from difflib import SequenceMatcher
from typing import Dict, Optional

from asgiref.sync import sync_to_async

from .llm_client import LiteLLMClient


class ProblemAgent:
    def __init__(self, llm: LiteLLMClient):
        self.llm = llm

    async def extract_fragment(
        self,
        *,
        current_txt_prb: str,
        user_message: str,
        address_text: str,
        session_id: str,
        message_id: Optional[int],
    ) -> Dict:
        prompt = await self._build_prompt(
            current_txt_prb=current_txt_prb,
            user_message=user_message,
            address_text=address_text,
        )
        if not prompt:
            return {"is_problem_detail": False, "clean_fragment": "", "reason": "prompt_missing"}

        result = await self.llm.json_call(
            prompt=prompt,
            session_id=session_id,
            message_id=message_id,
            caller_service="ProblemAgent.fragment",
            prompt_slug="problem-fragment-lite",
            max_tokens=140,
            temperature=0.0,
        )
        clean_fragment = (result.get("clean_fragment") or "").strip()
        is_problem_detail = bool(result.get("is_problem_detail"))
        contract_issue = self._fragment_contract_issue(
            user_message=user_message,
            address_text=address_text,
            clean_fragment=clean_fragment,
        )
        if is_problem_detail and clean_fragment and contract_issue:
            retry = await self.llm.json_call(
                prompt=(
                    prompt
                    + "\n\nПредыдущий ответ нарушил контракт: "
                    + contract_issue
                    + ". Верни JSON заново: сохрани объект, действие и все значимые номера из реплики; не добавляй слова, которых нет в реплике."
                ),
                session_id=session_id,
                message_id=message_id,
                caller_service="ProblemAgent.fragment.retry_contract",
                prompt_slug="problem-fragment-lite",
                max_tokens=140,
                temperature=0.0,
            )
            retry_fragment = (retry.get("clean_fragment") or "").strip()
            retry_issue = self._fragment_contract_issue(
                user_message=user_message,
                address_text=address_text,
                clean_fragment=retry_fragment,
            )
            if bool(retry.get("is_problem_detail")) and retry_fragment and not retry_issue:
                result = retry
                clean_fragment = retry_fragment
                is_problem_detail = True
            else:
                clean_fragment = (user_message or "").strip()
                is_problem_detail = bool(clean_fragment)
                result["reason"] = f"{result.get('reason') or ''}; contract_fallback:{contract_issue}".strip("; ")
        if is_problem_detail and clean_fragment and not self._fragment_is_grounded(user_message, clean_fragment):
            clean_fragment = (user_message or "").strip()
        if clean_fragment and self._fragment_is_address_only(address_text, clean_fragment):
            clean_fragment = ""
            is_problem_detail = False
        return {
            "is_problem_detail": is_problem_detail,
            "clean_fragment": clean_fragment,
            "reason": result.get("reason") or "",
            "raw": result.get("_raw_response"),
        }

    def _fragment_is_grounded(self, user_message: str, clean_fragment: str) -> bool:
        source_tokens = set(self._meaningful_tokens(user_message))
        fragment_tokens = self._meaningful_tokens(clean_fragment)
        if not fragment_tokens:
            return False
        for fragment_token in fragment_tokens:
            for source_token in source_tokens:
                if fragment_token == source_token:
                    return True
                if len(fragment_token) >= 4 and len(source_token) >= 4:
                    if fragment_token.startswith(source_token[:4]) or source_token.startswith(fragment_token[:4]):
                        return True
        return False

    def _fragment_contract_issue(self, *, user_message: str, address_text: str, clean_fragment: str) -> str:
        if not clean_fragment:
            return ""
        source_digits = set(re.findall(r"\d+", user_message or ""))
        address_digits = set(re.findall(r"\d+", address_text or ""))
        problem_digits = source_digits - address_digits
        fragment_digits = set(re.findall(r"\d+", clean_fragment or ""))
        missing_digits = sorted(problem_digits - fragment_digits)
        if missing_digits:
            return "потеряны значимые номера из реплики: " + ", ".join(missing_digits)

        source_tokens = self._meaningful_tokens(user_message)
        allowed = []
        for token in self._meaningful_tokens(clean_fragment):
            if any(self._token_supported(token, source_token) for source_token in source_tokens):
                continue
            allowed.append(token)
        if allowed:
            return "добавлены неподтвержденные слова: " + ", ".join(sorted(set(allowed))[:5])
        return ""

    def _token_supported(self, token: str, source_token: str) -> bool:
        if token == source_token:
            return True
        if len(token) < 4 or len(source_token) < 4:
            return False
        if token.startswith(source_token[:4]) or source_token.startswith(token[:4]):
            return True
        return SequenceMatcher(None, token, source_token).ratio() >= 0.72

    def _meaningful_tokens(self, text: str):
        return [
            token
            for token in re.findall(r"[a-zа-яё0-9]+", (text or "").lower().replace("ё", "е"))
            if len(token) >= 3
        ]

    def _fragment_is_address_only(self, address_text: str, clean_fragment: str) -> bool:
        address_tokens = set(self._meaningful_tokens(address_text))
        fragment_tokens = self._meaningful_tokens(clean_fragment)
        if not address_tokens or not fragment_tokens:
            return False
        return all(token in address_tokens for token in fragment_tokens)

    async def _build_prompt(self, *, current_txt_prb: str, user_message: str, address_text: str) -> str:
        template = await self._load_prompt_template("problem-fragment-lite")
        if not template:
            return ""
        return (
            template
            .replace("{current_txtPrb}", current_txt_prb or "")
            .replace("{user_message}", user_message or "")
            .replace("{address_text}", address_text or "")
        )

    async def _load_prompt_template(self, slug: str) -> str:
        def load_sync():
            try:
                from django.db import connection

                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT template
                        FROM llm_tester_prompttemplate
                        WHERE slug = %s AND is_active = true
                        ORDER BY id DESC
                        LIMIT 1
                        """,
                        [slug],
                    )
                    row = cursor.fetchone()
                return row[0] if row else ""
            except Exception:
                return ""

        return await sync_to_async(load_sync)()
