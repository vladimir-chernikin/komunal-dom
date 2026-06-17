from datetime import date
from typing import Optional, Tuple

from django.db.models import Q

from nsi.models import Company
from work_orders.models import CompanyObjectServicePeriod


class ServiceObjectCompanyResolver:
    """Resolves the active company for a service object on a specific date."""

    def resolve(
        self,
        *,
        service_object_id: Optional[int],
        on_date: Optional[date] = None,
    ) -> Tuple[Optional[Company], str, Optional[int]]:
        if not service_object_id:
            return None, "service_object_missing", None

        effective_date = on_date or date.today()
        period = (
            CompanyObjectServicePeriod.objects.select_related("company")
            .filter(
                object_id=service_object_id,
                is_active=True,
                is_test=False,
                date_from__lte=effective_date,
            )
            .filter(Q(date_to__isnull=True) | Q(date_to__gte=effective_date))
            .order_by("-date_from", "company_id")
            .first()
        )
        if period is None:
            return None, "company_object_service_period_missing", None

        return period.company, "company_object_service_period", period.id
