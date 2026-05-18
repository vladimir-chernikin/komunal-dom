#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import re
from typing import Dict, Optional

from address.models import Building
from address.services import build_full_address, normalize_house_number, normalize_text, normalize_unit_number
from kladr.fias_service import FiasAddressService

logger = logging.getLogger(__name__)


class AddressExtractor:
    """Разбор адреса из текста и сопоставление с локальными объектами обслуживания."""

    STREET_PATTERN = re.compile(
        r"(?:ул(?:ица)?|пр(?:оспект|[-.\s]?т)?|пер(?:еулок)?|бул(?:ьвар)?|наб(?:ережная)?|шоссе)\s+([^,]+)",
        re.IGNORECASE,
    )
    HOUSE_PATTERN = re.compile(
        r"(?:д(?:ом)?\.?\s*)?(\d+[а-яa-z0-9/\-]*(?:\s*(?:к|корп|корпус|с|стр|строение|лит)\s*[а-яa-z0-9/\-]+)*)",
        re.IGNORECASE,
    )
    APARTMENT_PATTERN = re.compile(r"(?:кв(?:артира)?|пом(?:ещение)?)\.?\s*([a-zа-я0-9\-\/]+)", re.IGNORECASE)

    def __init__(self):
        self.fias_service = FiasAddressService()

    def extract_address_components(self, text: str, context_memory: Dict = None) -> Dict:
        current = self._parse_address_text(text)
        merged = self._merge_with_memory(current, context_memory or {})
        normalized = self._normalize_components(merged)

        known = sum(
            1
            for value in (
                normalized.get("city"),
                normalized.get("street"),
                normalized.get("house_number"),
                normalized.get("apartment_number"),
            )
            if value
        )
        normalized["confidence"] = min(1.0, known / 4.0)
        return normalized

    def validate_and_match_to_db(self, address_components: Dict) -> Dict:
        city = address_components.get("city")
        street = address_components.get("street")
        house_number = normalize_house_number(address_components.get("house_number"))
        apartment_number = normalize_unit_number(address_components.get("apartment_number"))

        missing = []
        if not city:
            missing.append("населенный пункт")
        if not street:
            missing.append("улицу")
        if not house_number:
            missing.append("номер дома")
        if missing:
            return self._result(
                found=False,
                serviced=False,
                confidence=0.0,
                reason=f"Нужно указать: {', '.join(missing)}",
                match_status="incomplete",
                source="input",
            )

        search_string = self._build_search_string(address_components)
        fias_match = self.fias_service.resolve_building_with_fallback(address_components)
        street_guid = fias_match.get("street_guid")
        house_guid = fias_match.get("house_guid")

        if not street_guid:
            return self._result(
                found=False,
                serviced=False,
                confidence=0.0,
                reason="Улица не найдена в ФИАС",
                match_status="not_found",
                source="fias",
                fias_candidate_hints=fias_match.get("candidate_hints") or [],
            )

        building = self._find_local_building(
            fias_guid=house_guid,
            street_guid=street_guid,
            house_number=house_number,
        )
        if building is None:
            return self._result(
                found=False,
                serviced=False,
                confidence=0.4 if house_guid else 0.2,
                reason="Дом найден в ФИАС, но не привязан к обслуживаемым объектам" if house_guid else "Дом не найден в локальной адресной базе",
                match_status="not_serviced" if house_guid else "not_found",
                source="fias",
                address_full=fias_match.get("full_address") or search_string,
                fias_object_guid=house_guid,
                street_fias_guid=street_guid,
                house_number=house_number,
                fias_candidate_hints=fias_match.get("candidate_hints") or [],
            )

        service_object = self._resolve_service_object(building.id, apartment_number)
        unit_id = self._resolve_unit(building.id, apartment_number)

        source = "local+fias" if (building.fias_guid or street_guid) else "local"
        return self._result(
            found=True,
            serviced=bool(service_object),
            building_id=building.id,
            unit_id=unit_id,
            service_object_id=service_object.service_object_id if service_object else None,
            address_full=building.full_address,
            confidence=0.95 if service_object else 0.7,
            reason=None if service_object else "Адрес найден, но объект обслуживания еще не создан",
            match_status="matched" if service_object else "not_serviced",
            source=source,
            fias_object_guid=str(building.fias_guid) if building.fias_guid else house_guid,
            street_fias_guid=str(building.street_fias_guid) if building.street_fias_guid else street_guid,
            house_number=building.house_number,
        )

    def ask_clarification_if_needed(self, address_components: Dict, validation_result: Dict) -> Dict:
        if validation_result.get("match_status") == "matched" and validation_result.get("confidence", 0) >= 0.8:
            return {"need_clarification": False, "message": None}

        if validation_result.get("reason"):
            return {
                "need_clarification": True,
                "message": f"{validation_result['reason']}. Напишите адрес еще раз: населенный пункт, улица, дом.",
            }

        return {
            "need_clarification": True,
            "message": "Напишите адрес полностью: населенный пункт, улица, дом.",
        }

    def _parse_address_text(self, text: str) -> Dict:
        result = {
            "region": None,
            "city": None,
            "settlement": None,
            "street": None,
            "house_number": None,
            "apartment_number": None,
            "entrance": None,
        }
        normalized = normalize_text(text)
        if not normalized:
            return result

        city_match = re.search(r"(?:г(?:ород)?\.?\s*)([^,]+)", normalized, re.IGNORECASE)
        if city_match:
            result["city"] = city_match.group(1).strip()
        else:
            parts = [part.strip() for part in normalized.split(",") if part.strip()]
            if len(parts) >= 2:
                result["city"] = parts[0]

        street_match = self.STREET_PATTERN.search(normalized)
        if street_match:
            street = street_match.group(1).split(",")[0].strip()
            street = re.split(self.HOUSE_PATTERN, street, maxsplit=1)[0].strip(" ,")
            result["street"] = street

        house_match = self.HOUSE_PATTERN.search(normalized)
        if house_match:
            result["house_number"] = house_match.group(1).strip()

        apartment_match = self.APARTMENT_PATTERN.search(normalized)
        if apartment_match:
            result["apartment_number"] = apartment_match.group(1).strip()

        return result

    def _merge_with_memory(self, current: Dict, context_memory: Dict) -> Dict:
        result = {
            "region": context_memory.get("region"),
            "city": context_memory.get("city"),
            "settlement": context_memory.get("settlement"),
            "street": context_memory.get("street"),
            "house_number": context_memory.get("house_number"),
            "apartment_number": context_memory.get("apartment_number"),
            "entrance": context_memory.get("entrance"),
        }
        for key, value in current.items():
            if value:
                result[key] = value
        return result

    def _normalize_components(self, components: Dict) -> Dict:
        normalized = dict(components)
        for key in ("region", "city", "settlement", "street"):
            value = normalized.get(key)
            normalized[key] = normalize_text(value) if value else None
        normalized["house_number"] = normalize_house_number(normalized.get("house_number"))
        normalized["apartment_number"] = normalize_unit_number(normalized.get("apartment_number"))
        return normalized

    def _build_search_string(self, address_components: Dict) -> str:
        return build_full_address(address_components)

    def _find_local_building(
        self,
        *,
        fias_guid: Optional[str],
        street_guid: Optional[str],
        house_number: str,
    ) -> Optional[Building]:
        if fias_guid:
            building = Building.objects.filter(fias_guid=fias_guid).first()
            if building:
                return building

        if street_guid and house_number:
            return Building.objects.filter(
                street_fias_guid=street_guid,
                house_number=house_number,
            ).first()
        return None

    def _find_local_building_by_text(self, *, city: str, street: str, house_number: str) -> Optional[Building]:
        if not city or not street or not house_number:
            return None
        city_norm = normalize_text(city)
        street_norm = normalize_text(street)
        for candidate in Building.objects.filter(house_number=house_number).order_by("id")[:50]:
            normalized_address = normalize_text(candidate.full_address)
            if city_norm in normalized_address and street_norm in normalized_address:
                return candidate
        return None

    def _resolve_service_object(self, building_id: int, apartment_number: Optional[str]):
        from portal.models import ServiceObject, Unit

        if apartment_number:
            unit = (
                Unit.objects.filter(building_id=building_id, unit_number__iexact=apartment_number)
                .order_by("unit_id")
                .first()
            )
            if unit:
                service_object = (
                    ServiceObject.objects.filter(building_id=building_id, unit_id=unit.unit_id, is_active=True)
                    .order_by("service_object_id")
                    .first()
                )
                if service_object:
                    return service_object

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
            Unit.objects.filter(building_id=building_id, unit_number__iexact=apartment_number)
            .order_by("unit_id")
            .first()
        )
        return unit.unit_id if unit else None

    def _result(self, **kwargs) -> Dict:
        result = {
            "found": False,
            "serviced": False,
            "building_id": None,
            "unit_id": None,
            "service_object_id": None,
            "address_full": None,
            "confidence": 0.0,
            "reason": None,
            "match_status": "not_found",
            "source": "input",
            "fias_object_id": None,
            "fias_object_guid": None,
            "street_fias_guid": None,
            "house_number": None,
            "fias_level_id": None,
            "fias_address_type": None,
            "fias_candidate_hints": [],
        }
        result.update(kwargs)
        return result
