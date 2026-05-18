import hashlib
import json
import time
from typing import Any, Dict, List, Optional, Tuple

from asgiref.sync import sync_to_async
from django.db import connection


class CatalogProvider:
    """Small reference catalog loader with version-based invalidation."""

    _snapshot: Optional[Dict[str, Any]] = None
    _loaded_at: float = 0.0
    _ttl_seconds = 60

    async def get_snapshot(self) -> Dict[str, Any]:
        now = time.monotonic()
        if self.__class__._snapshot and now - self.__class__._loaded_at < self.__class__._ttl_seconds:
            return self.__class__._snapshot

        snapshot = await sync_to_async(self._load_snapshot_sync)()
        current = self.__class__._snapshot
        if current and current.get("catalog_version") == snapshot.get("catalog_version"):
            current["checked_at"] = now
            self.__class__._loaded_at = now
            return current

        self.__class__._snapshot = snapshot
        self.__class__._loaded_at = now
        return snapshot

    async def get_service_types(self) -> List[Dict[str, Any]]:
        return (await self.get_snapshot())["service_types"]

    async def get_localizations(self) -> List[Dict[str, Any]]:
        return (await self.get_snapshot())["localizations"]

    async def get_categories(self) -> List[Dict[str, Any]]:
        return (await self.get_snapshot())["categories"]

    async def get_default_category_id(self) -> Optional[int]:
        return (await self.get_snapshot()).get("default_category_id")

    async def resolve_service(
        self,
        *,
        service_type_id: int,
        localization_id: int,
        category_id: int,
        company_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        return await sync_to_async(self._resolve_service_sync)(
            service_type_id=service_type_id,
            localization_id=localization_id,
            category_id=category_id,
            company_id=company_id,
        )

    def _load_snapshot_sync(self) -> Dict[str, Any]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT type_id, type_name FROM ref_service_types ORDER BY type_id")
            service_types = [
                {"service_type_id": row[0], "service_type_name": row[1]}
                for row in cursor.fetchall()
            ]

            cursor.execute("SELECT localization_id, localization_name FROM ref_localization ORDER BY localization_id")
            localizations = [
                {"localization_id": row[0], "localization_name": row[1]}
                for row in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT category_id, category_name, COALESCE(llm_description, ''), is_default
                FROM ref_categories
                ORDER BY category_id
                """
            )
            categories = [
                {
                    "category_id": row[0],
                    "category_name": row[1],
                    "llm_description": row[2],
                    "is_default": row[3],
                }
                for row in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT service_id, scenario_name, type_id, localization_id, category_id, updated_at
                FROM services_catalog
                WHERE is_active = TRUE
                ORDER BY service_id
                """
            )
            services = [
                {
                    "service_id": row[0],
                    "service_name": row[1],
                    "scenario_name": row[1],
                    "service_type_id": row[2],
                    "localization_id": row[3],
                    "category_id": row[4],
                    "updated_at": row[5].isoformat() if row[5] else None,
                }
                for row in cursor.fetchall()
            ]

        version_payload = {
            "service_types": service_types,
            "localizations": localizations,
            "categories": categories,
            "services": services,
        }
        catalog_version = hashlib.sha256(
            json.dumps(version_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        default_category_id = next((item["category_id"] for item in categories if item.get("is_default")), None)
        return {
            **version_payload,
            "default_category_id": default_category_id,
            "catalog_version": catalog_version,
            "loaded_at_monotonic": time.monotonic(),
        }

    def _resolve_service_sync(
        self,
        *,
        service_type_id: int,
        localization_id: int,
        category_id: int,
        company_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT service_id, scenario_name
                FROM services_catalog
                WHERE is_active = TRUE
                  AND type_id = %s
                  AND localization_id = %s
                  AND category_id = %s
                ORDER BY service_id
                LIMIT 1
                """,
                [service_type_id, localization_id, category_id],
            )
            row = cursor.fetchone()
            if not row:
                return None
            service_id, scenario_name = row

            route_warning = None
            if company_id:
                cursor.execute(
                    """
                    SELECT id
                    FROM company_service_route
                    WHERE company_id = %s AND service_id = %s AND is_active = TRUE
                    LIMIT 1
                    """,
                    [company_id, service_id],
                )
                if cursor.fetchone() is None:
                    route_warning = "Для компании не найден активный маршрут услуги; заявка будет создана без подразделения."

        return {
            "service_id": service_id,
            "service_name": scenario_name,
            "scenario_name": scenario_name,
            "route_warning": route_warning,
        }


def find_by_id(items: List[Dict[str, Any]], id_key: str, value: Any) -> Optional[Dict[str, Any]]:
    try:
        wanted = int(value)
    except (TypeError, ValueError):
        return None
    return next((item for item in items if int(item.get(id_key)) == wanted), None)


def find_by_name(items: List[Dict[str, Any]], name_key: str, value: str) -> Optional[Dict[str, Any]]:
    normalized = (value or "").strip().lower().replace("ё", "е")
    if not normalized:
        return None
    return next(
        (
            item
            for item in items
            if (item.get(name_key) or "").strip().lower().replace("ё", "е") == normalized
        ),
        None,
    )
