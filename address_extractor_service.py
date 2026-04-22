#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import re
from typing import Dict, Optional

from django.db.models import Q

from kladr.fias_service import FiasAddressService
from kladr.models import Building, KladrAddressObject

logger = logging.getLogger(__name__)


class AddressExtractor:
    """Extracts address fragments from chat text and validates them against FIAS/local data."""

    STREET_PREFIXES = (
        "улица",
        "ул",
        "ул.",
        "проспект",
        "пр-т",
        "пр",
        "пр.",
        "переулок",
        "пер",
        "пер.",
        "бульвар",
        "бул",
        "бул.",
        "проезд",
        "шоссе",
        "наб",
        "наб.",
    )

    def __init__(self):
        self.fias_service = FiasAddressService()
        logger.info("AddressExtractor initialized with Django ORM and FIAS support")

    def extract_address_components(self, text: str, context_memory: Dict = None) -> Dict:
        current_components = self._parse_address_text(text)
        result = self._merge_with_memory(current_components, context_memory or {})
        result = self._normalize_components(result)

        parts_count = sum(
            1
            for value in (
                result.get("city"),
                result.get("street"),
                result.get("house_number"),
                result.get("apartment_number"),
            )
            if value
        )
        result["confidence"] = min(1.0, parts_count / 4.0)
        return result

    def validate_and_match_to_db(self, address_components: Dict) -> Dict:
        street = address_components.get("street")
        city = address_components.get("city")
        house_number = address_components.get("house_number")
        apartment_number = address_components.get("apartment_number")

        if not street or not house_number:
            return {
                "found": False,
                "serviced": False,
                "building_id": None,
                "unit_id": None,
                "service_object_id": None,
                "confidence": 0.0,
                "reason": "Нужно указать улицу и номер дома",
                "match_status": "incomplete",
                "source": "input",
                "fias_object_id": None,
                "fias_object_guid": None,
                "fias_level_id": None,
                "fias_address_type": None,
            }

        try:
            building_obj = self._find_local_building(street=street, house_number=house_number, city=city)
            search_string = self._build_search_string(address_components, building=building_obj)

            fias_item = {}
            if self.fias_service.is_configured:
                try:
                    fias_item = self.fias_service.resolve_building_match(
                        search_string,
                        expected_house_number=house_number,
                    )
                except Exception as exc:
                    logger.warning("FIAS validation failed for '%s': %s", search_string, exc)

            if building_obj is None and fias_item:
                internal_ids = self.fias_service.get_internal_ids_by_fias(
                    fias_object_guid=fias_item.get("object_guid"),
                    fias_object_id=fias_item.get("object_id"),
                )
                if internal_ids.get("building_id"):
                    building_obj = (
                        Building.objects.select_related(
                            "address_object__type",
                            "address_object__parent__type",
                            "address_object__parent__parent__type",
                        )
                        .filter(pk=internal_ids["building_id"])
                        .first()
                    )

            if building_obj is None:
                if fias_item:
                    return {
                        "found": False,
                        "serviced": False,
                        "building_id": None,
                        "unit_id": None,
                        "service_object_id": None,
                        "confidence": 0.4,
                        "reason": "Адрес существует в ФИАС, но не привязан к объектам обслуживания компании",
                        "match_status": "not_serviced",
                        "source": "fias",
                        "address_full": fias_item.get("full_name") or search_string,
                        "fias_object_id": fias_item.get("object_id"),
                        "fias_object_guid": fias_item.get("object_guid"),
                        "fias_level_id": fias_item.get("object_level_id"),
                        "fias_address_type": fias_item.get("address_type"),
                    }

                return {
                    "found": False,
                    "serviced": False,
                    "building_id": None,
                    "unit_id": None,
                    "service_object_id": None,
                    "confidence": 0.0,
                    "reason": f'Адрес "{search_string}" не найден',
                    "match_status": "not_found",
                    "source": "fias" if self.fias_service.is_configured else "local",
                    "fias_object_id": None,
                    "fias_object_guid": None,
                    "fias_level_id": None,
                    "fias_address_type": None,
                }

            if fias_item:
                self.fias_service.bind_building_mapping(building_obj, fias_item)
            else:
                fias_item = self._update_fias_mapping_for_building(building_obj, address_components)

            service_object = self._resolve_service_object(building_obj.id)
            unit_id = self._resolve_unit(building_obj.id, apartment_number)

            if fias_item:
                fias_object_id = fias_item.get("object_id") or building_obj.fias_object_id
                fias_object_guid = fias_item.get("object_guid") or (
                    str(building_obj.fias_object_guid) if building_obj.fias_object_guid else None
                )
                fias_level_id = fias_item.get("object_level_id") or building_obj.fias_level_id
                fias_address_type = fias_item.get("address_type") or building_obj.fias_address_type
            else:
                fias_object_id = building_obj.fias_object_id
                fias_object_guid = str(building_obj.fias_object_guid) if building_obj.fias_object_guid else None
                fias_level_id = building_obj.fias_level_id
                fias_address_type = building_obj.fias_address_type

            serviced = bool(service_object)
            return {
                "found": True,
                "serviced": serviced,
                "building_id": building_obj.id,
                "unit_id": unit_id,
                "service_object_id": service_object.service_object_id if service_object else None,
                "street_name": building_obj.address_object.name,
                "address_full": building_obj.get_full_address(),
                "confidence": 0.95 if serviced else 0.7,
                "reason": None if serviced else "Дом найден, но объект обслуживания для чат-intake не настроен",
                "match_status": "matched" if serviced else "not_serviced",
                "source": "local+fias" if fias_object_id else "local",
                "fias_object_id": fias_object_id,
                "fias_object_guid": fias_object_guid,
                "fias_level_id": fias_level_id,
                "fias_address_type": fias_address_type,
            }
        except Exception as exc:
            logger.error("Address validation failed: %s", exc, exc_info=True)
            return {
                "found": False,
                "serviced": False,
                "building_id": None,
                "unit_id": None,
                "service_object_id": None,
                "reason": f"Ошибка базы данных: {exc}",
                "confidence": 0.0,
                "match_status": "error",
                "source": "local",
                "fias_object_id": None,
                "fias_object_guid": None,
                "fias_level_id": None,
                "fias_address_type": None,
            }

    def ask_clarification_if_needed(self, address_components: Dict, validation_result: Dict) -> Dict:
        confidence = validation_result.get("confidence", 0.0)
        if confidence >= 0.8 and validation_result.get("match_status") == "matched":
            return {
                "need_clarification": False,
                "message": None,
            }

        missing_parts = []
        if not address_components.get("street"):
            missing_parts.append("улицу")
        if not address_components.get("house_number"):
            missing_parts.append("номер дома")

        if missing_parts:
            message = f"Подскажите, пожалуйста, {', '.join(missing_parts)}."
        elif validation_result.get("match_status") == "not_serviced":
            message = "Адрес нашла, но он пока не привязан к обслуживаемому объекту. Проверьте адрес еще раз."
        elif validation_result.get("reason"):
            message = f"{validation_result['reason']}. Проверьте адрес и напишите его еще раз."
        else:
            message = "Напишите, пожалуйста, адрес: улицу и номер дома."

        return {
            "need_clarification": True,
            "message": message,
            "missing_parts": missing_parts,
        }

    def _parse_address_text(self, text: str) -> Dict:
        result = {
            "city": None,
            "street": None,
            "house_number": None,
            "apartment_number": None,
            "entrance": None,
        }

        if not text:
            return result

        normalized = re.sub(r"\s+", " ", text.strip())
        lowered = normalized.lower()

        city_match = re.search(r"(?:город|г\.)\s*([а-яё\- ]{2,})", lowered, re.IGNORECASE)
        if city_match:
            result["city"] = city_match.group(1).strip()

        street_patterns = [
            r"(?:улица|ул\.?|проспект|пр-т|пр\.?|переулок|пер\.?|бульвар|бул\.?|проезд|шоссе|наб\.?)\s+([а-яё0-9\- ]{2,})",
            r"^([а-яё0-9\- ]{2,})\s+(?:дом|д\.?)\s*\d",
            r"^([а-яё0-9\- ]{2,})\s+\d+[а-яёa-z0-9/\-]*$",
        ]
        for pattern in street_patterns:
            match = re.search(pattern, lowered, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip(" ,.")
                if not self._looks_like_problem_text(candidate):
                    result["street"] = candidate
                    break

        house_match = re.search(r"(?:дом|д\.?)\s*(\d+[а-яa-z0-9/\-]*)", lowered, re.IGNORECASE)
        if not house_match:
            house_match = re.search(r"\b([а-яё0-9\- ]{2,})\s+(\d+[а-яa-z0-9/\-]*)\b$", lowered, re.IGNORECASE)
            if house_match and result["street"] is None:
                candidate = house_match.group(1).strip(" ,.")
                if not self._looks_like_problem_text(candidate):
                    result["street"] = candidate
                result["house_number"] = house_match.group(2).strip()
        else:
            result["house_number"] = house_match.group(1).strip()

        apartment_match = re.search(r"(?:квартира|кв\.?)\s*(\d+[а-яa-z0-9/\-]*)", lowered, re.IGNORECASE)
        if apartment_match:
            result["apartment_number"] = apartment_match.group(1).strip()

        entrance_match = re.search(r"(?:подъезд|подьезд|под\.?)\s*(\d+)", lowered, re.IGNORECASE)
        if entrance_match:
            result["entrance"] = entrance_match.group(1).strip()

        return result

    def _merge_with_memory(self, current_components: Dict, context_memory: Dict) -> Dict:
        result = {
            "city": context_memory.get("city"),
            "street": context_memory.get("street"),
            "house_number": context_memory.get("house_number"),
            "apartment_number": context_memory.get("apartment_number"),
            "entrance": context_memory.get("entrance"),
        }
        for key, value in current_components.items():
            if value:
                result[key] = value
        return result

    def _normalize_components(self, components: Dict) -> Dict:
        result = dict(components)
        for key in ("city", "street"):
            value = result.get(key)
            if value:
                clean = re.sub(r"\s+", " ", str(value).strip(" ,."))
                result[key] = clean[:1].upper() + clean[1:] if clean else None

        for key in ("house_number", "apartment_number", "entrance"):
            value = result.get(key)
            if value:
                result[key] = str(value).strip(" ,.")

        return result

    def _build_search_string(self, address_components: Dict, building: Optional[Building] = None) -> str:
        if building is not None:
            return building.get_full_address()

        parts = []
        for field_name in ("region", "city", "settlement", "street"):
            value = address_components.get(field_name)
            if value:
                parts.append(str(value).strip())

        house_number = address_components.get("house_number")
        if house_number:
            parts.append(f"дом {house_number}")

        apartment_number = address_components.get("apartment_number")
        if apartment_number:
            parts.append(f"кв. {apartment_number}")

        return ", ".join(parts)

    def _find_local_building(self, *, street: str, house_number: str, city: Optional[str] = None) -> Optional[Building]:
        street_value = street.strip()
        streets = (
            KladrAddressObject.objects.select_related("type", "parent__type", "parent__parent__type")
            .filter(type__level=5)
            .filter(
                Q(name__iexact=street_value) |
                Q(name__icontains=street_value) |
                Q(name__istartswith=street_value)
            )
        )

        if city:
            city_value = city.strip()
            streets = streets.filter(
                Q(parent__name__iexact=city_value) |
                Q(parent__parent__name__iexact=city_value)
            )

        street_ids = list(streets.values_list("id", flat=True)[:20])
        if not street_ids:
            return None

        return (
            Building.objects.select_related(
                "address_object__type",
                "address_object__parent__type",
                "address_object__parent__parent__type",
            )
            .filter(address_object_id__in=street_ids, house_number__iexact=house_number.strip())
            .order_by("id")
            .first()
        )

    def _resolve_service_object(self, building_id: int):
        from portal.models import ServiceObject

        service_object = (
            ServiceObject.objects.filter(building_id=building_id, unit_id__isnull=True, is_active=True)
            .order_by("service_object_id")
            .first()
        )
        if service_object is None:
            service_object = (
                ServiceObject.objects.filter(building_id=building_id, is_active=True)
                .order_by("service_object_id")
                .first()
            )
        return service_object

    def _resolve_unit(self, building_id: int, apartment_number: Optional[str]) -> Optional[int]:
        if not apartment_number:
            return None

        from portal.models import Unit

        unit = (
            Unit.objects.filter(building_id=building_id, unit_number__iexact=str(apartment_number).strip())
            .order_by("unit_id")
            .first()
        )
        return unit.unit_id if unit else None

    def _update_fias_mapping_for_building(self, building: Building, address_components: Dict) -> Dict:
        if not self.fias_service.is_configured:
            return {}

        if building.fias_object_guid and building.fias_object_id and building.fias_level_id:
            return {
                "object_id": building.fias_object_id,
                "object_guid": str(building.fias_object_guid),
                "object_level_id": building.fias_level_id,
                "address_type": building.fias_address_type,
                "full_name": building.fias_full_name or building.get_full_address(),
            }

        search_string = self._build_search_string(address_components, building=building)
        fias_item = self.fias_service.resolve_building_match(
            search_string,
            expected_house_number=building.house_number,
        )
        if fias_item:
            self.fias_service.bind_building_mapping(building, fias_item)
        return fias_item

    def _looks_like_problem_text(self, candidate: str) -> bool:
        noise_words = (
            "теч",
            "прорв",
            "засор",
            "сломан",
            "не работает",
            "батаре",
            "кран",
            "труба",
            "вода",
            "отоплен",
            "свет",
            "лифт",
        )
        lowered = candidate.lower()
        return any(word in lowered for word in noise_words)
