from typing import Dict, Optional

from asgiref.sync import sync_to_async

from .llm_client import LiteLLMClient


class QuestionAgent:
    def __init__(self, llm: LiteLLMClient):
        self.llm = llm

    async def generate_category_question(
        self,
        *,
        txt_prb: str,
        missing_fact: str,
        session_id: str,
        message_id: Optional[int],
    ) -> Dict:
        return await self.generate_question(
            txt_prb=txt_prb,
            missing_fact=missing_fact,
            session_id=session_id,
            message_id=message_id,
        )

    async def generate_question(
        self,
        *,
        txt_prb: str,
        missing_fact: str,
        session_id: str,
        message_id: Optional[int],
    ) -> Dict:
        correction = ""
        last_question = ""
        for _attempt in range(3):
            prompt = await self._build_generator_prompt(
                txt_prb=txt_prb,
                missing_fact=missing_fact,
                correction=correction,
                last_question=last_question,
            )
            if not prompt:
                return {
                    "question": "",
                    "valid": False,
                    "validation": {
                        "valid": False,
                        "reason": "question_generator_prompt_missing",
                        "correction_for_llm": "",
                    },
                }
            generated = await self.llm.json_call(
                prompt=prompt,
                session_id=session_id,
                message_id=message_id,
                caller_service="QuestionAgent.generator",
                prompt_slug="question-generator-lite",
                max_tokens=220,
                temperature=0.2,
            )
            question = (generated.get("question") or generated.get("_raw_response") or "").strip()
            question = question.strip("` \n\r\t")
            last_question = question
            if not question:
                correction = "Верни один короткий вопрос в JSON с ключом question."
                continue
            validation = await self.validate_question(
                question=question,
                txt_prb=txt_prb,
                missing_fact=missing_fact,
                session_id=session_id,
                message_id=message_id,
            )
            if validation.get("valid"):
                return {"question": question, "valid": True, "validation": validation}
            correction = validation.get("correction_for_llm") or validation.get("reason") or ""

        return {
            "question": last_question,
            "valid": False,
            "validation": {
                "valid": False,
                "reason": "question_generation_failed",
                "correction_for_llm": correction,
            },
        }

    async def validate_question(
        self,
        *,
        question: str,
        txt_prb: str,
        missing_fact: str,
        session_id: str,
        message_id: Optional[int],
    ) -> Dict:
        prompt = await self._build_validator_prompt(question=question, txt_prb=txt_prb, missing_fact=missing_fact)
        if not prompt:
            return {
                "valid": False,
                "reason": "question_validator_prompt_missing",
                "correction_for_llm": "Сформулируй другой короткий открытый вопрос.",
                "raw": None,
            }
        result = await self.llm.json_call(
            prompt=prompt,
            session_id=session_id,
            message_id=message_id,
            caller_service="QuestionAgent.validator",
            prompt_slug="question-validator-lite",
            max_tokens=260,
            temperature=0.0,
        )
        return {
            "valid": bool(result.get("valid")),
            "reason": result.get("reason") or "",
            "correction_for_llm": result.get("correction_for_llm") or "",
            "raw": result.get("_raw_response"),
        }

    async def _build_validator_prompt(self, *, question: str, txt_prb: str, missing_fact: str) -> str:
        template = await self._load_prompt_template("question-validator-lite")
        if template:
            return (
                template
                .replace("{txtPrb}", txt_prb or "")
                .replace("{missing_fact}", missing_fact or "")
                .replace("{question_goal}", missing_fact or "")
                .replace("{question}", question or "")
            )
        return ""

    async def _build_generator_prompt(self, *, txt_prb: str, missing_fact: str, correction: str, last_question: str) -> str:
        template = await self._load_prompt_template("question-generator-lite")
        if template:
            return (
                template
                .replace("{txtPrb}", txt_prb or "")
                .replace("{missing_fact}", missing_fact or "")
                .replace("{question_goal}", missing_fact or "")
                .replace("{previous_bad_question}", last_question or "")
                .replace("{validator_feedback}", correction or "")
            )
        return ""

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
