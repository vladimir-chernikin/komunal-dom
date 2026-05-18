from typing import Any, Dict, Optional

from asgiref.sync import sync_to_async

from work_orders.chat_order_service import ChatOrderService


class OrderCreationAgent:
    def __init__(self):
        self.chat_order_service = ChatOrderService()

    async def create(
        self,
        *,
        state: Dict[str, Any],
        original_text: str,
        channel: str,
        session_id: str,
        user_id: str,
        django_user_id: Optional[int],
        message_log_id: Optional[int],
        source_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        missing = self._missing_fields(state)
        if missing:
            return {
                "created": False,
                "message": "Не хватает данных для заявки: " + ", ".join(missing),
                "missing": missing,
            }

        result = await sync_to_async(self.chat_order_service.create_from_chat)(
            service_result=self._service_result(state),
            order_context=self._order_context(state),
            original_text=original_text,
            channel=channel,
            session_id=session_id,
            user_id=user_id,
            django_user_id=django_user_id,
            message_log_id=message_log_id,
            source_metadata=source_metadata or {},
        )
        if result.get("created"):
            state.setdefault("order", {}).update(
                {
                    "work_order_id": result.get("work_order_id"),
                    "order_number": result.get("work_order_no"),
                    "status": "created",
                }
            )
            state.setdefault("service", {})["is_confirmed_by_user"] = True
            state.setdefault("control", {}).update(
                {
                    "is_finished": True,
                    "finish_reason": "order_created",
                    "stage": "finished",
                    "next_action": None,
                }
            )
        return result

    def _missing_fields(self, state: Dict[str, Any]):
        required = {
            "txtPrb": (state.get("problem") or {}).get("txtPrb"),
            "building_id": (state.get("local_address") or {}).get("building_id"),
            "service_object_id": (state.get("service_context") or {}).get("service_object_id"),
            "company_id": (state.get("service_context") or {}).get("company_id"),
            "contact_name": (state.get("contact") or {}).get("name"),
            "contact_phone": (state.get("contact") or {}).get("phone"),
            "service_id": (state.get("service") or {}).get("service_id"),
            "service_type_id": (state.get("classification") or {}).get("service_type_id"),
            "localization_id": (state.get("classification") or {}).get("localization_id"),
            "category_id": (state.get("classification") or {}).get("category_id"),
        }
        return [key for key, value in required.items() if not value]

    def _service_result(self, state: Dict[str, Any]) -> Dict[str, Any]:
        classification = state.get("classification") or {}
        service = state.get("service") or {}
        return {
            "status": "SUCCESS",
            "service_id": service.get("service_id"),
            "service_name": service.get("service_name"),
            "confidence": min((classification.get("confidence") or {}).values() or [0.8]),
            "_metadata": {
                "txtPrb": (state.get("problem") or {}).get("txtPrb"),
                "established_filters": {
                    "incident_type": {
                        "id": classification.get("service_type_id"),
                        "value": classification.get("service_type_name"),
                    },
                    "location_type": {
                        "id": classification.get("localization_id"),
                        "value": classification.get("localization_name"),
                    },
                    "category": {
                        "id": classification.get("category_id"),
                        "value": classification.get("category_name"),
                    },
                },
                "state_snapshot": state,
            },
        }

    def _order_context(self, state: Dict[str, Any]) -> Dict[str, Any]:
        address = state.get("address_input") or {}
        local_address = state.get("local_address") or {}
        service_context = state.get("service_context") or {}
        fias = state.get("fias_result") or {}
        contact = state.get("contact") or {}
        return {
            "contact": {
                "name": contact.get("name"),
                "phone": contact.get("phone"),
            },
            "address_string": address.get("normalized_text") or address.get("raw_text"),
            "address_components": {
                "region": address.get("region"),
                "city": address.get("city"),
                "street": address.get("street"),
                "house_number": address.get("house"),
                "apartment_number": address.get("flat"),
            },
            "address_validation": {
                "found": service_context.get("service_status") == "serviced",
                "serviced": service_context.get("service_status") == "serviced",
                "building_id": local_address.get("building_id"),
                "unit_id": local_address.get("unit_id"),
                "service_object_id": service_context.get("service_object_id"),
                "address_full": fias.get("normalized_address") or address.get("normalized_text"),
                "fias_object_guid": fias.get("fias_house_guid"),
                "street_fias_guid": fias.get("fias_street_guid"),
                "house_number": local_address.get("house_number_normalized") or address.get("house"),
                "match_status": "matched",
                "source": local_address.get("match_source") or "fias",
            },
            "state_snapshot": state,
        }
