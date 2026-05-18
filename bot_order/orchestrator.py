import re
from typing import Any, Dict, Optional

from asgiref.sync import sync_to_async

from .address_agent import AddressAgent
from .contact_agent import ContactAgent
from .customer_lookup import lookup_known_customer, normalize_phone
from .dialog_guard_agent import DialogGuardAgent
from .final_review_agent import FinalReviewAgent
from .llm_client import LiteLLMClient
from .order_agent import OrderCreationAgent
from .problem_agent import ProblemAgent
from .security_guard import SecurityGuard
from .service_agent import ServiceSelectionAgent
from .state import StateStore, compact_state
from .turn_splitter_agent import TurnSplitterAgent
from .utils import is_greeting_only


class BotOrderOrchestrator:
    """Fast graph-like order bot orchestrator."""

    def __init__(self, *, tracer=None):
        self.tracer = tracer
        self._active_stage = None
        self.state_store = StateStore()
        self.llm = LiteLLMClient(tracer=tracer)
        self.static_guard = SecurityGuard()
        self.dialog_guard = DialogGuardAgent(self.llm)
        self.address_agent = AddressAgent(self.llm)
        self.contact_agent = ContactAgent(self.llm)
        self.problem_agent = ProblemAgent(self.llm)
        self.service_agent = ServiceSelectionAgent(self.llm)
        self.final_review_agent = FinalReviewAgent(self.llm)
        self.turn_splitter = TurnSplitterAgent(self.llm)
        self.order_agent = OrderCreationAgent()

    async def handle_message(
        self,
        *,
        text: str,
        user_id: str,
        channel: str,
        session_id: str,
        message_id: Optional[str],
        message_log_id: Optional[int],
        django_user_id: Optional[int],
        source_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        state = await self.state_store.load(
            session_id=session_id,
            user_id=user_id,
            channel=channel,
            message_id=message_id,
        )
        await self._bootstrap_customer_identity(
            state=state,
            user_id=user_id,
            channel=channel,
            django_user_id=django_user_id,
            source_metadata=source_metadata or {},
        )
        previous_stage = (state.get("control") or {}).get("stage")
        state.setdefault("dialog_context", {})["previous_stage"] = previous_stage or "new"
        self._set_stage(state, "ingress_normalize")
        state.setdefault("trace", {})["current_fias_log_ids"] = []
        state.setdefault("message", {})["current_text"] = text
        if not state["message"].get("first_user_text") and not is_greeting_only(text):
            state["message"]["first_user_text"] = text
        problem_state = state.setdefault("problem", {})

        if is_greeting_only(text) and self._is_empty_dialog(previous_stage, state):
            self._set_stage(state, "greeting")
            return self._result(
                status="GREETING",
                message="Здравствуйте. Для начала определим, где обнаружена проблема. По какому адресу хотите оставить обращение?",
                state=state,
                extra={"is_greeting": True},
            )

        guard_result = await self._timed_await(
            "dialog_guard.check",
            self.dialog_guard.check(
                text=text,
                state=state,
                session_id=session_id,
                message_log_id=message_log_id,
            ),
            {"previous_stage": previous_stage, "text_len": len(text or "")},
        )
        static_guard_result = self.static_guard.check(text)
        if not static_guard_result.get("allowed"):
            guard_result.update(static_guard_result)
            guard_result["action"] = "block"
            if not guard_result.get("reply_prefix"):
                guard_result["reply_prefix"] = "Я Елизавета, сотрудник аварийно-диспетчерской службы."
            guard_result["safe_reply"] = "Помогу оформить обращение. По какому адресу хотите оставить обращение?"
        elif (
            previous_stage == "pre_registration_review"
            and not guard_result.get("allowed")
            and self.address_agent._looks_like_address_update(state, text)
        ):
            guard_result.update(
                {
                    "allowed": True,
                    "action": "allow",
                    "reason": "final_review_address_update_false_positive",
                    "continue_order_flow": True,
                    "use_message_for_order": True,
                }
            )
        state["guard"] = guard_result
        if not guard_result.get("allowed"):
            self._set_stage(state, "security_guard_blocked")
            return self._result(
                status="GUARD_BLOCKED",
                message=guard_result.get("safe_reply") or self._guard_redirect_message(state),
                state=state,
        )
        use_message_for_order = bool(guard_result.get("use_message_for_order", True))
        turn_result = await self._timed_await(
            "turn_splitter.analyze",
            self.turn_splitter.analyze(
                text=text,
                state=state,
                session_id=session_id,
                message_log_id=message_log_id,
            ),
            {"previous_stage": previous_stage, "text_len": len(text or "")},
        )
        state["turn"] = turn_result

        if previous_stage == "contact_profile_confirm":
            return await self._handle_contact_profile_confirmation(
                state=state,
                text=text,
                user_id=user_id,
                channel=channel,
                session_id=session_id,
                message_log_id=message_log_id,
                django_user_id=django_user_id,
                source_metadata=source_metadata,
            )

        if previous_stage == "contact_phone_confirm":
            return await self._handle_contact_phone_confirmation(
                state=state,
                text=text,
                user_id=user_id,
                channel=channel,
                session_id=session_id,
                message_log_id=message_log_id,
                django_user_id=django_user_id,
                source_metadata=source_metadata,
            )

        if previous_stage == "address_change_confirm":
            return await self._handle_address_change_confirmation(
                state=state,
                text=text,
            )

        if previous_stage == "pre_registration_review":
            return await self._handle_pre_registration_review(
                state=state,
                text=text,
                user_id=user_id,
                channel=channel,
                session_id=session_id,
                message_log_id=message_log_id,
                django_user_id=django_user_id,
                source_metadata=source_metadata,
            )

        if self._address_is_locked(state):
            state.setdefault("trace", {})["address_pipeline"] = "skipped_address_locked"
            address_result = {"status": "matched", "message": None, "address_validation": None}
            optional_address_result = await self._timed_await(
                "address_agent.update_optional_slots",
                self.address_agent.update_optional_slots(
                    state=state,
                    text=self._address_text_for_turn(state, text),
                    session_id=session_id,
                    message_log_id=message_log_id,
                ),
                {"address_locked": True, "text_len": len(text or "")},
            )
            if optional_address_result.get("fias_log_ids"):
                state.setdefault("trace", {})["current_fias_log_ids"] = optional_address_result.get("fias_log_ids") or []
            if optional_address_result.get("updated"):
                state.setdefault("trace", {})["address_pipeline"] = "updated_optional_slots"
            if optional_address_result.get("apartment_not_found"):
                self._append_address_note_to_problem(
                    state,
                    apartment_number=optional_address_result.get("apartment_number"),
                )
                self._rebuild_problem_text(state)
        else:
            self._set_stage(state, "address_pipeline")
            address_result = await self._timed_await(
                "address_agent.resolve",
                self.address_agent.resolve(
                    state=state,
                    text=text,
                    session_id=session_id,
                    message_log_id=message_log_id,
                ),
                {"address_locked": False, "text_len": len(text or "")},
            )
            state.setdefault("trace", {})["current_fias_log_ids"] = address_result.get("fias_log_ids") or []

        if address_result["status"] == "not_serviced":
            self._set_stage(state, "address_not_serviced")
            state.setdefault("control", {}).update(
                {
                    "is_finished": True,
                    "finish_reason": "address_not_serviced",
                    "next_action": None,
                }
            )
            return self._result(
                status="ADDRESS_NOT_SERVICED",
                message=self._not_serviced_message(state),
                state=state,
            )

        if address_result["status"] != "matched":
            await self._timed_await(
                "bot_order._record_problem_fragment",
                self._record_problem_fragment(
                    state=state,
                    text=text,
                    use_message_for_order=use_message_for_order,
                    session_id=session_id,
                    message_log_id=message_log_id,
                ),
                {"address_status": address_result["status"], "text_len": len(text or "")},
            )
            self._rebuild_problem_text(state)
            self._set_stage(state, f"address_{address_result['status']}")
            return self._result(
                status=address_result["status"].upper(),
                message=await self._address_followup_message(state, address_result),
                state=state,
            )

        contact_was_complete = self.contact_agent.is_complete(state)
        if self._should_extract_contact(state, previous_stage, contact_was_complete):
            contact_result = await self._timed_await(
                "contact_agent.extract",
                self.contact_agent.extract(
                    state=state,
                    text=self._contact_text_for_turn(state, text),
                    session_id=session_id,
                    message_log_id=message_log_id,
                ),
                {"was_complete": contact_was_complete, "text_len": len(text or "")},
            )
        else:
            contact_result = {"has_contact": False, "name": None, "phone": None, "reason": "not_contact_turn"}
        contact_was_answer = (
            previous_stage == "contact_required"
            and not contact_was_complete
            and bool(contact_result.get("name") or contact_result.get("phone"))
        )
        if not contact_was_answer:
            await self._timed_await(
                "bot_order._record_problem_fragment",
                self._record_problem_fragment(
                    state=state,
                    text=text,
                    use_message_for_order=use_message_for_order,
                    session_id=session_id,
                    message_log_id=message_log_id,
                ),
                {"contact_was_answer": contact_was_answer, "text_len": len(text or "")},
            )
        self._rebuild_problem_text(state)

        if not self.contact_agent.is_complete(state):
            if self._has_unconfirmed_profile_contact(state):
                self._set_stage(state, "contact_profile_confirm")
                return self._result(
                    status="CONTACT_PROFILE_CONFIRM",
                    message=self._profile_contact_confirmation_message(state),
                    state=state,
                )
            self._set_stage(state, "contact_required")
            return self._result(
                status="CONTACT_REQUIRED",
                message=await self._contact_prompt(state),
                state=state,
            )

        if self._problem_looks_empty_or_address_only(state):
            self._set_stage(state, "problem_required")
            return self._result(
                status="PROBLEM_REQUIRED",
                message=await self._serviced_address_problem_prompt(state),
                state=state,
            )

        self._set_stage(state, "service_selection")
        service_result = await self._timed_await(
            "service_agent.select",
            self.service_agent.select(
                state=state,
                session_id=session_id,
                message_log_id=message_log_id,
            ),
            {"txt_prb_len": len(((state.get("problem") or {}).get("txtPrb") or ""))},
        )
        if service_result["status"] != "service_selected":
            self._set_stage(state, service_result["status"])
            return self._result(
                status=service_result["status"].upper(),
                message=service_result["message"],
                state=state,
            )

        self._set_stage(state, "pre_registration_review")
        return self._result(
            status="PRE_REGISTRATION_REVIEW",
            message=await self._pre_registration_review_message(state),
            state=state,
            service_id=(state.get("service") or {}).get("service_id"),
            service_name=(state.get("service") or {}).get("service_name"),
        )

    async def _create_order(
        self,
        *,
        state: Dict[str, Any],
        text: str,
        user_id: str,
        channel: str,
        session_id: str,
        message_log_id: Optional[int],
        django_user_id: Optional[int],
        source_metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if await self._voice_revision_is_superseded(source_metadata):
            return self._result(
                status="SUPERSEDED_REVISION",
                message="",
                state=state,
                superseded_revision=True,
            )

        self._set_stage(state, "order_create")
        order_result = await self.order_agent.create(
            state=state,
            original_text=(state.get("message") or {}).get("first_user_text") or text,
            channel=channel,
            session_id=session_id,
            user_id=user_id,
            django_user_id=django_user_id,
            message_log_id=message_log_id,
            source_metadata=source_metadata or {},
        )
        if order_result.get("created"):
            number = order_result.get("work_order_no") or order_result.get("work_order_id")
            company_name = await self._company_name((state.get("service_context") or {}).get("company_id"))
            company_part = f" в компанию {company_name}" if company_name else ""
            finish_marker = (
                "\n<-------- Диалог завершен --------->"
                if channel in {"telegram", "max", "maxchat"}
                else ""
            )
            state.setdefault("control", {}).update(
                {
                    "is_finished": True,
                    "finish_reason": "order_created",
                    "next_action": None,
                }
            )
            return self._result(
                status="CONFIRMED",
                message=f"Спасибо за обращение{company_part}. Заявка создана. Номер: {number}.{finish_marker}",
                state=state,
                service_id=(state.get("service") or {}).get("service_id"),
                service_name=(state.get("service") or {}).get("service_name"),
                order_result=order_result,
            )
        return self._result(
            status="ORDER_ERROR",
            message=order_result.get("message") or "Не удалось создать заявку.",
            state=state,
            order_result=order_result,
        )

    async def _handle_contact_profile_confirmation(
        self,
        *,
        state: Dict[str, Any],
        text: str,
        user_id: str,
        channel: str,
        session_id: str,
        message_log_id: Optional[int],
        django_user_id: Optional[int],
        source_metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        turn = state.get("turn") or {}
        if turn.get("address_change_attempt") or (
            turn.get("has_address") and not turn.get("has_contact") and not turn.get("has_problem")
        ):
            state.setdefault("pending_address_change", {})["address_text"] = turn.get("address_text") or text
            self._set_stage(state, "address_change_confirm")
            return self._result(
                status="ADDRESS_CHANGE_CONFIRM",
                message=(
                    "Похоже, вы указали другой адрес обращения. "
                    "Подтвердите, это новый адрес для текущей заявки? "
                    "Если нужно оформить обращение по двум адресам, для второго адреса надо создать отдельную заявку."
                ),
                state=state,
            )

        decision = await self._interpret_contact_profile_reply(
            state=state,
            text=text,
            session_id=session_id,
            message_log_id=message_log_id,
        )
        contact = state.setdefault("contact", {})
        if decision.get("use_profile"):
            contact["name"] = contact.get("candidate_name") or contact.get("name")
            contact["profile_name_confirmed"] = True
            contact["status"] = "complete" if self.contact_agent.is_complete(state) else "incomplete"
            if self._needs_contact_phone_confirmation(state):
                self._set_stage(state, "contact_phone_confirm")
                return self._result(
                    status="CONTACT_PHONE_CONFIRM",
                    message=self._profile_contact_phone_confirmation_message(state),
                    state=state,
                )
            if not self.contact_agent.is_complete(state):
                self._set_stage(state, "contact_required")
                return self._result(status="CONTACT_REQUIRED", message=await self._contact_prompt(state), state=state)
            contact["profile_confirmed"] = True
            return await self._continue_after_contact_ready(
                state=state,
                session_id=session_id,
                message_log_id=message_log_id,
            )

        extracted = await self.contact_agent.extract(
            state=state,
            text=decision.get("clean_text") or text,
            session_id=session_id,
            message_log_id=message_log_id,
        )
        if decision.get("name"):
            contact["name"] = decision["name"]
        if decision.get("phone"):
            contact["phone"] = decision["phone"]
            contact["phone_confirmed"] = True
        contact["status"] = "complete" if self.contact_agent.is_complete(state) else "incomplete"
        if self._needs_contact_phone_confirmation(state):
            self._set_stage(state, "contact_phone_confirm")
            return self._result(
                status="CONTACT_PHONE_CONFIRM",
                message=self._profile_contact_phone_confirmation_message(state),
                state=state,
            )
        if not self.contact_agent.is_complete(state):
            self._set_stage(state, "contact_required")
            return self._result(status="CONTACT_REQUIRED", message=await self._contact_prompt(state), state=state)
        return await self._continue_after_contact_ready(
            state=state,
            session_id=session_id,
            message_log_id=message_log_id,
            contact_extraction=extracted,
        )

    async def _handle_contact_phone_confirmation(
        self,
        *,
        state: Dict[str, Any],
        text: str,
        user_id: str,
        channel: str,
        session_id: str,
        message_log_id: Optional[int],
        django_user_id: Optional[int],
        source_metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        decision = await self._interpret_contact_phone_reply(
            state=state,
            text=text,
            session_id=session_id,
            message_log_id=message_log_id,
        )
        contact = state.setdefault("contact", {})
        if decision.get("use_known_phone"):
            contact["phone"] = self._known_contact_phone(contact)
            contact["phone_confirmed"] = True
            contact["profile_confirmed"] = True
        elif decision.get("phone"):
            contact["phone"] = decision["phone"]
            contact["phone_confirmed"] = True
            contact["profile_confirmed"] = True
        else:
            extracted = await self.contact_agent.extract(
                state=state,
                text=decision.get("clean_text") or text,
                session_id=session_id,
                message_log_id=message_log_id,
            )
            if extracted.get("phone"):
                contact["phone_confirmed"] = True
            if not self.contact_agent.is_complete(state):
                self._set_stage(state, "contact_required")
                return self._result(status="CONTACT_REQUIRED", message=await self._contact_prompt(state), state=state)
        contact["status"] = "complete" if self.contact_agent.is_complete(state) else "incomplete"
        if not self.contact_agent.is_complete(state):
            self._set_stage(state, "contact_required")
            return self._result(status="CONTACT_REQUIRED", message=await self._contact_prompt(state), state=state)
        return await self._continue_after_contact_ready(
            state=state,
            session_id=session_id,
            message_log_id=message_log_id,
        )

    async def _handle_address_change_confirmation(self, *, state: Dict[str, Any], text: str) -> Dict[str, Any]:
        self._set_stage(state, "address_change_confirm")
        return self._result(
            status="ADDRESS_CHANGE_CONFIRM",
            message=(
                "Пока не меняю адрес автоматически. "
                "Напишите, пожалуйста, один адрес для этой заявки или начните отдельную заявку для второго адреса."
            ),
            state=state,
        )

    async def _handle_pre_registration_review(
        self,
        *,
        state: Dict[str, Any],
        text: str,
        user_id: str,
        channel: str,
        session_id: str,
        message_log_id: Optional[int],
        django_user_id: Optional[int],
        source_metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        decision = await self._timed_await(
            "final_review.interpret",
            self.final_review_agent.interpret(
                text=text,
                state=state,
                session_id=session_id,
                message_log_id=message_log_id,
            ),
            {"text_len": len(text or "")},
        )
        state.setdefault("review", {})["last_decision"] = decision
        action = decision.get("action")
        fields = set(decision.get("fields") or [])
        clean_text = decision.get("clean_text") or text
        update_mode = decision.get("mode") or "append"

        if action == "ready_to_register":
            return await self._create_order(
                state=state,
                text=text,
                user_id=user_id,
                channel=channel,
                session_id=session_id,
                message_log_id=message_log_id,
                django_user_id=django_user_id,
                source_metadata=source_metadata,
            )

        if action == "clarify":
            self._set_stage(state, "pre_registration_review")
            return self._result(
                status="PRE_REGISTRATION_REVIEW",
                message=await self._pre_registration_review_message(state),
                state=state,
            )

        if action in {"update_address", "update_multiple"} or "address" in fields:
            address_result = await self._timed_await(
                "address_agent.update_optional_slots",
                self.address_agent.update_optional_slots(
                    state=state,
                    text=clean_text,
                    session_id=session_id,
                    message_log_id=message_log_id,
                ),
                {"source": "pre_registration_review", "text_len": len(clean_text or "")},
            )
            if address_result.get("status") not in {"matched", "skipped"} and not address_result.get("updated"):
                self._set_stage(state, f"address_{address_result.get('status') or 'incomplete'}")
                return self._result(
                    status=(address_result.get("status") or "incomplete").upper(),
                    message=await self._address_followup_message(state, address_result),
                    state=state,
                )
            if address_result.get("apartment_not_found"):
                self._append_address_note_to_problem(
                    state,
                    apartment_number=address_result.get("apartment_number"),
                )
                self._rebuild_problem_text(state)

        if action in {"update_contact", "update_multiple"} or "contact" in fields:
            await self._timed_await(
                "contact_agent.extract",
                self.contact_agent.extract(
                    state=state,
                    text=clean_text,
                    session_id=session_id,
                    message_log_id=message_log_id,
                ),
                {"source": "pre_registration_review", "text_len": len(clean_text or "")},
            )
            if not self.contact_agent.is_complete(state):
                self._set_stage(state, "contact_required")
                return self._result(status="CONTACT_REQUIRED", message=await self._contact_prompt(state), state=state)

        if action in {"update_problem", "update_multiple"} or "problem" in fields:
            if update_mode == "replace":
                problem = state.setdefault("problem", {})
                problem["fragments"] = []
                problem["cleaned_fragments"] = {}
            await self._timed_await(
                "bot_order._record_problem_fragment",
                self._record_problem_fragment(
                    state=state,
                    text=clean_text,
                    use_message_for_order=True,
                    session_id=session_id,
                    message_log_id=message_log_id,
                ),
                {"source": "pre_registration_review", "text_len": len(clean_text or "")},
            )
            self._rebuild_problem_text(state)
            state["classification"] = {"confidence": {}}
            state["service"] = {"is_confirmed_by_user": False}
            return await self._run_service_selection_review(
                state=state,
                session_id=session_id,
                message_log_id=message_log_id,
                review_note="problem_updated",
            )

        self._set_stage(state, "pre_registration_review")
        return self._result(
            status="PRE_REGISTRATION_REVIEW",
            message=await self._pre_registration_review_message(state),
            state=state,
        )

    async def _voice_revision_is_superseded(self, source_metadata: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(source_metadata, dict):
            return False
        revision_info = source_metadata.get("voice_revision")
        if not isinstance(revision_info, dict):
            return False
        session_id = str(revision_info.get("session_id") or "").strip()
        turn_id = str(revision_info.get("turn_id") or "").strip()
        revision = revision_info.get("revision")
        if not session_id or not turn_id or revision is None:
            return False
        try:
            revision = int(revision)
        except (TypeError, ValueError):
            return False

        from message_handler.voice_revision_guard import is_current_voice_turn

        is_current = await sync_to_async(is_current_voice_turn)(
            session_id=session_id,
            turn_id=turn_id,
            revision=revision,
        )
        return not is_current

    async def _run_service_selection_review(
        self,
        *,
        state: Dict[str, Any],
        session_id: str,
        message_log_id: Optional[int],
        review_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._set_stage(state, "service_selection")
        service_result = await self._timed_await(
            "service_agent.select",
            self.service_agent.select(
                state=state,
                session_id=session_id,
                message_log_id=message_log_id,
            ),
            {"txt_prb_len": len(((state.get("problem") or {}).get("txtPrb") or ""))},
        )
        if service_result["status"] != "service_selected":
            self._set_stage(state, service_result["status"])
            return self._result(
                status=service_result["status"].upper(),
                message=service_result["message"],
                state=state,
            )
        self._set_stage(state, "pre_registration_review")
        return self._result(
            status="PRE_REGISTRATION_REVIEW",
            message=await self._pre_registration_review_message(state, review_note=review_note),
            state=state,
            service_id=(state.get("service") or {}).get("service_id"),
            service_name=(state.get("service") or {}).get("service_name"),
        )

    def _address_text_for_turn(self, state: Dict[str, Any], fallback: str) -> str:
        turn = state.get("turn") or {}
        if turn.get("has_address") and (turn.get("address_text") or "").strip():
            return str(turn.get("address_text")).strip()
        return fallback or ""

    def _problem_text_for_turn(self, state: Dict[str, Any], fallback: str) -> str:
        turn = state.get("turn") or {}
        if turn.get("has_problem") and (turn.get("problem_text") or "").strip():
            return str(turn.get("problem_text")).strip()
        return fallback or ""

    def _contact_text_for_turn(self, state: Dict[str, Any], fallback: str) -> str:
        turn = state.get("turn") or {}
        if turn.get("has_contact") and (turn.get("contact_text") or "").strip():
            return str(turn.get("contact_text")).strip()
        return fallback or ""

    def _should_extract_contact(
        self,
        state: Dict[str, Any],
        previous_stage: Optional[str],
        contact_was_complete: bool,
    ) -> bool:
        if contact_was_complete:
            return False
        if previous_stage in {"contact_required", "contact_profile_confirm", "contact_phone_confirm"}:
            return True
        turn = state.get("turn") or {}
        return bool(turn.get("has_contact"))

    def _address_is_locked(self, state: Dict[str, Any]) -> bool:
        local_address = state.get("local_address") or {}
        service_context = state.get("service_context") or {}
        fias_result = state.get("fias_result") or {}
        return bool(
            local_address.get("building_id")
            or service_context.get("service_object_id")
            or fias_result.get("status") == "matched"
        )

    async def _bootstrap_customer_identity(
        self,
        *,
        state: Dict[str, Any],
        user_id: str,
        channel: str,
        django_user_id: Optional[int],
        source_metadata: Dict[str, Any],
    ) -> None:
        api_info = source_metadata.get("api_info") if isinstance(source_metadata.get("api_info"), dict) else {}
        client_phone = (
            source_metadata.get("client_phone")
            or api_info.get("client_phone")
            or api_info.get("nomer")
            or source_metadata.get("nomer")
        )
        normalized_phone = normalize_phone(client_phone)
        telegram_info = source_metadata.get("telegram_info") if isinstance(source_metadata.get("telegram_info"), dict) else {}
        max_info = source_metadata.get("max_info") if isinstance(source_metadata.get("max_info"), dict) else {}
        metadata_username = (
            source_metadata.get("username")
            or source_metadata.get("telegram_username")
            or source_metadata.get("max_username")
            or telegram_info.get("username")
            or telegram_info.get("id")
            or max_info.get("username")
            or max_info.get("user_id")
        )
        identifiers = {
            "id_in_system": django_user_id or (user_id if channel == "web" else None),
            "id_tg": metadata_username if channel == "telegram" else None,
            "id_max": metadata_username if channel in {"max", "maxchat"} else None,
            "telefon": f"+{normalized_phone}" if normalized_phone else "",
        }
        customer_identity = state.setdefault("customer_identity", {})
        customer_identity["identifiers"] = {
            **(customer_identity.get("identifiers") or {}),
            **{key: value for key, value in identifiers.items() if value not in (None, "")},
        }
        contact = state.setdefault("contact", {})
        if normalized_phone and not contact.get("phone"):
            contact["phone"] = f"+{normalized_phone}"
            contact["source_phone"] = f"+{normalized_phone}"
            contact["phone_source"] = "api_client_phone"
        elif normalized_phone:
            contact["source_phone"] = f"+{normalized_phone}"

        if customer_identity.get("lookup_done"):
            return
        lookup_result = await sync_to_async(lookup_known_customer, thread_sensitive=True)(
            customer_identity.get("identifiers") or {}
        )
        customer_identity["lookup_result"] = lookup_result
        customer_identity["lookup_done"] = True
        lookup_contacts = lookup_result.get("contacts") or {}
        lookup_phone = normalize_phone(lookup_contacts.get("telefon"))
        if lookup_result.get("name"):
            contact["candidate_name"] = lookup_result.get("name")
            contact["candidate_source"] = "customer_lookup_db"
        if lookup_phone:
            contact["candidate_phone"] = f"+{lookup_phone}"
            contact.setdefault("source_phone", f"+{lookup_phone}")

    def _has_unconfirmed_profile_contact(self, state: Dict[str, Any]) -> bool:
        contact = state.get("contact") or {}
        return bool(
            contact.get("candidate_name")
            and not contact.get("profile_name_confirmed")
            and not contact.get("name")
        )

    def _profile_contact_confirmation_message(self, state: Dict[str, Any]) -> str:
        contact = state.get("contact") or {}
        name = contact.get("candidate_name") or contact.get("name")
        self._set_last_bot_action(state, "confirm_contact_name")
        first_name = str(name or "").strip().split()[0] if name else ""
        display_name = first_name or name
        return f"Контактным лицом по заявке оставляем вас, {display_name}?"

    def _profile_contact_phone_confirmation_message(self, state: Dict[str, Any]) -> str:
        contact = state.get("contact") or {}
        phone = self._known_contact_phone(contact)
        self._set_last_bot_action(state, "confirm_contact_phone")
        return f"Для связи по заявке использовать номер {phone}?"

    def _known_contact_phone(self, contact: Dict[str, Any]) -> str:
        return (
            contact.get("candidate_phone")
            or contact.get("phone")
            or contact.get("source_phone")
            or ""
        )

    def _needs_contact_phone_confirmation(self, state: Dict[str, Any]) -> bool:
        contact = state.get("contact") or {}
        return bool(self._known_contact_phone(contact) and not contact.get("phone_confirmed"))

    async def _interpret_contact_profile_reply(
        self,
        *,
        state: Dict[str, Any],
        text: str,
        session_id: str,
        message_log_id: Optional[int],
    ) -> Dict[str, Any]:
        contact = state.get("contact") or {}
        prompt = (
            "Ты определяешь, согласен ли житель использовать найденное имя как контактное лицо по заявке. "
            "Не пиши ответ пользователю, верни только JSON.\n"
            f"Найденное имя: {contact.get('candidate_name') or ''}\n"
            f"Ответ жителя: {text or ''}\n"
            "Схема: {\"use_profile\": true|false, \"name\": string|null, \"phone\": string|null, \"clean_text\": string, \"reason\": string}. "
            "Если житель подтверждает найденное имя или отвечает согласием, use_profile=true. "
            "Если он исправляет имя, use_profile=false и заполни name. "
            "На этом шаге не подтверждай телефон: phone=null, даже если ответ похож на согласие."
        )
        result = await self.llm.json_call(
            prompt=prompt,
            session_id=session_id,
            message_id=message_log_id,
            caller_service="BotOrderOrchestrator.contact_profile_confirmation",
            prompt_slug="contact-profile-confirm-runtime",
            max_tokens=220,
            temperature=0.0,
        )
        phone = (result.get("phone") or "").strip() or None
        return {
            "use_profile": bool(result.get("use_profile")),
            "name": (result.get("name") or "").strip() or None,
            "phone": phone,
            "clean_text": (result.get("clean_text") or text or "").strip(),
            "reason": result.get("reason") or "",
        }

    async def _interpret_contact_phone_reply(
        self,
        *,
        state: Dict[str, Any],
        text: str,
        session_id: str,
        message_log_id: Optional[int],
    ) -> Dict[str, Any]:
        contact = state.get("contact") or {}
        known_phone = self._known_contact_phone(contact)
        prompt = (
            "Ты определяешь, согласен ли житель использовать найденный телефон для связи по заявке. "
            "Не пиши ответ пользователю, верни только JSON.\n"
            f"Найденный телефон: {known_phone}\n"
            f"Ответ жителя: {text or ''}\n"
            "Схема: {\"use_known_phone\": true|false, \"phone\": string|null, \"clean_text\": string, \"reason\": string}. "
            "Если житель соглашается, говорит 'да', 'по этому номеру', 'на этот номер', use_known_phone=true. "
            "Если он называет другой телефон, use_known_phone=false и заполни phone. "
            "Если ответа на телефон нет, use_known_phone=false и phone=null."
        )
        result = await self.llm.json_call(
            prompt=prompt,
            session_id=session_id,
            message_id=message_log_id,
            caller_service="BotOrderOrchestrator.contact_phone_confirmation",
            prompt_slug="contact-phone-confirm-runtime",
            max_tokens=180,
            temperature=0.0,
        )
        return {
            "use_known_phone": bool(result.get("use_known_phone")),
            "phone": (result.get("phone") or "").strip() or None,
            "clean_text": (result.get("clean_text") or text or "").strip(),
            "reason": result.get("reason") or "",
        }

    async def _continue_after_contact_ready(
        self,
        *,
        state: Dict[str, Any],
        session_id: str,
        message_log_id: Optional[int],
        contact_extraction: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if self._problem_looks_empty_or_address_only(state):
            self._set_stage(state, "problem_required")
            return self._result(
                status="PROBLEM_REQUIRED",
                message=await self._serviced_address_problem_prompt(state),
                state=state,
                contact_extraction=contact_extraction,
            )
        return await self._run_service_selection_review(
            state=state,
            session_id=session_id,
            message_log_id=message_log_id,
        )

    def _is_empty_dialog(self, previous_stage: Optional[str], state: Dict[str, Any]) -> bool:
        if previous_stage not in (None, "", "new"):
            return False
        address = state.get("address_input") or {}
        problem = state.get("problem") or {}
        contact = state.get("contact") or {}
        service_context = state.get("service_context") or {}
        return not any(
            [
                (problem.get("txtPrb") or "").strip(),
                address.get("raw_text"),
                address.get("city"),
                address.get("street"),
                address.get("house"),
                self._has_user_supplied_contact(contact),
                service_context.get("service_object_id"),
            ]
        )

    def _has_user_supplied_contact(self, contact: Dict[str, Any]) -> bool:
        if (contact.get("name") or "").strip():
            return True
        phone = (contact.get("phone") or "").strip()
        if not phone:
            return False
        if contact.get("profile_confirmed"):
            return True
        if contact.get("last_slot_extraction"):
            return True
        return contact.get("phone_source") not in {"api_client_phone"}

    def _rebuild_problem_text(self, state: Dict[str, Any]) -> None:
        problem = state.setdefault("problem", {})
        raw_fragments = problem.get("fragments") or []
        if not raw_fragments and isinstance(problem.get("cleaned_fragments"), dict):
            raw_fragments = list((problem.get("cleaned_fragments") or {}).values())
        fragments = []
        seen = set()
        for fragment in raw_fragments:
            fragment = str(fragment or "").strip()
            if not fragment:
                continue
            key = fragment.lower().replace("ё", "е")
            if key in seen:
                continue
            seen.add(key)
            fragments.append(fragment)
        txt_prb = ", ".join(fragments)
        previous = (problem.get("txtPrb") or "").strip()
        problem.update(
            {
                "txtPrb": txt_prb,
                "new_info": txt_prb if txt_prb != previous else "",
                "is_meaningful": bool(txt_prb),
            }
        )

    async def _record_problem_fragment(
        self,
        *,
        state: Dict[str, Any],
        text: str,
        use_message_for_order: bool,
        session_id: str,
        message_log_id: Optional[int],
    ) -> None:
        problem = state.setdefault("problem", {})
        if not use_message_for_order or is_greeting_only(text):
            self._append_unique(problem.setdefault("ignored_messages", []), text)
            return
        turn = state.get("turn") or {}
        if turn and not turn.get("has_problem") and (
            turn.get("has_address") or turn.get("has_contact") or turn.get("answers_current_question")
        ):
            self._append_unique(problem.setdefault("ignored_messages", []), text)
            return
        turn_problem_text = (turn.get("problem_text") or "").strip() if turn.get("has_problem") else ""
        if turn_problem_text:
            address_text = (turn.get("address_text") or "").strip()
            if not address_text and not self._address_is_locked(state):
                address_text = self._problem_context_address_text(state)
            problem_source_text = turn_problem_text if address_text else text
            decision = await self.problem_agent.extract_fragment(
                current_txt_prb=(problem.get("txtPrb") or ""),
                user_message=problem_source_text,
                address_text=address_text,
                session_id=session_id,
                message_id=message_log_id,
            )
            clean_fragment = (decision.get("clean_fragment") or "").strip()
            if decision.get("is_problem_detail") and clean_fragment:
                problem["last_fragment_decision"] = decision
                self._append_unique(problem.setdefault("source_messages", []), text)
                self._append_unique(problem.setdefault("fragments", []), clean_fragment)
                problem.setdefault("cleaned_fragments", {})[str(text or "")] = clean_fragment
                return
            problem["last_fragment_decision"] = {
                "is_problem_detail": True,
                "clean_fragment": turn_problem_text,
                "reason": "turn_splitter_problem_text",
                "raw": turn.get("raw"),
            }
            self._append_unique(problem.setdefault("source_messages", []), text)
            self._append_unique(problem.setdefault("fragments", []), turn_problem_text)
            problem.setdefault("cleaned_fragments", {})[str(text or "")] = turn_problem_text
            return
        if self._message_is_address_only(state, text):
            self._append_unique(problem.setdefault("ignored_messages", []), text)
            problem["last_fragment_decision"] = {
                "is_problem_detail": False,
                "clean_fragment": "",
                "reason": "address_only_message",
            }
            return

        decision = await self.problem_agent.extract_fragment(
            current_txt_prb=(problem.get("txtPrb") or ""),
            user_message=text,
            address_text=self._problem_context_address_text(state),
            session_id=session_id,
            message_id=message_log_id,
        )
        problem["last_fragment_decision"] = decision
        clean_fragment = (decision.get("clean_fragment") or "").strip()
        if not decision.get("is_problem_detail") or not clean_fragment:
            self._append_unique(problem.setdefault("ignored_messages", []), text)
            return

        self._append_unique(problem.setdefault("source_messages", []), text)
        self._append_unique(problem.setdefault("fragments", []), clean_fragment)
        problem.setdefault("cleaned_fragments", {})[str(text or "")] = clean_fragment

    def _problem_context_address_text(self, state: Dict[str, Any]) -> str:
        address = state.get("address_input") or {}
        parts = [
            address.get("normalized_text"),
            address.get("raw_text"),
            address.get("city"),
            address.get("street"),
            address.get("house"),
            address.get("flat"),
        ]
        return ", ".join(str(part) for part in parts if part)

    def _message_is_address_only(self, state: Dict[str, Any], text: str) -> bool:
        address = state.get("address_input") or {}
        slot_result = address.get("last_slot_extraction") or {}
        if not slot_result.get("is_address_message"):
            return False

        problem_words = [
            token
            for token in self._text_tokens(text)
            if token not in self._address_tokens_from_state(address)
        ]
        return not problem_words

    def _text_tokens(self, text: str) -> list:
        return re.findall(r"[a-zа-яё0-9]+", (text or "").lower().replace("ё", "е"))

    def _address_tokens_from_state(self, address: Dict[str, Any]) -> set:
        allowed = set()
        for key in ("city", "settlement", "street", "house", "flat"):
            allowed.update(self._text_tokens(str(address.get(key) or "")))
        allowed.update(
            {
                "да",
                "ага",
                "угу",
                "г",
                "город",
                "ул",
                "улица",
                "д",
                "дом",
                "кв",
                "квартира",
                "пом",
                "помещение",
                "корпус",
                "корп",
                "строение",
                "стр",
                "литера",
                "лит",
                "ноль",
                "один",
                "одна",
                "одно",
                "два",
                "две",
                "три",
                "четыре",
                "пять",
                "шесть",
                "семь",
                "восемь",
                "девять",
                "десять",
                "одиннадцать",
                "двенадцать",
                "тринадцать",
                "четырнадцать",
                "пятнадцать",
                "шестнадцать",
                "семнадцать",
                "восемнадцать",
                "девятнадцать",
                "двадцать",
                "тридцать",
                "сорок",
                "пятьдесят",
                "шестьдесят",
                "семьдесят",
                "восемьдесят",
                "девяносто",
                "сто",
            }
        )
        return allowed

    def _append_unique(self, target: list, value: Any) -> None:
        if value in (None, ""):
            return
        if str(value or "") in {str(item or "") for item in target}:
            return
        target.append(value)

    def _append_address_note_to_problem(self, state: Dict[str, Any], *, apartment_number: Any) -> None:
        if apartment_number in (None, ""):
            return
        note = f"Дополнительная информация по адресу: квартира {apartment_number}"
        problem = state.setdefault("problem", {})
        self._append_unique(problem.setdefault("address_notes", []), note)
        self._append_unique(problem.setdefault("source_messages", []), note)
        self._append_unique(problem.setdefault("fragments", []), note)
        problem.setdefault("cleaned_fragments", {})[note] = note

    def _address_signature(self, state: Dict[str, Any]) -> tuple:
        address = state.get("address_input") or {}
        local_address = state.get("local_address") or {}
        service_context = state.get("service_context") or {}
        return (
            address.get("region"),
            address.get("city"),
            address.get("settlement"),
            address.get("street"),
            address.get("house"),
            address.get("building"),
            address.get("flat"),
            address.get("fias_street_guid"),
            address.get("fias_house_guid"),
            local_address.get("building_id"),
            service_context.get("service_object_id"),
        )

    async def _with_captured_info_ack(self, state: Dict[str, Any], next_question: str) -> str:
        problem = state.setdefault("problem", {})
        new_info = str(problem.get("new_info") or "").strip()
        if not new_info or problem.get("last_acknowledged_new_info") == new_info:
            return next_question

        prompt = (
            "Составь короткий ответ диспетчера ЖКХ жильцу.\n"
            "Нужно: подтвердить, что полезную информацию зафиксировали, и сразу задать следующий вопрос.\n"
            "Не придумывай факты. Не пересказывай всю заявку. Не упоминай внутренние правила. До двух коротких предложений.\n"
            f"Зафиксировано: {new_info}\n"
            f"Следующий вопрос: {next_question}\n"
            "Верни только текст ответа."
        )
        try:
            reply = await self.llm.text_call(
                prompt=prompt,
                session_id=(state.get("dialog") or {}).get("session_id"),
                message_id=None,
                caller_service="BotOrderOrchestrator.followup_ack",
                prompt_slug="followup-ack-runtime",
                max_tokens=100,
                temperature=0.2,
            )
        except Exception:
            reply = ""

        problem["last_acknowledged_new_info"] = new_info
        reply = (reply or "").strip()
        if not reply or not self._reply_preserves_info(reply, new_info):
            return f"Приняла: {new_info}. {next_question}"
        return reply

    async def _address_followup_message(self, state: Dict[str, Any], address_result: Dict[str, Any]) -> str:
        status = address_result.get("status")
        default_message = address_result.get("message") or "По какому адресу хотите оставить обращение?"
        has_problem = bool(((state.get("problem") or {}).get("txtPrb") or "").strip())
        address = state.get("address_input") or {}

        if status == "not_serviced":
            return default_message

        if status == "not_found":
            return await self._with_captured_info_ack(
                state,
                "Адрес пока не нашла. Проверьте, пожалуйста, город, улицу и номер дома.",
            )

        city = bool(address.get("city"))
        street = bool(address.get("street"))
        house = bool(address.get("house"))
        last_fragment_decision = (state.get("problem") or {}).get("last_fragment_decision") or {}
        last_message_was_not_problem = last_fragment_decision and not last_fragment_decision.get("is_problem_detail")

        if not city and not street and not house:
            if last_message_was_not_problem:
                return await self._with_captured_info_ack(state, "Чтобы оформить обращение, сначала уточним адрес.")
            if has_problem:
                return await self._with_captured_info_ack(state, "По какому адресу хотите оставить обращение?")
            return await self._with_captured_info_ack(state, "По какому адресу хотите оставить обращение?")

        if city and not street and not house:
            return await self._with_captured_info_ack(state, "Подскажите улицу и номер дома.")
        if street and not city and not house:
            return await self._with_captured_info_ack(state, "Подскажите город и номер дома.")
        if house and not city and not street:
            return await self._with_captured_info_ack(state, "Подскажите город и улицу.")
        if city and street and not house:
            return await self._with_captured_info_ack(state, "Теперь нужен номер дома." if has_problem else "Подскажите номер дома.")
        if city and house and not street:
            return await self._with_captured_info_ack(state, "Теперь нужна улица." if has_problem else "Подскажите улицу.")
        if street and house and not city:
            return await self._with_captured_info_ack(state, "Теперь нужно уточнить город." if has_problem else "Уточните населенный пункт.")

        return await self._with_captured_info_ack(state, default_message)

    def _guard_redirect_message(self, state: Dict[str, Any]) -> str:
        last_question = ((state.get("dialog_context") or {}).get("last_bot_question") or "").strip()
        if last_question:
            return f"Понимаю, что это раздражает. Заявку не начинаю заново. {last_question}"
        return "Понимаю, что это раздражает. Продолжим оформление заявки."

    def _not_serviced_message(self, state: Dict[str, Any]) -> str:
        address = state.get("address_input") or {}
        city = (address.get("city") or address.get("settlement") or "").strip()
        street = (address.get("street") or "").strip()
        house = (address.get("house") or "").strip()
        parts = []
        if city:
            parts.append(city)
        street_house = " ".join(part for part in [street, house] if part).strip()
        if street_house:
            parts.append(street_house)
        address_text = ", ".join(parts) or (address.get("normalized_text") or address.get("raw_text") or "Этот дом")
        return f"{address_text} - нами не обслуживается."

    def _problem_looks_empty_or_address_only(self, state: Dict[str, Any]) -> bool:
        txt = ((state.get("problem") or {}).get("txtPrb") or "").strip()
        return not txt

    def _set_stage(self, state: Dict[str, Any], stage: str) -> None:
        if self.tracer:
            if self._active_stage:
                self.tracer.end(self._active_stage)
            self._active_stage = f"bot_order.{stage}"
            self.tracer.start(self._active_stage)
        state.setdefault("control", {})["stage"] = stage

    def _set_last_bot_action(self, state: Dict[str, Any], action: str, **details) -> None:
        context = state.setdefault("dialog_context", {})
        context["last_bot_action"] = action
        if details:
            context["last_bot_action_details"] = details

    async def _timed_await(self, name: str, awaitable, metadata: Optional[Dict[str, Any]] = None):
        """Measure one awaited diagnostic step without changing control flow."""
        if not self.tracer:
            return await awaitable
        self.tracer.start(name, metadata or {})
        try:
            result = await awaitable
        except Exception as exc:
            self.tracer.end(name, error=exc)
            raise
        self.tracer.end(name, result=result)
        return result

    def _result(self, *, status: str, message: str, state: Dict[str, Any], **extra) -> Dict[str, Any]:
        if self.tracer and self._active_stage:
            self.tracer.end(self._active_stage, result={"status": status})
            self._active_stage = None
        message = self._apply_guard_prefix(state, message)
        if message:
            state.setdefault("dialog_context", {})["last_bot_question"] = message
        control = state.get("control") or {}
        dialog_finished = bool(control.get("is_finished"))
        finish_reason = control.get("finish_reason")
        metadata = {
            "txtPrb": (state.get("problem") or {}).get("txtPrb"),
            "established_filters": self._established_filters(state),
            "state_snapshot": compact_state(state),
            "fias_log_ids": (state.get("trace") or {}).get("current_fias_log_ids") or [],
            "dialog_finished": dialog_finished,
            "finish_reason": finish_reason,
            "close_session": dialog_finished,
            "bot_order_orchestrator": {
                "stage": control.get("stage"),
            },
            "contact": state.get("contact") or {},
        }
        return {
            "status": status,
            "message": message,
            "response": message,
            "service_id": extra.get("service_id"),
            "service_name": extra.get("service_name"),
            "work_order_id": (extra.get("order_result") or {}).get("work_order_id"),
            "work_order_no": (extra.get("order_result") or {}).get("work_order_no"),
            "dialog_finished": dialog_finished,
            "finish_reason": finish_reason,
            "close_session": dialog_finished,
            "_metadata": metadata,
            **extra,
        }

    def _apply_guard_prefix(self, state: Dict[str, Any], message: str) -> str:
        prefix = ((state.get("guard") or {}).get("reply_prefix") or "").strip()
        if not prefix or not message:
            return message
        if message.startswith(prefix):
            return message
        return f"{prefix} {message}"

    async def _serviced_address_problem_prompt(self, state: Dict[str, Any]) -> str:
        service_context = state.setdefault("service_context", {})
        if service_context.get("service_announcement_sent"):
            return "Расскажите, что произошло."
        company_name = await self._company_name((state.get("service_context") or {}).get("company_id"))
        if company_name:
            service_context["service_announcement_sent"] = True
            return f"Адрес в зоне обслуживания {company_name}. Расскажите, что произошло."
        return "Адрес в зоне обслуживания. Расскажите, что произошло."

    async def _contact_prompt(self, state: Dict[str, Any]) -> str:
        question = self.contact_agent.question(state)
        missing = set(self.contact_agent.missing_fields(state))
        if missing == {"name", "phone"}:
            service_context = state.setdefault("service_context", {})
            if service_context.get("service_announcement_sent"):
                return await self._with_captured_info_ack(state, question)
            company_name = await self._company_name((state.get("service_context") or {}).get("company_id"))
            if company_name:
                service_context["service_announcement_sent"] = True
                return await self._with_captured_info_ack(state, f"Адрес в зоне обслуживания {company_name}. {question}")
        return await self._with_captured_info_ack(state, question)

    async def _pre_registration_review_message(self, state: Dict[str, Any], review_note: Optional[str] = None) -> str:
        self._set_last_bot_action(
            state,
            "pre_registration_review_additions",
            no_means="ready_to_register",
            expected_reply="confirm_or_add_changes",
        )
        address_text = self._review_address_text(state)
        problem_text = ((state.get("problem") or {}).get("txtPrb") or "").strip() or "не указано"
        contact = state.get("contact") or {}
        name = (contact.get("name") or "").strip() or "не указано"
        phone = (contact.get("phone") or contact.get("source_phone") or "").strip()
        contact_method = phone or "не указан"
        if review_note == "problem_updated":
            return f"Принято, обновила описание проблемы: {problem_text}. Можно регистрировать заявку или еще что-то поправить?"
        flat_hint = ""
        address_notes = (state.get("problem") or {}).get("address_notes") or []
        has_apartment_note = any("квартир" in str(note or "").lower() for note in address_notes)
        if (
            not (state.get("address_input") or {}).get("flat")
            and not has_apartment_note
            and self._should_prompt_for_flat(state)
        ):
            flat_hint = " Например, квартиру, если это важно."
        return await self._compose_final_review_message(
            state=state,
            address_text=address_text,
            problem_text=problem_text,
            name=name,
            contact_method=contact_method,
            flat_hint=flat_hint,
        )

    async def _compose_final_review_message(
        self,
        *,
        state: Dict[str, Any],
        address_text: str,
        problem_text: str,
        name: str,
        contact_method: str,
        flat_hint: str,
    ) -> str:
        prompt = (
            "Составь короткую финальную проверку заявки ЖКХ перед регистрацией.\n"
            "Обязательно сохрани факты без искажений. Не придумывай новые детали. Не начинай с фразы \"Мне кажется\".\n"
            "В конце спроси, можно ли регистрировать заявку или нужно что-то поправить.\n"
            "Если подсказка пустая, не спрашивай про квартиру.\n"
            f"Адрес: {address_text}\n"
            f"Проблема: {problem_text}\n"
            f"Контакт: {name}\n"
            f"Способ связи: {contact_method}\n"
            f"Дополнительная подсказка: {flat_hint}\n"
            "Верни только текст ответа."
        )
        fallback = (
            "Перед регистрацией проверим данные: "
            f"адрес: {address_text}; описание проблемы: {problem_text}; "
            f"контакт: {name}; способ связи: {contact_method}. "
            f"Можно регистрировать заявку или что-то поправить?{flat_hint}"
        )
        try:
            reply = await self.llm.text_call(
                prompt=prompt,
                session_id=(state.get("dialog") or {}).get("session_id"),
                message_id=None,
                caller_service="BotOrderOrchestrator.final_review_message",
                prompt_slug="final-review-message-runtime",
                max_tokens=180,
                temperature=0.2,
            )
        except Exception:
            reply = ""
        reply = (reply or "").strip()
        if not self._final_review_reply_is_valid(
            reply=reply,
            problem_text=problem_text,
            contact_method=contact_method,
        ):
            return fallback
        return reply

    def _reply_preserves_info(self, reply: str, info: str) -> bool:
        info_tokens = [token for token in self._text_tokens(info) if len(token) >= 4]
        if not info_tokens:
            return True
        reply_tokens = set(self._text_tokens(reply))
        overlap = [token for token in info_tokens if token in reply_tokens]
        return len(overlap) >= min(2, len(set(info_tokens)))

    def _final_review_reply_is_valid(self, *, reply: str, problem_text: str, contact_method: str) -> bool:
        if not reply:
            return False
        if "\n-" in reply or reply.lstrip().startswith("-"):
            return False
        normalized_reply = self._normalize_text(reply)
        if self._normalize_text(problem_text) not in normalized_reply:
            return False
        phone_digits = re.sub(r"\D+", "", contact_method or "")
        reply_digits = re.sub(r"\D+", "", reply or "")
        if phone_digits and phone_digits not in reply_digits and phone_digits[-10:] not in reply_digits:
            return False
        return True

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").lower().replace("ё", "е")).strip()

    def _should_prompt_for_flat(self, state: Dict[str, Any]) -> bool:
        classification = state.get("classification") or {}
        if str(classification.get("localization_name") or "").lower().replace("ё", "е") == "общедомовое":
            return False
        txt_prb = ((state.get("problem") or {}).get("txtPrb") or "").lower().replace("ё", "е")
        common_places = ("подъезд", "подвал", "двор", "вход", "лестниц", "лифт", "крыша", "фасад")
        return not any(place in txt_prb for place in common_places)

    def _review_address_text(self, state: Dict[str, Any]) -> str:
        address = state.get("address_input") or {}
        if address.get("normalized_text"):
            base = str(address.get("normalized_text"))
        else:
            parts = [
                address.get("city") or address.get("settlement"),
                address.get("street"),
                address.get("house"),
            ]
            base = ", ".join(str(part) for part in parts if part)
        if address.get("flat") and str(address.get("flat")) not in base:
            base = f"{base}, квартира {address.get('flat')}" if base else f"квартира {address.get('flat')}"
        return base or "не указан"

    async def _company_name(self, company_id: Optional[int]) -> Optional[str]:
        if not company_id:
            return None

        def load_sync():
            try:
                from nsi.models import Company

                company = Company.objects.filter(pk=company_id).first()
                return company.name if company else None
            except Exception:
                return None

        return await sync_to_async(load_sync)()

    def _established_filters(self, state: Dict[str, Any]) -> Dict[str, Any]:
        classification = state.get("classification") or {}
        confidence = classification.get("confidence") or {}
        return {
            "incident_type": {
                "id": classification.get("service_type_id"),
                "value": classification.get("service_type_name"),
                "confidence": confidence.get("service_type"),
            },
            "location_type": {
                "id": classification.get("localization_id"),
                "value": classification.get("localization_name"),
                "confidence": confidence.get("localization"),
            },
            "category": {
                "id": classification.get("category_id"),
                "value": classification.get("category_name"),
                "confidence": confidence.get("category"),
            },
        }
