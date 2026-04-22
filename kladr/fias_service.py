import logging
from typing import Any, Dict, List, Optional

import httpx
from decouple import config

logger = logging.getLogger(__name__)

HOUSE_LEVEL_IDS = {10}
STREET_LEVEL_IDS = {8}


class FiasAddressService:
    """Client for the official FIAS SPAS API v2.0."""

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
        return {
            "master-token": self.master_token,
            "Accept": "application/json",
        }

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
            if not response.text.strip():
                return {}
            return response.json()

    def search_address_item(self, search_string: str, address_type: Optional[int] = None) -> Dict[str, Any]:
        if not search_string:
            return {}
        return self._request(
            "GET",
            "SearchAddressItem",
            params={
                "search_string": search_string,
                "address_type": address_type or self.address_type,
            },
        )

    def search_address_items(self, search_string: str, address_type: Optional[int] = None) -> List[Dict[str, Any]]:
        if not search_string:
            return []
        data = self._request(
            "GET",
            "SearchAddressItems",
            params={
                "search_string": search_string,
                "address_type": address_type or self.address_type,
            },
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
            params={
                "object_guid": object_guid,
                "address_type": address_type or self.address_type,
            },
        )
        addresses = data.get("addresses") or []
        return addresses[0] if addresses else {}

    def get_address_item_by_id(self, object_id: int, address_type: Optional[int] = None) -> Dict[str, Any]:
        if not object_id:
            return {}
        data = self._request(
            "GET",
            "GetAddressItemById",
            params={
                "object_id": object_id,
                "address_type": address_type or self.address_type,
            },
        )
        addresses = data.get("addresses") or []
        return addresses[0] if addresses else {}

    def resolve_building_match(
        self,
        full_address: str,
        expected_house_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        house_number = (expected_house_number or "").strip().lower()

        direct = self.search_address_item(full_address)
        if self._is_house_candidate(direct, house_number):
            return direct

        candidates = self.search_address_items(full_address)
        ranked = [candidate for candidate in candidates if self._is_house_candidate(candidate, house_number)]
        ranked.sort(key=lambda item: self._score_candidate(item, full_address, house_number), reverse=True)
        return ranked[0] if ranked else {}

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

    def bind_building_mapping(self, building, fias_item: Dict[str, Any]) -> bool:
        if not fias_item:
            return False

        changed = False
        changed |= self._apply_fias_fields(building, fias_item, full_name=fias_item.get("full_name"))

        street_item = self._extract_street_from_hierarchy(fias_item)
        if street_item:
            street_changed = self._apply_fias_fields(building.address_object, street_item)
            if street_changed:
                changed = True
                building.address_object.save(
                    update_fields=[
                        "fias_object_id",
                        "fias_object_guid",
                        "fias_level_id",
                        "fias_address_type",
                        "updated_at",
                    ]
                )

        if changed:
            building.save(
                update_fields=[
                    "fias_object_id",
                    "fias_object_guid",
                    "fias_level_id",
                    "fias_address_type",
                    "fias_full_name",
                    "updated_at",
                ]
            )
            self._sync_service_objects_for_building(building.id, building.fias_object_id)
        return changed

    def get_internal_ids_by_fias(
        self,
        *,
        fias_object_guid: Optional[str] = None,
        fias_object_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        from kladr.models import Building
        from portal.models import ServiceObject

        service_object = None
        if fias_object_id:
            service_object = (
                ServiceObject.objects.filter(fias_house_object_id=fias_object_id, unit_id__isnull=True, is_active=True)
                .order_by("service_object_id")
                .first()
            )
            if service_object is None:
                service_object = (
                    ServiceObject.objects.filter(fias_house_object_id=fias_object_id, is_active=True)
                    .order_by("service_object_id")
                    .first()
                )

        building = None
        if service_object is not None:
            building = Building.objects.filter(pk=service_object.building_id).first()
        if fias_object_guid:
            building = Building.objects.filter(fias_object_guid=fias_object_guid).first()
        if building is None and fias_object_id:
            building = Building.objects.filter(fias_object_id=fias_object_id).first()
        if building is None:
            return {}

        if service_object is None:
            service_object = (
                ServiceObject.objects.filter(building_id=building.id, unit_id__isnull=True, is_active=True)
                .order_by("service_object_id")
                .first()
            )
        if service_object is None:
            service_object = (
                ServiceObject.objects.filter(building_id=building.id, is_active=True)
                .order_by("service_object_id")
                .first()
            )

        return {
            "building_id": building.id,
            "service_object_id": service_object.service_object_id if service_object else None,
            "fias_object_id": building.fias_object_id,
            "fias_object_guid": str(building.fias_object_guid) if building.fias_object_guid else None,
            "fias_level_id": building.fias_level_id,
            "fias_address_type": building.fias_address_type,
        }

    def _extract_street_from_hierarchy(self, fias_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        hierarchy = fias_item.get("hierarchy") or []
        for item in reversed(hierarchy):
            if item.get("object_level_id") in STREET_LEVEL_IDS:
                return item
        return None

    def _apply_fias_fields(self, obj, fias_item: Dict[str, Any], *, full_name: Optional[str] = None) -> bool:
        mapping = {
            "fias_object_id": fias_item.get("object_id"),
            "fias_object_guid": fias_item.get("object_guid"),
            "fias_level_id": fias_item.get("object_level_id"),
            "fias_address_type": fias_item.get("address_type"),
        }
        if hasattr(obj, "fias_full_name"):
            mapping["fias_full_name"] = full_name or fias_item.get("full_name")

        changed = False
        for field_name, value in mapping.items():
            if getattr(obj, field_name, None) != value:
                setattr(obj, field_name, value)
                changed = True
        return changed

    def _sync_service_objects_for_building(self, building_id: int, fias_house_object_id: Optional[int]) -> None:
        if not building_id:
            return

        from portal.models import ServiceObject

        ServiceObject.objects.filter(building_id=building_id).update(fias_house_object_id=fias_house_object_id)

    def _is_house_candidate(self, item: Dict[str, Any], expected_house_number: str) -> bool:
        if not item:
            return False
        if item.get("object_level_id") not in HOUSE_LEVEL_IDS:
            return False
        if not expected_house_number:
            return True
        return self._extract_house_number(item) == expected_house_number

    def _extract_house_number(self, item: Dict[str, Any]) -> str:
        if item.get("object_level_id") in HOUSE_LEVEL_IDS:
            hierarchy = item.get("hierarchy") or []
            if hierarchy:
                last = hierarchy[-1]
                return str(last.get("number") or "").strip().lower()
        return ""

    def _score_candidate(self, item: Dict[str, Any], full_address: str, expected_house_number: str) -> int:
        score = 0
        if item.get("is_active"):
            score += 50
        if item.get("object_level_id") in HOUSE_LEVEL_IDS:
            score += 100
        if expected_house_number and self._extract_house_number(item) == expected_house_number:
            score += 100
        item_name = (item.get("full_name") or "").lower()
        search_name = (full_address or "").lower()
        if item_name == search_name:
            score += 100
        elif search_name in item_name:
            score += 50
        return score


def resolve_internal_ids_by_fias(
    *,
    fias_object_guid: Optional[str] = None,
    fias_object_id: Optional[int] = None,
) -> Dict[str, Any]:
    return FiasAddressService().get_internal_ids_by_fias(
        fias_object_guid=fias_object_guid,
        fias_object_id=fias_object_id,
    )
