import json
import re
import time
from typing import Any, Dict, Optional

from asgiref.sync import sync_to_async

from .catalog_provider import CatalogProvider, find_by_id, find_by_name
from .llm_client import LiteLLMClient
from .question_agent import QuestionAgent
from .utils import to_float


class ServiceSelectionAgent:
    HIGH_CONFIDENCE = 0.85
    CONFLICT_RE = re.compile(
        r"\b(не то|ошиб|неверн|друг|вместо|а не|помен|замен|отмен|"
        r"не течет|уже не|хочу другое|добавлю новую)\b",
        re.IGNORECASE,
    )

    def __init__(self, llm: LiteLLMClient):
        self.llm = llm
        self.tracer = getattr(llm, "tracer", None) or getattr(getattr(llm, "ai_agent", None), "tracer", None)
        self.catalog = CatalogProvider()
        self.questions = QuestionAgent(llm)

    async def select(
        self,
        *,
        state: Dict[str, Any],
        session_id: str,
        message_log_id: Optional[int],
    ) -> Dict[str, Any]:
        txt_prb = (state.get("problem") or {}).get("txtPrb") or ""
        if not txt_prb.strip():
            return {"status": "need_problem", "message": "Адрес нашла. Что случилось?"}
        classification_text = self._classification_text(state, txt_prb)
        state.setdefault("problem", {})["classification_text"] = classification_text

        catalog_meta = {"cache_hit_before": self._catalog_cache_hit()}
        snapshot = await self._timed_await(
            "ServiceSelectionAgent.catalog.get_snapshot",
            self.catalog.get_snapshot(),
            catalog_meta,
        )
        catalog_meta.update(
            {
                "service_types": len(snapshot.get("service_types") or []),
                "localizations": len(snapshot.get("localizations") or []),
                "categories": len(snapshot.get("categories") or []),
                "services": len(snapshot.get("services") or []),
            }
        )

        service_types = snapshot["service_types"]
        localizations = snapshot["localizations"]
        categories = snapshot["categories"]

        await self._timed_await(
            "ServiceSelectionAgent.gigachat_token_prefetch",
            self.llm.ai_agent._get_gigachat_token(),
            {"reason": "service_selection_prefetch"},
            redact_result=True,
        )

        classification = state.setdefault("classification", {})
        reuse_decision = await self._try_reuse_confident_classification(
            state=state,
            classification=classification,
            classification_text=classification_text,
            session_id=session_id,
            message_log_id=message_log_id,
        )
        if reuse_decision.get("reuse"):
            classification.setdefault("raw", {})["reuse"] = reuse_decision
            state.setdefault("trace", {})["service_selection_reuse"] = reuse_decision
            return await self._select_reused_service(
                state=state,
                snapshot=snapshot,
                classification=classification,
                classification_text=classification_text,
                meaning_gate=reuse_decision.get("meaning_gate") or {},
                session_id=session_id,
                message_log_id=message_log_id,
            )
        if reuse_decision.get("reset"):
            classification = state.setdefault("classification", {})

        service_type = await self._timed_await(
            "ServiceSelectionAgent._detect_service_type",
            self._detect_service_type(
                txt_prb=classification_text,
                service_types=service_types,
                session_id=session_id,
                message_log_id=message_log_id,
            ),
            {"txt_prb_len": len(classification_text or ""), "service_types": len(service_types)},
        )
        classification.update(
            {
                "service_type_id": service_type.get("service_type_id"),
                "service_type_name": service_type.get("service_type_name"),
                "confidence": {
                    **(classification.get("confidence") or {}),
                    "service_type": service_type.get("confidence", 0),
                },
                "raw": {
                    **(classification.get("raw") or {}),
                    "service_type": service_type.get("raw"),
                },
            }
        )
        if not service_type.get("service_type_id"):
            return await self._timed_await(
                "ServiceSelectionAgent._ask_clarification",
                self._ask_clarification(
                    state=state,
                    stage="service_type",
                    txt_prb=classification_text,
                    missing_fact="нужно понять характер обращения: текущая неисправность либо запрос без поломки",
                    session_id=session_id,
                    message_log_id=message_log_id,
                ),
                {"stage": "service_type"},
            )

        category = await self._timed_await(
            "ServiceSelectionAgent._detect_category",
            self._detect_category(
                txt_prb=classification_text,
                categories=categories,
                default_category_id=snapshot.get("default_category_id"),
                session_id=session_id,
                message_log_id=message_log_id,
            ),
            {"txt_prb_len": len(classification_text or ""), "categories": len(categories)},
        )
        classification.update(
            {
                "category_id": category.get("category_id"),
                "category_name": category.get("category_name"),
                "confidence": {
                    **(classification.get("confidence") or {}),
                    "category": category.get("confidence", 0),
                },
                "raw": {
                    **(classification.get("raw") or {}),
                    "category": category.get("raw"),
                },
            }
        )

        if category.get("need_question") or not category.get("category_id") or category.get("confidence", 0) < 0.7:
            attempts = state.setdefault("questions", {}).setdefault("attempts_by_stage", {})
            if int(attempts.get("category") or 0) < 2:
                return await self._timed_await(
                    "ServiceSelectionAgent._ask_clarification",
                    self._ask_clarification(
                        state=state,
                        stage="category",
                        txt_prb=classification_text,
                        missing_fact=category.get("missing_fact") or "нужно понять, с каким объектом или системой связана проблема",
                        session_id=session_id,
                        message_log_id=message_log_id,
                    ),
                    {"stage": "category"},
                )

            default_category_id = snapshot.get("default_category_id")
            default_category = find_by_id(categories, "category_id", default_category_id)
            if default_category:
                classification.update(
                    {
                        "category_id": default_category["category_id"],
                        "category_name": default_category["category_name"],
                    }
                )

        required = [
            classification.get("service_type_id"),
            classification.get("category_id"),
        ]
        if not all(required):
            return {
                "status": "need_problem",
                "message": "Расскажите чуть подробнее, что именно произошло.",
            }

        localization = await self._timed_await(
            "ServiceSelectionAgent._detect_localization",
            self._detect_localization(
                txt_prb=classification_text,
                localizations=localizations,
                session_id=session_id,
                message_log_id=message_log_id,
            ),
            {"txt_prb_len": len(classification_text or ""), "localizations": len(localizations)},
        )
        if not localization.get("localization_id"):
            localization = self._infer_localization_from_catalog(
                snapshot=snapshot,
                service_type_id=classification.get("service_type_id"),
                category_id=classification.get("category_id"),
                localizations=localizations,
            )
        classification.update(
            {
                "localization_id": localization.get("localization_id"),
                "localization_name": localization.get("localization_name"),
                "confidence": {
                    **(classification.get("confidence") or {}),
                    "localization": localization.get("confidence", 0),
                },
                "raw": {
                    **(classification.get("raw") or {}),
                    "localization": localization.get("raw"),
                },
            }
        )

        if classification.get("category_id") and classification.get("localization_id"):
            decision_guard = await self._timed_await(
                "ServiceSelectionAgent._validate_selected_filters",
                self._validate_selected_filters(
                    txt_prb=classification_text,
                    classification=classification,
                    session_id=session_id,
                    message_log_id=message_log_id,
                ),
                {
                    "service_type_id": classification.get("service_type_id"),
                    "category_id": classification.get("category_id"),
                    "localization_id": classification.get("localization_id"),
                },
            )
            classification.setdefault("raw", {})["selection_guard"] = decision_guard
            if not decision_guard.get("category_valid", True):
                classification.update({"category_id": None, "category_name": None})
                return await self._timed_await(
                    "ServiceSelectionAgent._ask_clarification",
                    self._ask_clarification(
                        state=state,
                        stage="category",
                        txt_prb=classification_text,
                        missing_fact=decision_guard.get("missing_fact") or "нужно понять, с каким объектом или системой связана проблема",
                        session_id=session_id,
                        message_log_id=message_log_id,
                    ),
                    {"stage": "category", "source": "selection_guard"},
                )
            if not decision_guard.get("localization_valid", True):
                classification.update({"localization_id": None, "localization_name": None})
                return await self._timed_await(
                    "ServiceSelectionAgent._ask_clarification",
                    self._ask_clarification(
                        state=state,
                        stage="localization",
                        txt_prb=classification_text,
                        missing_fact=decision_guard.get("missing_fact") or "нужно понять место проявления проблемы",
                        session_id=session_id,
                        message_log_id=message_log_id,
                    ),
                    {"stage": "localization", "source": "selection_guard"},
                )

        if not localization.get("localization_id"):
            missing_fact = (
                "нужно, чтобы жилец своими словами описал место проявления проблемы; "
                "вопрос не должен содержать варианты, примеры, списки и слово 'или'"
            )
            return await self._timed_await(
                "ServiceSelectionAgent._ask_clarification",
                self._ask_clarification(
                    state=state,
                    stage="localization",
                    txt_prb=classification_text,
                    missing_fact=missing_fact,
                    session_id=session_id,
                    message_log_id=message_log_id,
                ),
                {"stage": "localization"},
            )

        service = await self._timed_await(
            "ServiceSelectionAgent.resolve_service",
            self.catalog.resolve_service(
                service_type_id=classification["service_type_id"],
                localization_id=classification["localization_id"],
                category_id=classification["category_id"],
                company_id=(state.get("service_context") or {}).get("company_id"),
            ),
            {
                "service_type_id": classification.get("service_type_id"),
                "category_id": classification.get("category_id"),
                "localization_id": classification.get("localization_id"),
                "company_id": (state.get("service_context") or {}).get("company_id"),
            },
        )
        if not service:
            return {
                "status": "service_not_found",
                "message": "Пока не нашла подходящую услугу в справочнике. Расскажите проблему чуть подробнее.",
            }

        state.setdefault("service", {}).update(
            {
                "service_id": service["service_id"],
                "service_name": service["service_name"],
                "scenario_name": service["scenario_name"],
                "is_confirmed_by_user": False,
                "route_warning": service.get("route_warning"),
            }
        )
        classification["classification_text"] = classification_text
        state.setdefault("control", {}).update({"stage": "service_selected", "next_action": "pre_registration_review"})
        return {
            "status": "service_selected",
            "message": self._confirmation_message(state),
        }

    def _classification_text(self, state: Dict[str, Any], txt_prb: str) -> str:
        return (txt_prb or "").strip()

    async def _try_reuse_confident_classification(
        self,
        *,
        state: Dict[str, Any],
        classification: Dict[str, Any],
        classification_text: str,
        session_id: str,
        message_log_id: Optional[int],
    ) -> Dict[str, Any]:
        previous_text = (classification.get("classification_text") or "").strip()
        if not previous_text or not classification_text.strip():
            return {"reuse": False, "reason": "no_previous_text"}
        if not self._classification_has_required_ids(classification):
            return {"reuse": False, "reason": "missing_filter_ids"}
        if not self._has_high_confidence(classification):
            return {"reuse": False, "reason": "low_confidence"}

        if self._normalize_problem_text(previous_text) == self._normalize_problem_text(classification_text):
            meaning_gate = {"decision": "same_issue", "reason": "same_classification_text", "skipped_llm": True}
        else:
            meaning_gate = await self._timed_await(
                "ServiceSelectionAgent._check_problem_meaning_change",
                self._check_problem_meaning_change(
                    previous_text=previous_text,
                    current_text=classification_text,
                    session_id=session_id,
                    message_log_id=message_log_id,
                ),
                {"previous_len": len(previous_text), "current_len": len(classification_text)},
            )

        if meaning_gate.get("decision") != "same_issue":
            state["classification"] = {
                "confidence": {},
                "reset_reason": "problem_meaning_changed",
                "previous_classification_text": previous_text,
                "current_classification_text": classification_text,
                "meaning_gate": meaning_gate,
            }
            state["service"] = {"is_confirmed_by_user": False}
            return {"reuse": False, "reset": True, "reason": "problem_meaning_changed", "meaning_gate": meaning_gate}

        return {"reuse": True, "reason": "high_confidence_same_issue", "meaning_gate": meaning_gate}

    async def _select_reused_service(
        self,
        *,
        state: Dict[str, Any],
        snapshot: Dict[str, Any],
        classification: Dict[str, Any],
        classification_text: str,
        meaning_gate: Dict[str, Any],
        session_id: str,
        message_log_id: Optional[int],
    ) -> Dict[str, Any]:
        current_text = ((state.get("message") or {}).get("current_text") or classification_text)
        skip_guard = self._can_skip_decision_guard(
            snapshot=snapshot,
            classification=classification,
            current_text=current_text,
            meaning_gate=meaning_gate,
        )
        classification.setdefault("raw", {})["decision_guard_skip"] = {
            "skipped": skip_guard,
            "reason": "high_confidence_single_service_same_issue_no_conflict" if skip_guard else "guard_required",
        }
        if not skip_guard:
            decision_guard = await self._timed_await(
                "ServiceSelectionAgent._validate_selected_filters",
                self._validate_selected_filters(
                    txt_prb=classification_text,
                    classification=classification,
                    session_id=session_id,
                    message_log_id=message_log_id,
                ),
                {
                    "service_type_id": classification.get("service_type_id"),
                    "category_id": classification.get("category_id"),
                    "localization_id": classification.get("localization_id"),
                    "source": "reuse",
                },
            )
            classification.setdefault("raw", {})["selection_guard"] = decision_guard
            if not decision_guard.get("category_valid", True) or not decision_guard.get("localization_valid", True):
                state["classification"] = {"confidence": {}, "reset_reason": "decision_guard_rejected_reuse"}
                state["service"] = {"is_confirmed_by_user": False}
                return await self.select(state=state, session_id=session_id, message_log_id=message_log_id)

        service = await self._timed_await(
            "ServiceSelectionAgent.resolve_service",
            self.catalog.resolve_service(
                service_type_id=classification["service_type_id"],
                localization_id=classification["localization_id"],
                category_id=classification["category_id"],
                company_id=(state.get("service_context") or {}).get("company_id"),
            ),
            {
                "service_type_id": classification.get("service_type_id"),
                "category_id": classification.get("category_id"),
                "localization_id": classification.get("localization_id"),
                "company_id": (state.get("service_context") or {}).get("company_id"),
                "source": "reuse",
            },
        )
        if not service:
            state["classification"] = {"confidence": {}, "reset_reason": "reused_service_not_found"}
            state["service"] = {"is_confirmed_by_user": False}
            return await self.select(state=state, session_id=session_id, message_log_id=message_log_id)

        state.setdefault("service", {}).update(
            {
                "service_id": service["service_id"],
                "service_name": service["service_name"],
                "scenario_name": service["scenario_name"],
                "is_confirmed_by_user": False,
                "route_warning": service.get("route_warning"),
            }
        )
        classification["classification_text"] = classification_text
        state.setdefault("control", {}).update({"stage": "service_selected", "next_action": "pre_registration_review"})
        return {
            "status": "service_selected",
            "message": self._confirmation_message(state),
        }

    async def _check_problem_meaning_change(
        self,
        *,
        previous_text: str,
        current_text: str,
        session_id: str,
        message_log_id: Optional[int],
    ) -> Dict[str, Any]:
        prompt = (
            "Сравни старое и новое описание заявки. Верни только JSON.\n"
            f"OLD={json.dumps(previous_text or '', ensure_ascii=False)}\n"
            f"NEW={json.dumps(current_text or '', ensure_ascii=False)}\n"
            "same_issue: NEW только уточняет ту же проблему. "
            "changed_issue: изменился объект, тип работ, аварийность или смысл заявки. "
            "unclear: непонятно.\n"
            '{"decision":"same_issue|changed_issue|unclear","reason":"кратко"}'
        )
        result = await self.llm.json_call(
            prompt=prompt,
            session_id=session_id,
            message_id=message_log_id,
            caller_service="ServiceSelectionAgent.meaning_gate",
            prompt_slug="service-selection-meaning-gate-runtime",
            max_tokens=90,
            temperature=0.0,
        )
        decision = str(result.get("decision") or "unclear").strip().lower()
        if decision not in {"same_issue", "changed_issue", "unclear"}:
            decision = "unclear"
        return {
            "decision": decision,
            "reason": result.get("reason") or "",
            "raw": result.get("_raw_response"),
        }

    def _classification_has_required_ids(self, classification: Dict[str, Any]) -> bool:
        return bool(
            classification.get("service_type_id")
            and classification.get("category_id")
            and classification.get("localization_id")
        )

    def _has_high_confidence(self, classification: Dict[str, Any]) -> bool:
        confidence = classification.get("confidence") or {}
        return all(
            to_float(confidence.get(key), 0.0) >= self.HIGH_CONFIDENCE
            for key in ("service_type", "category", "localization")
        )

    def _matching_services(self, snapshot: Dict[str, Any], classification: Dict[str, Any]) -> list:
        return [
            service for service in (snapshot.get("services") or [])
            if service.get("service_type_id") == classification.get("service_type_id")
            and service.get("category_id") == classification.get("category_id")
            and service.get("localization_id") == classification.get("localization_id")
        ]

    def _has_conflict_words(self, text: str) -> bool:
        return bool(self.CONFLICT_RE.search((text or "").lower()))

    def _can_skip_decision_guard(
        self,
        *,
        snapshot: Dict[str, Any],
        classification: Dict[str, Any],
        current_text: str,
        meaning_gate: Dict[str, Any],
    ) -> bool:
        return (
            self._has_high_confidence(classification)
            and len(self._matching_services(snapshot, classification)) == 1
            and meaning_gate.get("decision") == "same_issue"
            and not self._has_conflict_words(current_text)
        )

    def _normalize_problem_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower().replace("ё", "е"))

    async def _ask_clarification(
        self,
        *,
        state: Dict[str, Any],
        stage: str,
        txt_prb: str,
        missing_fact: str,
        session_id: str,
        message_log_id: Optional[int],
    ) -> Dict[str, Any]:
        attempts = state.setdefault("questions", {}).setdefault("attempts_by_stage", {})
        attempts[stage] = int(attempts.get(stage) or 0) + 1
        if stage == "localization" and attempts[stage] > 1:
            missing_fact = (
                "нужно подробнее понять место проявления проблемы в свободном ответе жильца; "
                "вопрос без вариантов, примеров, списков и слова 'или'"
            )
        question = await self.questions.generate_question(
            txt_prb=txt_prb,
            missing_fact=missing_fact,
            session_id=session_id,
            message_id=message_log_id,
        )
        if question.get("valid") and question.get("question"):
            state.setdefault("questions", {}).setdefault("items", []).append(
                {
                    "stage": stage,
                    "question": question["question"],
                    "validation": question.get("validation"),
                }
            )
            state.setdefault("control", {}).update({"stage": f"{stage}_question", "next_action": "await_user"})
            return {"status": f"need_{stage}_clarification", "message": question["question"]}

        state.setdefault("control", {}).update({"stage": f"{stage}_question_failed", "next_action": "await_user"})
        fallback_questions = {
            "service_type": "Расскажите, что именно происходит сейчас и какой результат нужен.",
            "localization": (
                "Расскажите, где именно это происходит."
                if attempts.get(stage, 0) <= 1
                else "Расскажите точнее, где это происходит."
            ),
            "category": "Расскажите, с каким объектом связана проблема.",
        }
        return {
            "status": f"need_{stage}_clarification",
            "message": fallback_questions.get(stage, "Расскажите чуть подробнее, что именно произошло."),
        }

    async def _detect_service_type(self, *, txt_prb: str, service_types, session_id: str, message_log_id: Optional[int]) -> Dict[str, Any]:
        template = await self._load_prompt_template("filter-incident-type")
        prompt = template.replace("{txtPrb}", json.dumps(txt_prb, ensure_ascii=False))
        raw = await self.llm.json_call(
            prompt=prompt,
            session_id=session_id,
            message_id=message_log_id,
            caller_service="ServiceSelectionAgent.service_type",
            prompt_slug="filter-incident-type",
            max_tokens=220,
            temperature=0.0,
        )
        confidence = to_float(raw.get("confidence"), 0.0)
        incident_type = self._canonical_name(raw.get("incident_type"), ("Инцидент", "Запрос"))
        item = find_by_name(service_types, "service_type_name", incident_type) if incident_type else None
        return {
            "service_type_id": item.get("service_type_id") if item and confidence >= 0.7 else None,
            "service_type_name": item.get("service_type_name") if item and confidence >= 0.7 else None,
            "confidence": confidence,
            "missing_fact": "",
            "raw": raw,
        }

    async def _validate_selected_filters(
        self,
        *,
        txt_prb: str,
        classification: Dict[str, Any],
        session_id: str,
        message_log_id: Optional[int],
    ) -> Dict[str, Any]:
        template = await self._load_prompt_template("filter-decision-guard")
        if not template:
            return {"category_valid": True, "localization_valid": True, "missing_fact": "", "reasoning": "prompt_missing"}
        raw = classification.get("raw") or {}
        prompt = (
            template
            .replace("{txtPrb}", txt_prb or "")
            .replace("{category_name}", str(classification.get("category_name") or ""))
            .replace("{category_reason}", str((raw.get("category") or {}).get("reasoning") or ""))
            .replace("{localization_name}", str(classification.get("localization_name") or ""))
            .replace("{localization_reason}", str((raw.get("localization") or {}).get("reasoning") or ""))
        )
        result = await self.llm.json_call(
            prompt=prompt,
            session_id=session_id,
            message_id=message_log_id,
            caller_service="ServiceSelectionAgent.decision_guard",
            prompt_slug="filter-decision-guard",
            max_tokens=280,
            temperature=0.0,
        )
        return {
            "category_valid": bool(result.get("category_valid", True)),
            "localization_valid": bool(result.get("localization_valid", True)),
            "missing_fact": result.get("missing_fact") or "",
            "reasoning": result.get("reasoning") or "",
            "raw": result,
        }

    async def _detect_localization(self, *, txt_prb: str, localizations, session_id: str, message_log_id: Optional[int]) -> Dict[str, Any]:
        template = await self._load_prompt_template("filter-location-type")
        prompt = template.replace("{txtPrb}", json.dumps(txt_prb, ensure_ascii=False))
        raw = await self.llm.json_call(
            prompt=prompt,
            session_id=session_id,
            message_id=message_log_id,
            caller_service="ServiceSelectionAgent.localization",
            prompt_slug="filter-location-type",
            max_tokens=260,
            temperature=0.0,
        )
        confidence = to_float(raw.get("confidence"), 0.0)
        location_type = self._canonical_name(raw.get("location_type"), ("Индивидуальное", "Общедомовое"))
        item = find_by_name(localizations, "localization_name", location_type) if location_type else None
        return {
            "localization_id": item.get("localization_id") if item and confidence >= 0.7 else None,
            "localization_name": item.get("localization_name") if item and confidence >= 0.7 else None,
            "confidence": confidence,
            "missing_fact": "",
            "raw": raw,
        }

    async def _detect_category(
        self,
        *,
        txt_prb: str,
        categories,
        default_category_id,
        session_id: str,
        message_log_id: Optional[int],
    ) -> Dict[str, Any]:
        template = await self._load_prompt_template("filter-category")
        prompt_categories = [
            {
                "ID": item["category_id"],
                "Категория": item["category_name"],
                "Переработанное для LLM": item["llm_description"],
                "is_default": item["is_default"],
            }
            for item in categories
        ]
        prompt = template.replace("{txtPrb}", txt_prb)
        prompt = prompt.replace("{categories_json}", json.dumps(prompt_categories, ensure_ascii=False))
        prompt = prompt.replace("{is_default_id}", str(default_category_id))
        raw = await self.llm.json_call(
            prompt=prompt,
            session_id=session_id,
            message_id=message_log_id,
            caller_service="ServiceSelectionAgent.category",
            prompt_slug="filter-category",
            max_tokens=380,
            temperature=0.0,
        )
        if not raw.get("category_id") and not raw.get("category") and raw.get("_raw_response"):
            retry_prompt = (
                prompt
                + "\n\nПредыдущий ответ был невалидным: был текст вместо JSON. "
                + "Повтори классификацию и верни только JSON по требуемой схеме без анализа и Markdown."
            )
            raw = await self.llm.json_call(
                prompt=retry_prompt,
                session_id=session_id,
                message_id=message_log_id,
                caller_service="ServiceSelectionAgent.category.retry_json",
                prompt_slug="filter-category",
                max_tokens=220,
                temperature=0.0,
            )
        category_id = raw.get("category_id", raw.get("category"))
        item = find_by_id(categories, "category_id", category_id)
        if not item:
            item = find_by_name(categories, "category_name", raw.get("category_name") or raw.get("category"))
        confidence = to_float(raw.get("confidence"), 0.0)
        return {
            "category_id": item.get("category_id") if item and confidence >= 0.7 else None,
            "category_name": item.get("category_name") if item and confidence >= 0.7 else None,
            "confidence": confidence,
            "need_question": confidence < 0.7 or not item,
            "question": "",
            "missing_fact": raw.get("missing_fact") or raw.get("reasoning") or "нужно понять, с каким объектом или системой связана проблема",
            "raw": raw,
        }

    async def _load_prompt_template(self, slug: str) -> str:
        def load_sync():
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

        metadata = {"slug": slug}
        if self.tracer:
            self.tracer.start(f"ServiceSelectionAgent.prompt_template.{slug}", metadata)
        try:
            template = await sync_to_async(load_sync)()
        except Exception as exc:
            if self.tracer:
                self.tracer.end(f"ServiceSelectionAgent.prompt_template.{slug}", error=exc)
            raise
        metadata["template_len"] = len(template or "")
        if self.tracer:
            self.tracer.end(
                f"ServiceSelectionAgent.prompt_template.{slug}",
                result={"slug": slug, "found": bool(template), "template_len": len(template or "")},
            )
        return template

    async def _timed_await(
        self,
        name: str,
        awaitable,
        metadata: Optional[Dict[str, Any]] = None,
        *,
        redact_result: bool = False,
    ):
        """Measure one awaited diagnostic step without changing decisions."""
        if not self.tracer:
            return await awaitable
        self.tracer.start(name, metadata or {})
        try:
            result = await awaitable
        except Exception as exc:
            self.tracer.end(name, error=exc)
            raise
        trace_result = {"status": "completed"} if redact_result else result
        self.tracer.end(name, result=trace_result)
        return result

    def _catalog_cache_hit(self) -> bool:
        loaded_at = getattr(self.catalog.__class__, "_loaded_at", 0.0) or 0.0
        ttl = getattr(self.catalog.__class__, "_ttl_seconds", 0) or 0
        return bool(self.catalog.__class__._snapshot and time.monotonic() - loaded_at < ttl)

    def _canonical_name(self, value: Any, allowed: tuple) -> Optional[str]:
        normalized = self._normalize_catalog_name(value)
        if not normalized or normalized == "null":
            return None
        for item in allowed:
            if self._normalize_catalog_name(item) == normalized:
                return item
        return None

    def _normalize_catalog_name(self, value: Any) -> str:
        text = str(value or "").strip().lower().replace("ё", "е")
        text = text.translate(str.maketrans({"“": "", "”": "", "„": "", "«": "", "»": "", '"': ""}))
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _infer_localization_from_catalog(
        self,
        *,
        snapshot: Dict[str, Any],
        service_type_id: Optional[int],
        category_id: Optional[int],
        localizations,
    ) -> Dict[str, Any]:
        if not service_type_id or not category_id:
            return {"localization_id": None, "localization_name": None, "confidence": 0.0, "raw": None}
        matches = [
            service
            for service in snapshot.get("services", [])
            if service.get("service_type_id") == service_type_id
            and service.get("category_id") == category_id
        ]
        localization_ids = sorted({service.get("localization_id") for service in matches if service.get("localization_id")})
        if len(localization_ids) != 1:
            return {"localization_id": None, "localization_name": None, "confidence": 0.0, "raw": {"source": "catalog_inference", "candidate_localization_ids": localization_ids}}
        item = find_by_id(localizations, "localization_id", localization_ids[0])
        return {
            "localization_id": item.get("localization_id") if item else None,
            "localization_name": item.get("localization_name") if item else None,
            "confidence": 1.0 if item else 0.0,
            "raw": {"source": "catalog_inference", "candidate_localization_ids": localization_ids},
        }

    def _confirmation_message(self, state: Dict[str, Any]) -> str:
        classification = state.get("classification") or {}
        category = classification.get("category_name") or "проблеме"
        localization = classification.get("localization_name") or ""
        if localization:
            return f"Приняла: {category.lower()}, {localization.lower()}. Скажите, можно оформлять заявку на этот адрес."
        return f"Приняла: {category.lower()}. Скажите, можно оформлять заявку на этот адрес."
