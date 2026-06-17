import json
from typing import Any, Dict, Optional

from .llm_client import LiteLLMClient


class FinalReviewAgent:
    """Interprets the resident's reply to the final pre-registration review."""

    def __init__(self, llm: LiteLLMClient):
        self.llm = llm

    async def interpret(
        self,
        *,
        text: str,
        state: Dict[str, Any],
        session_id: str,
        message_log_id: Optional[int],
    ) -> Dict[str, Any]:
        prompt = self._build_prompt(text=text, state=state)
        result = await self.llm.json_call(
            prompt=prompt,
            session_id=session_id,
            message_id=message_log_id,
            caller_service="FinalReviewAgent.interpret",
            prompt_slug="final-review-runtime",
            max_tokens=260,
            temperature=0.0,
        )
        action = str(result.get("action") or "clarify").strip().lower()
        if action not in {
            "ready_to_register",
            "update_address",
            "update_contact",
            "update_problem",
            "update_multiple",
            "clarify",
        }:
            action = "clarify"
        fields = result.get("fields") if isinstance(result.get("fields"), list) else []
        return {
            "action": action,
            "fields": [str(item).strip().lower() for item in fields if str(item).strip()],
            "clean_text": (result.get("clean_text") or text or "").strip(),
            "mode": str(result.get("mode") or "append").strip().lower(),
            "reason": result.get("reason") or "",
            "raw": result.get("_raw_response"),
        }

    def _build_prompt(self, *, text: str, state: Dict[str, Any]) -> str:
        address = state.get("address_input") or {}
        problem = state.get("problem") or {}
        contact = state.get("contact") or {}
        dialog_context = state.get("dialog_context") or {}
        last_bot_action = dialog_context.get("last_bot_action") or ""
        last_bot_action_details = dialog_context.get("last_bot_action_details") or {}
        context = {
            "address": {
                "normalized_text": address.get("normalized_text"),
                "raw_text": address.get("raw_text"),
                "city": address.get("city"),
                "street": address.get("street"),
                "house": address.get("house"),
                "flat": address.get("flat"),
            },
            "problem": problem.get("txtPrb"),
            "contact": {
                "name": contact.get("name"),
                "phone": contact.get("phone"),
            },
        }
        compact_last_action = {
            "last_bot_action": last_bot_action,
            "details": last_bot_action_details,
        }
        return (
            "Ты классифицируешь ответ жильца на финальную проверку заявки перед регистрацией. "
            "До этого бот показал адрес, описание проблемы и контакт. "
            "Нужно понять, можно ли регистрировать заявку или пользователь хочет что-то исправить/добавить. "
            "Не создавай текст ответа пользователю. Верни только JSON.\n\n"
            f"Компактный контекст последнего вопроса: {json.dumps(compact_last_action, ensure_ascii=False)}\n"
            f"Текущая заявка JSON: {json.dumps(context, ensure_ascii=False)}\n"
            f"Ответ жильца: {json.dumps(text or '', ensure_ascii=False)}\n\n"
            "Схема JSON:\n"
            "{"
            "\"action\":\"ready_to_register|update_address|update_contact|update_problem|update_multiple|clarify\","
            "\"fields\":[\"address\"|\"contact\"|\"problem\"],"
            "\"clean_text\":\"текст с полезным исправлением или исходный ответ\","
            "\"reason\":\"короткая причина\""
            "}\n"
            "Если жилец явно согласен, что добавлять нечего и можно оформлять, action=ready_to_register. "
            "Если last_bot_action=pre_registration_review_additions и жилец отвечает 'нет', 'ничего', 'не надо', "
            "это означает что добавлять нечего и заявку можно регистрировать: action=ready_to_register. "
            "Если он добавляет квартиру, подъезд, дом, улицу или другой адресный фрагмент, action=update_address. "
            "Если он исправляет имя или телефон, action=update_contact. "
            "Если он добавляет детали неисправности или меняет смысл проблемы, action=update_problem. "
            "Если в одной фразе несколько исправлений, action=update_multiple и перечисли fields. "
            "Если ответ непонятен, action=clarify. "
            "Добавь поле mode=\"replace\", если жилец говорит, что бот записал проблему неправильно, и дает правильную формулировку. "
            "Добавь mode=\"append\", если жилец просто добавляет новую деталь к уже записанной проблеме."
        )
