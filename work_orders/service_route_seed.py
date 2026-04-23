from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryDepartmentSeed:
    category_id: int
    department_name: str
    parent_name: str
    is_external: bool


INTERNAL_ROOT_NAME = "Внутренние службы"
EXTERNAL_ROOT_NAME = "Внешние службы"

ASPECT_CATEGORY_DEPARTMENT_SEED = {
    1: CategoryDepartmentSeed(1, "Дворники", INTERNAL_ROOT_NAME, False),
    2: CategoryDepartmentSeed(2, "Сантехники", INTERNAL_ROOT_NAME, False),
    3: CategoryDepartmentSeed(3, "Электрики", INTERNAL_ROOT_NAME, False),
    4: CategoryDepartmentSeed(4, "Газовщики", EXTERNAL_ROOT_NAME, True),
    5: CategoryDepartmentSeed(5, "Вентиляционная специализированная компания", EXTERNAL_ROOT_NAME, True),
    6: CategoryDepartmentSeed(6, "Сочинский ПЖБ", EXTERNAL_ROOT_NAME, True),
    7: CategoryDepartmentSeed(7, "Плотники", INTERNAL_ROOT_NAME, False),
    8: CategoryDepartmentSeed(8, "Лифтерская", EXTERNAL_ROOT_NAME, True),
    9: CategoryDepartmentSeed(9, "Фин.отдел", INTERNAL_ROOT_NAME, False),
    10: CategoryDepartmentSeed(10, "Цифровая трансформация", INTERNAL_ROOT_NAME, False),
    11: CategoryDepartmentSeed(11, "Многофункциональная компания", EXTERNAL_ROOT_NAME, True),
}


def get_seed_for_category(category_id: int) -> CategoryDepartmentSeed | None:
    return ASPECT_CATEGORY_DEPARTMENT_SEED.get(category_id)
