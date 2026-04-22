from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nsi.models import Company
from portal.models import ServicesCatalog
from work_orders.models import CompanyDepartment, CompanyRouteMapping
from work_orders.service_route_seed import ASPECT_CATEGORY_DEPARTMENT_SEED


class Command(BaseCommand):
    help = "Создает подразделения и маршруты услуг для ООО УК АСПЕКТ по согласованной карте категорий."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, default=1)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        company_id = options["company_id"]
        dry_run = options["dry_run"]

        company = Company.objects.filter(pk=company_id).first()
        if not company:
            raise CommandError(f"Компания с id={company_id} не найдена.")

        services = list(
            ServicesCatalog.objects
            .filter(is_active=True)
            .select_related("category")
            .order_by("category_id", "scenario_name", "service_id")
        )
        missing_categories = sorted({service.category_id for service in services} - set(ASPECT_CATEGORY_DEPARTMENT_SEED))
        if missing_categories:
            raise CommandError(f"Нет сопоставления для категорий: {missing_categories}")

        root_department, root_created, root_updated = self._get_or_create_department(
            company=company,
            parent=None,
            name="Компания",
            is_external=False,
            dry_run=dry_run,
        )

        parent_cache = {}
        department_cache = {}
        created_departments = int(root_created)
        updated_departments = int(root_updated)
        created_routes = 0
        updated_routes = 0

        with transaction.atomic():
            for service in services:
                seed = ASPECT_CATEGORY_DEPARTMENT_SEED[service.category_id]
                parent = parent_cache.get(seed.parent_name)
                if parent is None:
                    parent, parent_created, parent_updated = self._get_or_create_department(
                        company=company,
                        parent=root_department,
                        name=seed.parent_name,
                        is_external=False,
                        dry_run=dry_run,
                    )
                    parent_cache[seed.parent_name] = parent
                    created_departments += int(parent_created)
                    updated_departments += int(parent_updated)

                department_key = (seed.parent_name, seed.department_name)
                department = department_cache.get(department_key)
                if department is None:
                    department, department_created, department_updated = self._get_or_create_department(
                        company=company,
                        parent=parent,
                        name=seed.department_name,
                        is_external=seed.is_external,
                        dry_run=dry_run,
                    )
                    department_cache[department_key] = department
                    created_departments += int(department_created)
                    updated_departments += int(department_updated)

                route = self._get_legacy_route(seed.legacy_route_code)
                mapping = CompanyRouteMapping.objects.filter(company=company, service=service).first()
                if mapping:
                    changed = (
                        mapping.target_department_id != department.id
                        or mapping.route_id != route.id
                        or not mapping.is_active
                        or mapping.is_test
                    )
                    if changed and not dry_run:
                        mapping.target_department = department
                        mapping.route = route
                        mapping.is_active = True
                        mapping.is_test = False
                        mapping.save(update_fields=["target_department", "route", "is_active", "is_test", "updated_at"])
                    updated_routes += int(changed)
                else:
                    if not dry_run:
                        CompanyRouteMapping.objects.create(
                            company=company,
                            service=service,
                            route=route,
                            target_department=department,
                            is_active=True,
                            is_test=False,
                        )
                    created_routes += 1

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f"{company.name}: услуг обработано {len(services)}, "
            f"маршрутов создано {created_routes}, обновлено {updated_routes}, "
            f"подразделений создано {created_departments}, обновлено {updated_departments}."
        ))

    def _get_or_create_department(self, *, company, parent, name, is_external, dry_run):
        department = CompanyDepartment.objects.filter(
            company=company,
            parent_department=parent,
            department_name=name,
        ).first()
        if department:
            if department.is_external != is_external:
                if not dry_run:
                    department.is_external = is_external
                    department.save(update_fields=["is_external", "updated_at"])
                return department, False, True
            return department, False, False

        code = CompanyDepartment.generate_department_code(company.id, name)
        if dry_run:
            department = CompanyDepartment(
                company=company,
                parent_department=parent,
                department_name=name,
                department_code=code,
                is_external=is_external,
                is_active=True,
                is_test=False,
            )
            department.id = -abs(hash((company.id, parent.id if parent else None, name)) % 1000000)
            return department, True, False

        return CompanyDepartment.objects.create(
            company=company,
            parent_department=parent,
            department_name=name,
            department_code=code,
            is_external=is_external,
            is_active=True,
            is_test=False,
        ), True, False

    def _get_legacy_route(self, route_code):
        from work_orders.models import RouteRef

        route = RouteRef.objects.filter(route_code=route_code, is_active=True).first()
        if not route:
            raise CommandError(f"Типовой маршрут {route_code} не найден.")
        return route
