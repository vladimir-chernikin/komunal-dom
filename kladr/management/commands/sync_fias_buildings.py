from django.core.management.base import BaseCommand

from kladr.fias_service import FiasAddressService
from kladr.models import Building


class Command(BaseCommand):
    help = "Synchronize local buildings with FIAS house identifiers."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--only-unmapped", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        service = FiasAddressService()
        if not service.is_configured:
            self.stderr.write(self.style.ERROR("FIAS_API_TOKEN is not configured"))
            return

        queryset = Building.objects.select_related(
            "address_object__type",
            "address_object__parent__type",
            "address_object__parent__parent__type",
        ).order_by("id")
        if options["only_unmapped"]:
            queryset = queryset.filter(fias_object_guid__isnull=True)
        if options["limit"]:
            queryset = queryset[: options["limit"]]

        total = 0
        matched = 0
        missing = 0

        for building in queryset:
            total += 1
            full_address = building.get_full_address()
            item = service.resolve_building_match(full_address, expected_house_number=building.house_number)
            if not item:
                missing += 1
                self.stdout.write(self.style.WARNING(f"NO MATCH [{building.id}] {full_address}"))
                continue

            matched += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"MATCH [{building.id}] {full_address} -> "
                    f"{item.get('object_id')} / {item.get('object_guid')} / level={item.get('object_level_id')}"
                )
            )
            if not options["dry_run"]:
                service.bind_building_mapping(building, item)

        self.stdout.write(
            self.style.NOTICE(
                f"Processed: {total}, matched: {matched}, missing: {missing}"
            )
        )
