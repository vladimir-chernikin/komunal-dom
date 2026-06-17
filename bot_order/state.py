import copy
import re
from typing import Any, Dict, Optional

from asgiref.sync import sync_to_async

from .utils import safe_truncate


STATE_SCHEMA_VERSION = "bot_order_state.v1"


def new_state(*, session_id: str, user_id: str, channel: str, message_id: Optional[str] = None) -> Dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "dialog": {
            "dialog_id": None,
            "session_id": session_id,
            "channel": channel,
            "user_id": str(user_id) if user_id is not None else None,
            "chat_id": None,
            "message_id": message_id,
        },
        "message": {
            "current_text": "",
            "first_user_text": "",
            "received_at": None,
        },
        "problem": {
            "txtPrb": "",
            "new_info": "",
            "is_meaningful": False,
            "source_messages": [],
        },
        "guard": {
            "allowed": True,
            "risk_code": None,
            "safe_reply": None,
            "continue_order_flow": True,
        },
        "address_input": {
            "raw_text": "",
            "normalized_text": "",
            "region": None,
            "city": None,
            "street": None,
            "house": None,
            "building": None,
            "corpus": None,
            "structure": None,
            "letter": None,
            "flat": None,
        },
        "fias_result": {
            "status": "unknown",
            "normalized_address": None,
            "fias_street_guid": None,
            "fias_house_guid": None,
            "raw_ref": None,
            "fias_log_id": None,
            "fias_log_ids": [],
        },
        "local_address": {
            "building_id": None,
            "unit_id": None,
            "match_source": None,
            "match_confidence": 0,
            "house_number_normalized": None,
        },
        "service_context": {
            "service_object_id": None,
            "company_id": None,
            "service_period_id": None,
            "service_status": "unknown",
            "service_status_reason": None,
        },
        "contact": {
            "name": None,
            "phone": None,
            "source_phone": None,
            "candidate_name": None,
            "candidate_phone": None,
            "candidate_source": None,
            "status": "unknown",
            "last_slot_extraction": None,
        },
        "customer_identity": {
            "identifiers": {},
            "lookup_result": None,
            "lookup_done": False,
        },
        "classification": {
            "service_type_id": None,
            "service_type_name": None,
            "localization_id": None,
            "localization_name": None,
            "category_id": None,
            "category_name": None,
            "confidence": {},
        },
        "service": {
            "service_id": None,
            "service_name": None,
            "scenario_name": None,
            "is_confirmed_by_user": False,
        },
        "order": {
            "work_order_id": None,
            "order_number": None,
            "status": "not_created",
            "created_at": None,
        },
        "questions": {
            "items": [],
            "attempts_by_stage": {},
        },
        "trace": {
            "step_timings": [],
            "prompt_slugs": [],
            "llm_request_ids": [],
            "raw_tool_refs": [],
        },
        "control": {
            "stage": "new",
            "next_action": "ingress_normalize",
            "is_finished": False,
            "finish_reason": None,
        },
    }


def compact_state(state: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = copy.deepcopy(state)
    return safe_truncate(snapshot, limit=3000)


class StateStore:
    """State persistence through dialog_logs.metadata.state_snapshot."""

    async def load(self, *, session_id: str, user_id: str, channel: str, message_id: Optional[str]) -> Dict[str, Any]:
        state = await sync_to_async(self._load_sync)(session_id)
        if not state or state.get("schema_version") != STATE_SCHEMA_VERSION:
            state = new_state(session_id=session_id, user_id=user_id, channel=channel, message_id=message_id)
        if state.get("control", {}).get("is_finished"):
            state = new_state(session_id=session_id, user_id=user_id, channel=channel, message_id=message_id)
        self._sanitize_loaded_state(state)
        state.setdefault("dialog", {})
        state["dialog"].update({"session_id": session_id, "channel": channel, "user_id": str(user_id), "message_id": message_id})
        return state

    def _sanitize_loaded_state(self, state: Dict[str, Any]) -> None:
        address = state.setdefault("address_input", {})
        has_house_only = (
            address.get("house")
            and not any(address.get(key) for key in ("region", "city", "settlement", "street"))
        )
        raw_text = address.get("raw_text") or ""
        explicit_house = bool(re.search(r"\b(?:д\.?|дом)\s*\d+", raw_text, flags=re.IGNORECASE))
        if not has_house_only or explicit_house:
            return

        rejected_raw_text = raw_text
        address["house"] = None
        address["flat"] = None
        if not any(address.get(key) for key in ("region", "city", "settlement", "street", "house", "flat")):
            address["raw_text"] = ""
            address["normalized_text"] = ""

        local_address = state.setdefault("local_address", {})
        local_address["house_number_normalized"] = None

        if rejected_raw_text:
            problem = state.setdefault("problem", {})
            source_messages = {str(item or "") for item in (problem.get("source_messages") or [])}
            if rejected_raw_text in source_messages:
                ignored = problem.setdefault("ignored_messages", [])
                if rejected_raw_text not in ignored:
                    ignored.append(rejected_raw_text)

    def _load_sync(self, session_id: str) -> Optional[Dict[str, Any]]:
        if not session_id:
            return None
        try:
            from message_handler.models import MessageLog

            messages = MessageLog.objects.filter(session_id=session_id).order_by("-timestamp")[:20]
            for message in messages:
                metadata = message.metadata or {}
                if not isinstance(metadata, dict):
                    continue
                snapshot = metadata.get("state_snapshot")
                if isinstance(snapshot, dict):
                    return snapshot
                service_result = metadata.get("service_result")
                if isinstance(service_result, dict):
                    nested = service_result.get("_metadata", {}).get("state_snapshot")
                    if isinstance(nested, dict):
                        return nested
        except Exception:
            return None
        return None

    async def save_to_message(self, *, message_log_id: Optional[int], state: Dict[str, Any], extra_metadata: Optional[Dict[str, Any]] = None) -> None:
        if not message_log_id:
            return
        await sync_to_async(self._save_to_message_sync)(message_log_id, state, extra_metadata or {})

    def _save_to_message_sync(self, message_log_id: int, state: Dict[str, Any], extra_metadata: Dict[str, Any]) -> None:
        from message_handler.models import MessageLog

        message = MessageLog.objects.filter(pk=message_log_id).first()
        if not message:
            return
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        metadata.update(extra_metadata)
        metadata["state_snapshot"] = compact_state(state)
        message.metadata = metadata
        message.save(update_fields=["metadata"])
