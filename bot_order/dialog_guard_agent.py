import json
import re
from typing import Any, Dict, Optional

from asgiref.sync import sync_to_async

from .llm_client import LiteLLMClient


class DialogGuardAgent:
    """Short LLM guard for identity, abuse, prompt attacks and off-topic turns."""

    DEFAULT_PREFIX = "Я Елизавета, сотрудник аварийно-диспетчерской службы."

    def __init__(self, llm: LiteLLMClient):
        self.llm = llm

    async def check(
        self,
        *,
        text: str,
        state: Dict[str, Any],
        session_id: str,
        message_log_id: Optional[int],
    ) -> Dict[str, Any]:
        prompt = await self._build_prompt(text=text, state=state)
        if not prompt:
            return self._default_result()
        result = await self.llm.json_call(
            prompt=prompt,
            session_id=session_id,
            message_id=message_log_id,
            caller_service="DialogGuardAgent.check",
            prompt_slug="dialog-guard-lite",
            max_tokens=120,
            temperature=0.0,
        )
        identity_requested = self._identity_requested(text)
        action = str(result.get("action") or "continue").strip().lower()
        if action not in {"continue", "identity_redirect", "soft_redirect", "block"}:
            action = "continue"
        reply_prefix = str(result.get("reply_prefix") or "").strip()
        if identity_requested:
            action = "identity_redirect"
            reply_prefix = self.DEFAULT_PREFIX
        elif action == "identity_redirect":
            action = "continue"
            reply_prefix = ""
        elif action != "identity_redirect":
            reply_prefix = ""
        if action == "identity_redirect" and not reply_prefix:
            reply_prefix = self.DEFAULT_PREFIX
        if action == "continue":
            use_message_for_order = True
        elif action in {"identity_redirect", "soft_redirect"}:
            use_message_for_order = bool(result.get("use_message_for_order", False))
        else:
            use_message_for_order = False

        return {
            "allowed": action != "block",
            "action": action,
            "risk_code": result.get("risk_code"),
            "reason": result.get("reason") or "",
            "use_message_for_order": use_message_for_order,
            "reply_prefix": reply_prefix,
            "safe_reply": result.get("safe_reply") or "",
            "raw": result.get("_raw_response"),
            "continue_order_flow": action != "block",
        }

    def _identity_requested(self, text: str) -> bool:
        value = (text or "").strip().lower().replace("ё", "е")
        if not value:
            return False
        return bool(
            re.search(
                r"\b(?:бот|робот|ии|ai|искусственн\w*|нейросет\w*|человек)\b|кто ты",
                value,
                flags=re.IGNORECASE,
            )
        )

    def _default_result(self) -> Dict[str, Any]:
        return {
            "allowed": True,
            "action": "continue",
            "risk_code": None,
            "reason": "",
            "use_message_for_order": True,
            "reply_prefix": "",
            "safe_reply": "",
            "continue_order_flow": True,
        }

    async def _build_prompt(self, *, text: str, state: Dict[str, Any]) -> str:
        template = await self._load_prompt_template("dialog-guard-lite")
        if not template:
            return ""
        address = state.get("address_input") or {}
        problem = state.get("problem") or {}
        control = state.get("control") or {}
        dialog_context = state.get("dialog_context") or {}
        known_facts = {
            "address_ready": bool(address.get("city") and address.get("street") and address.get("house")),
            "problem_present": bool((problem.get("txtPrb") or "").strip()),
            "contact_ready": bool(((state.get("contact") or {}).get("name") or "").strip() and ((state.get("contact") or {}).get("phone") or "").strip()),
        }
        return (
            template
            .replace("{user_message}", text or "")
            .replace("{stage}", str(dialog_context.get("previous_stage") or control.get("stage") or "new"))
            .replace("{last_bot_question}", str(dialog_context.get("last_bot_question") or ""))
            .replace("{known_facts}", json.dumps(known_facts, ensure_ascii=False, separators=(",", ":")))
            .replace("{txtPrb}", str(problem.get("txtPrb") or ""))
            .replace("{known_address}", self._format_address(address))
        )

    def _format_address(self, address: Dict[str, Any]) -> str:
        parts = [
            address.get("city"),
            address.get("street"),
            address.get("house"),
            address.get("flat"),
        ]
        return ", ".join(str(part) for part in parts if part)

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
