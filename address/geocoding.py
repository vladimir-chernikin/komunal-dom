from dataclasses import dataclass
from decimal import Decimal
from time import sleep
from typing import Optional

import httpx
from decouple import config


@dataclass
class GeocodeResult:
    lat: Decimal
    lon: Decimal
    timezone: Optional[str] = None


class NominatimGeocoder:
    def __init__(self):
        self.base_url = config("NOMINATIM_BASE_URL", default="https://nominatim.openstreetmap.org")
        self.user_agent = config("NOMINATIM_USER_AGENT", default="komunal-dom/1.0 admin geocoder")
        self.timeout = float(config("NOMINATIM_TIMEOUT", default="20"))
        self.sleep_seconds = max(float(config("NOMINATIM_SLEEP_SECONDS", default="1.0")), 1.0)

    def geocode(self, address: str) -> Optional[GeocodeResult]:
        if not address:
            return None
        sleep(self.sleep_seconds)
        with httpx.Client(timeout=self.timeout, headers={"User-Agent": self.user_agent}) as client:
            response = client.get(f"{self.base_url.rstrip('/')}/search", params={"q": address, "format": "jsonv2", "limit": 1})
            response.raise_for_status()
            payload = response.json() or []
        if not payload:
            return None
        item = payload[0]
        return GeocodeResult(lat=Decimal(str(item["lat"])), lon=Decimal(str(item["lon"])), timezone=None)
