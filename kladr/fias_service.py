import logging
from typing import Any, Dict, List, Optional

import httpx
from decouple import config

from address.services import build_full_address, normalize_house_number, normalize_text

logger = logging.getLogger(__name__)

HOUSE_LEVEL_IDS = {10}
STREET_LEVEL_IDS = {8}


class FiasAddressService:
    """Клиент FIAS/GAR API и адресный fallback по улице и дому."""

    def __init__(self):
        self.base_url = config(
            "FIAS_API_BASE_URL",
            default="https://fias-public-service.nalog.ru/api/spas/v2.0",
        ).rstrip("/")
        self.master_token = config("FIAS_API_TOKEN", default="").strip()
        self.address_type = int(config("FIAS_ADDRESS_TYPE", default="1"))
        self.timeout = float(config("FIAS_API_TIMEOUT", default="15"))

    @property
    def is_configured(self) -> bool:
        return bool(self.master_token)

    def _headers(self) -> Dict[str, str]:
        return {"master-token": self.master_token, "Accept": "application/json"}

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.is_configured:
            raise RuntimeError("FIAS_API_TOKEN is not configured")

        url = f"{self.base_url}/{path.lstrip('/')}"
        with httpx.Client(timeout=self.timeout, verify=True) as client:
            response = client.request(method, url, headers=self._headers(), params=params, json=json_body)
            response.raise_for_status()
            return response.json() if response.text.strip() else {}

    def search_address_item(self, search_string: str, address_type: Optional[int] = None) -> Dict[str, Any]:
        if not search_string:
            return {}
        return self._request(
            "GET",
            "SearchAddressItem",
            params={"search_string": search_string, "address_type": address_type or self.address_type},
        )

    def search_address_items(self, search_string: str, address_type: Optional[int] = None) -> List[Dict[str, Any]]:
        if not search_string:
            return []
        data = self._request(
            "GET",
            "SearchAddressItems",
            params={"search_string": search_string, "address_type": address_type or self.address_type},
        )
        return data.get("addresses") or []

    def search_by_parts(self, structured_address: Dict[str, Any]) -> Dict[str, Any]:
        if not structured_address:
            return {}
        return self._request("POST", "SearchByParts", json_body=structured_address)

    def get_address_item_by_guid(self, object_guid: str, address_type: Optional[int] = None) -> Dict[str, Any]:
        if not object_guid:
            return {}
        data = self._request(
            "GET",
            "GetAddressItemByGuid",
            params={"object_guid": object_guid, "address_type": address_type or self.address_type},
        )
        addresses = data.get("addresses") or []
        return addresses[0] if addresses else {}

    def get_address_item_by_id(self, object_id: int, address_type: Optional[int] = None) -> Dict[str, Any]:
        if not object_id:
            return {}
        data = self._request(
            "GET",
            "GetAddressItemById",
            params={"object_id": object_id, "address_type": address_type or self.address_type},
        )
        addresses = data.get("addresses") or []
        return addresses[0] if addresses else {}

    def build_structured_address(self, components: Dict[str, Any]) -> Dict[str, Any]:
        result = {
            "region": components.get("region") or None,
            "city": components.get("city") or None,
            "settlement": components.get("settlement") or None,
            "street": components.get("street") or None,
            "house": components.get("house_number") or None,
        }
        apartment = components.get("apartment_number")
        if apartment:
            result["apartment"] = apartment
        return {key: value for key, value in result.items() if value}

    def resolve_building_match(self, full_address: str, expected_house_number: Optional[str] = None) -> Dict[str, Any]:
        expected = normalize_house_number(expected_house_number)
        direct = self.search_address_item(full_address)
        if self._is_house_candidate(direct, expected):
            return direct

        candidates = self.search_address_items(full_address)
        ranked = [item for item in candidates if self._is_house_candidate(item, expected)]
        ranked.sort(key=lambda item: self._score_candidate(item, full_address, expected), reverse=True)
        return ranked[0] if ranked else {}

    def resolve_street_match(self, components: Dict[str, Any]) -> Dict[str, Any]:
        parts = {
            "region": components.get("region"),
            "city": components.get("city"),
            "settlement": components.get("settlement"),
            "street": components.get("street"),
        }
        search_string = ", ".join(str(value).strip() for value in parts.values() if value)
        if not search_string:
            return {}
        candidates = self.search_address_items(search_string)
        ranked = [item for item in candidates if item.get("object_level_id") in STREET_LEVEL_IDS]
        ranked.sort(key=lambda item: self._score_street_candidate(item, components), reverse=True)
        return ranked[0] if ranked else {}

    def resolve_building_by_street_guid(self, street_guid: str, house_number: str) -> Dict[str, Any]:
        if not street_guid or not house_number:
            return {}

        street_item = self.get_address_item_by_guid(street_guid)
        street_name = street_item.get("full_name") or street_item.get("name")
        if not street_name:
            return {}

        search_string = f"{street_name}, дом {house_number}"
        candidates = self.search_address_items(search_string)
        normalized_house = normalize_house_number(house_number)
        ranked = [
            item
            for item in candidates
            if self._is_house_candidate(item, normalized_house) and self._has_street_guid(item, street_guid)
        ]
        ranked.sort(key=lambda item: self._score_candidate(item, search_string, normalized_house), reverse=True)
        return ranked[0] if ranked else {}

    def resolve_building_with_fallback(self, components: Dict[str, Any]) -> Dict[str, Any]:
        search_string = build_full_address(components)
        house_number = normalize_house_number(components.get("house_number"))
        direct = self.resolve_building_match(search_string, expected_house_number=house_number)
        if direct:
            street_guid = self._extract_street_guid(direct)
            return {
                "house_guid": direct.get("object_guid"),
                "street_guid": street_guid,
                "full_address": direct.get("full_name") or search_string,
                "fias_item": direct,
            }

        street_item = self.resolve_street_match(components)
        street_guid = street_item.get("object_guid")
        if not street_guid:
            return {}

        by_street = self.resolve_building_by_street_guid(street_guid, house_number)
        if by_street:
            return {
                "house_guid": by_street.get("object_guid"),
                "street_guid": street_guid,
                "full_address": by_street.get("full_name") or search_string,
                "fias_item": by_street,
            }

        return {
            "house_guid": None,
            "street_guid": street_guid,
            "full_address": search_string,
            "fias_item": {},
        }

    def bind_building_mapping(self, building, fias_item: Dict[str, Any]) -> bool:
        if not fias_item:
            return False

        changed = False
        mapping = {
            "fias_guid": fias_item.get("object_guid"),
            "street_fias_guid": self._extract_street_guid(fias_item),
            "full_address": fias_item.get("full_name") or building.full_address,
        }
        house_number = self._extract_house_number(fias_item)
        if house_number:
            mapping["house_number"] = house_number

        for field_name, value in mapping.items():
            if value is not None and getattr(building, field_name, None) != value:
                setattr(building, field_name, value)
                changed = True

        if changed:
            building.save(update_fields=list(mapping.keys()) + ["updated_at"])
        return changed

    def get_internal_ids_by_fias(
        self,
        *,
        fias_object_guid: Optional[str] = None,
        street_fias_guid: Optional[str] = None,
        house_number: Optional[str] = None,
        apartment_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        from address.models import Building
        from portal.models import ServiceObject, Unit

        building = None
        if fias_object_guid:
            building = Building.objects.filter(fias_guid=fias_object_guid).first()
        if building is None and street_fias_guid and house_number:
            building = Building.objects.filter(
                street_fias_guid=street_fias_guid,
                house_number=normalize_house_number(house_number),
            ).first()
        if building is None:
            return {}

        unit = None
        if apartment_number:
            unit = (
                Unit.objects.filter(building_id=building.id, unit_number__iexact=normalize_text(apartment_number))
                .order_by("unit_id")
                .first()
            )

        service_object = None
        if unit is not None:
            service_object = (
                ServiceObject.objects.filter(building_id=building.id, unit_id=unit.unit_id, is_active=True)
                .order_by("service_object_id")
                .first()
            )
        if service_object is None:
            service_object = (
                ServiceObject.objects.filter(building_id=building.id, unit_id__isnull=True, is_active=True)
                .order_by("service_object_id")
                .first()
            )

        return {
            "building_id": building.id,
            "unit_id": unit.unit_id if unit else None,
            "service_object_id": service_object.service_object_id if service_object else None,
            "fias_object_guid": str(building.fias_guid) if building.fias_guid else None,
            "street_fias_guid": str(building.street_fias_guid) if building.street_fias_guid else None,
            "house_number": building.house_number,
        }

    def _is_house_candidate(self, item: Dict[str, Any], expected_house_number: str) -> bool:
        if not item or item.get("object_level_id") not in HOUSE_LEVEL_IDS:
            return False
        if not expected_house_number:
            return True
        return self._extract_house_number(item) == expected_house_number

    def _extract_house_number(self, item: Dict[str, Any]) -> str:
        hierarchy = item.get("hierarchy") or []
        for current in reversed(hierarchy):
            if current.get("object_level_id") in HOUSE_LEVEL_IDS or (current.get("object_type") or "").lower() == "house":
                number = current.get("number") or current.get("full_name") or current.get("name")
                return normalize_house_number(number)
        return normalize_house_number(item.get("number") or item.get("name"))

    def _extract_street_guid(self, item: Dict[str, Any]) -> Optional[str]:
        hierarchy = item.get("hierarchy") or []
        for current in reversed(hierarchy):
            if current.get("object_level_id") in STREET_LEVEL_IDS:
                return current.get("object_guid")
        return None

    def _has_street_guid(self, item: Dict[str, Any], street_guid: str) -> bool:
        hierarchy = item.get("hierarchy") or []
        return any(current.get("object_guid") == street_guid for current in hierarchy)

    def _score_candidate(self, item: Dict[str, Any], full_address: str, expected_house_number: str) -> int:
        score = 0
        if item.get("is_active"):
            score += 50
        if item.get("object_level_id") in HOUSE_LEVEL_IDS:
            score += 100
        if expected_house_number and self._extract_house_number(item) == expected_house_number:
            score += 100
        item_name = normalize_text(item.get("full_name"))
        search_name = normalize_text(full_address)
        if item_name == search_name:
            score += 100
        elif search_name and search_name in item_name:
            score += 50
        return score

    def _score_street_candidate(self, item: Dict[str, Any], components: Dict[str, Any]) -> int:
        score = 0
        if item.get("is_active"):
            score += 50
        if item.get("object_level_id") in STREET_LEVEL_IDS:
            score += 100
        item_name = normalize_text(item.get("full_name") or item.get("name"))
        street = normalize_text(components.get("street"))
        city = normalize_text(components.get("city"))
        if street and street in item_name:
            score += 100
        if city and city in item_name:
            score += 50
        return score


def resolve_internal_ids_by_fias(
    *,
    fias_object_guid: Optional[str] = None,
    street_fias_guid: Optional[str] = None,
    house_number: Optional[str] = None,
    apartment_number: Optional[str] = None,
) -> Dict[str, Any]:
    return FiasAddressService().get_internal_ids_by_fias(
        fias_object_guid=fias_object_guid,
        street_fias_guid=street_fias_guid,
        house_number=house_number,
        apartment_number=apartment_number,
    )
