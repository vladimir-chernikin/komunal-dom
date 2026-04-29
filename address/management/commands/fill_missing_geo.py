from django.core.management.base import BaseCommand
from timezonefinder import TimezoneFinder

from address.geocoding import NominatimGeocoder
from address.models import Building


class Command(BaseCommand):
    help = "Fill missing geo_lat/geo_lon/timezone for address.building via Nominatim"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        geocoder = NominatimGeocoder()
        tf = TimezoneFinder()
        queryset = Building.objects.filter(geo_lat__isnull=True, geo_lon__isnull=True).order_by("id")[: options["limit"]]
        processed = 0
        for building in queryset:
            result = geocoder.geocode(building.full_address)
            if not result:
                continue
            building.geo_lat = result.lat
            building.geo_lon = result.lon
            try:
                building.timezone = tf.timezone_at(lat=float(result.lat), lng=float(result.lon))
            except Exception:
                pass
            building.save(update_fields=["geo_lat", "geo_lon", "timezone", "updated_at"])
            processed += 1
        self.stdout.write(self.style.SUCCESS(f"Updated buildings: {processed}"))
