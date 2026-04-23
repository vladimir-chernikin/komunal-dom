import logging
from typing import Any, Dict, Optional, Tuple

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from portal.models import ServiceObject, ServicesCatalog
from work_orders.chat_intake import ChatIntakePayloadBuilder, ServiceObjectCompanyResolver
from work_orders.models import (
    CompanyRouteMapping,
    WorkOrder,
    WorkOrderEventLog,
    WorkOrderStatusHistory,
    WorkOrderStatusRef,
)
from work_orders.workflow import build_sla_rows

logger = logging.getLogger(__name__)
User = get_user_model()


class ChatIntakeService:
    "Создает промежуточный JSON и реальную заявку из чат-диалога."

    def __init__(self):
        self.payload_builder = ChatIntakePayloadBuilder()
        self.company_resolver = ServiceObjectCompanyResolver()

    def build_intermediate_payload(
        self,
        *,
        service_result: Dict[str, Any],
        intake_context: Dict[str, Any],
        original_text: str,
        channel: str,
        session_id: str,
        user_id: str,
        django_user_id: Optional[int],
        message_log_id: Optional[int],
        source_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.payload_builder.build(
            service_result=service_result,
            intake_context=intake_context,
            original_text=original_text,
            channel=channel,
            session_id=session_id,
            user_id=user_id,
            django_user_id=django_user_id,
            message_log_id=message_log_id,
            source_metadata=source_metadata,
        )

    def create_from_chat(
        self,
        *,
        service_result: Dict[str, Any],
        intake_context: Dict[str, Any],
        original_text: str,
        channel: str,
        session_id: str,
        user_id: str,
        django_user_id: Optional[int],
        message_log_id: Optional[int],
        external_message_id: Optional[str] = None,
        source_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = self.build_intermediate_payload(
            service_result=service_result,
            intake_context=intake_context,
            original_text=original_text,
            channel=channel,
            session_id=session_id,
            user_id=user_id,
            django_user_id=django_user_id,
            message_log_id=message_log_id,
            source_metadata=source_metadata,
        )

        if not payload["address"].get("service_object_id"):
            payload["decision"]["can_create_work_order"] = False
            payload["decision"]["reason_if_blocked"] = "Не удалось определить объект обслуживания по адресу"
            return {
                "created": False,
                "message": "Нужен корректный обслуживаемый адрес, иначе заявку создать нельзя.",
                "payload": payload,
            }

        company, resolution_source, service_period_id = self._resolve_company(payload)
        if company is None:
            payload["decision"]["can_create_work_order"] = False
            payload["decision"]["reason_if_blocked"] = "Не удалось определить компанию для объекта на текущую дату"
            return {
                "created": False,
                "message": "Адрес определился, но для объекта не найден активный период обслуживания.",
                "payload": payload,
            }

        payload["meta"]["company_resolution"] = resolution_source
        payload["meta"]["company_service_period_id"] = service_period_id

        department = self._resolve_department(payload["classification"]["service_id"], company.id)
        if department is None:
            payload["decision"]["can_create_work_order"] = False
            payload["decision"]["reason_if_blocked"] = "Для компании не настроен маршрут обработки услуги"
            return {
                "created": False,
                "message": "Для этого объекта еще не настроен маршрут обработки заявки.",
                "payload": payload,
            }

        payload["company"] = {
            "company_id": company.id,
            "company_name": company.name,
            "company_service_period_id": service_period_id,
            "department_id": department.id,
            "department_name": department.department_name,
        }

        existing_work_order_id = intake_context.get("work_order_id")
        if existing_work_order_id:
            existing = WorkOrder.objects.filter(pk=existing_work_order_id).first()
            if existing:
                return {
                    "created": True,
                    "work_order_id": existing.id,
                    "work_order_no": existing.work_order_no,
                    "payload": payload,
                    "company_id": existing.company_id,
                    "is_duplicate": True,
                }

        service_object = ServiceObject.objects.get(pk=payload["address"]["service_object_id"])
        service = ServicesCatalog.objects.get(pk=payload["classification"]["service_id"])
        status_new = WorkOrderStatusRef.objects.get(short_code_en="new_registered")
        resident_user = User.objects.filter(pk=django_user_id).first() if django_user_id else None

        source_payload_json = {
            "channel": channel,
            "session_id": session_id,
            "user_id": str(user_id),
            "django_user_id": django_user_id,
            "message_log_id": message_log_id,
            "original_text": original_text,
            "service_result": service_result,
            "intake_context": intake_context,
        }

        with transaction.atomic():
            work_order = WorkOrder.objects.create(
                company=company,
                object=service_object,
                service=service,
                department=department,
                message_log_ref=str(message_log_id) if message_log_id else None,
                creation_source="bot_json",
                resident_user=resident_user,
                original_request_text=payload["problem"]["summary"],
                additional_info_text=self.payload_builder.compose_additional_info(payload),
                is_emergency=payload["problem"]["is_emergency"],
                priority_code=payload["problem"]["priority_code"],
                current_internal_status=status_new,
                created_at=timezone.now(),
                is_test=False,
            )

            WorkOrderStatusHistory.objects.create(
                work_order=work_order,
                status=status_new,
                changed_by=resident_user,
                is_test=False,
            )

            build_sla_rows(work_order)

            WorkOrderEventLog.objects.create(
                work_order=work_order,
                company=company,
                department=department,
                event_type_code="created",
                event_datetime=timezone.now(),
                author_user=resident_user,
                text_value=f"Заявка создана из чатового intake ({channel}).",
                event_payload_json={
                    "source_payload_json": source_payload_json,
                    "external_message_id": external_message_id,
                    "channel": channel,
                    "session_id": session_id,
                    "message_log_id": message_log_id,
                    "normalized_payload_json": payload,
                },
                new_status=status_new,
                new_service=service,
                new_object=service_object,
                is_visible_to_resident=True,
                is_test=False,
            )

        return {
            "created": True,
            "work_order_id": work_order.id,
            "work_order_no": work_order.work_order_no,
            "payload": payload,
            "company_id": company.id,
            "department_id": department.id,
        }

    def _resolve_company(self, payload: Dict[str, Any]) -> Tuple[Optional[object], str, Optional[int]]:
        return self.company_resolver.resolve(
            service_object_id=payload["address"].get("service_object_id"),
            on_date=timezone.localdate(),
        )

    def _resolve_department(self, service_id: int, company_id: int):
        service_mapping = (
            CompanyRouteMapping.objects.select_related("target_department")
            .filter(company_id=company_id, service_id=service_id, is_active=True)
            .order_by("id")
            .first()
        )
        return service_mapping.target_department if service_mapping else None
