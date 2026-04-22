from __future__ import annotations

from dataclasses import dataclass

from .models import RouteRef


@dataclass(frozen=True)
class CategoryDepartmentSeed:
    category_id: int
    department_name: str
    parent_name: str
    is_external: bool
    legacy_route_code: str


INTERNAL_ROOT_NAME = "Внутренние службы"
EXTERNAL_ROOT_NAME = "Внешние службы"

ASPECT_CATEGORY_DEPARTMENT_SEED = {
    1: CategoryDepartmentSeed(1, "Дворники", INTERNAL_ROOT_NAME, False, "plumbing"),
    2: CategoryDepartmentSeed(2, "Сантехники", INTERNAL_ROOT_NAME, False, "plumbing"),
    3: CategoryDepartmentSeed(3, "Электрики", INTERNAL_ROOT_NAME, False, "electricity"),
    4: CategoryDepartmentSeed(4, "Газовщики", EXTERNAL_ROOT_NAME, True, "gas"),
    5: CategoryDepartmentSeed(5, "Вентиляционная специализированная компания", EXTERNAL_ROOT_NAME, True, "plumbing"),
    6: CategoryDepartmentSeed(6, "Сочинский ПЖБ", EXTERNAL_ROOT_NAME, True, "emergency"),
    7: CategoryDepartmentSeed(7, "Плотники", INTERNAL_ROOT_NAME, False, "plumbing"),
    8: CategoryDepartmentSeed(8, "Лифтерская", EXTERNAL_ROOT_NAME, True, "elevator"),
    9: CategoryDepartmentSeed(9, "Фин.отдел", INTERNAL_ROOT_NAME, False, "plumbing"),
    10: CategoryDepartmentSeed(10, "Цифровая трансформация", INTERNAL_ROOT_NAME, False, "plumbing"),
    11: CategoryDepartmentSeed(11, "Многофункциональная компания", EXTERNAL_ROOT_NAME, True, "plumbing"),
}


def get_seed_for_category(category_id: int) -> CategoryDepartmentSeed | None:
    return ASPECT_CATEGORY_DEPARTMENT_SEED.get(category_id)


def get_legacy_route_for_service(service):
    seed = get_seed_for_category(service.category_id)
    route_code = seed.legacy_route_code if seed else "plumbing"
    return RouteRef.objects.filter(route_code=route_code).first()
