from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from work_orders.models import CompanyObjectServicePeriod


@dataclass
class AssignCompanyResult:
    period: CompanyObjectServicePeriod
    previous_period: Optional[CompanyObjectServicePeriod]
    created: bool


class ServiceObjectCompanyPeriodService:
    """Single entry point for assigning a company to a service object by date."""

    def validate_assignment_start(
        self,
        *,
        object_id: int,
        date_from: date,
        exclude_period_id: Optional[int] = None,
        is_test: bool = False,
    ) -> None:
        if not object_id:
            raise ValidationError("Нужно указать объект обслуживания.")
        if not date_from:
            raise ValidationError("Нужно указать дату начала обслуживания.")

        base_qs = CompanyObjectServicePeriod.objects.filter(
            object_id=object_id,
            is_active=True,
            is_test=is_test,
        )
        if exclude_period_id:
            base_qs = base_qs.exclude(pk=exclude_period_id)

        current_open = base_qs.filter(date_to__isnull=True).order_by("-date_from", "-id").first()
        excluded_ids = []
        if current_open:
            if date_from <= current_open.date_from:
                raise ValidationError(
                    "Новая дата начала должна быть позже даты начала текущего открытого периода."
                )
            excluded_ids.append(current_open.pk)

        overlap_qs = base_qs.exclude(pk__in=excluded_ids)
        overlap_exists = (
            overlap_qs
            .filter(date_from__lte=date.max)
            .filter(Q(date_to__isnull=True) | Q(date_to__gte=date_from))
            .exists()
        )
        if overlap_exists:
            raise ValidationError(
                "Новая дата начала пересекается с уже существующим периодом обслуживания этого объекта."
            )

    def validate_period(
        self,
        *,
        object_id: int,
        company_id: int,
        date_from: date,
        date_to: Optional[date] = None,
        exclude_period_id: Optional[int] = None,
        is_active: bool = True,
        is_test: bool = False,
    ) -> None:
        if not object_id:
            raise ValidationError("Нужно указать объект обслуживания.")
        if not company_id:
            raise ValidationError("Нужно указать компанию.")
        if not date_from:
            raise ValidationError("Нужно указать дату начала обслуживания.")
        if date_to and date_to < date_from:
            raise ValidationError("Дата окончания не может быть раньше даты начала.")

        base_qs = CompanyObjectServicePeriod.objects.filter(object_id=object_id)
        if exclude_period_id:
            base_qs = base_qs.exclude(pk=exclude_period_id)

        if is_active and not is_test and date_to is None:
            if base_qs.filter(is_active=True, is_test=False, date_to__isnull=True).exists():
                raise ValidationError(
                    "У объекта уже есть открытый активный период обслуживания. "
                    "Сначала закройте его или используйте смену компании через новую дату."
                )

        period_end = date_to or date.max
        overlap_exists = (
            base_qs.filter(is_active=is_active, is_test=is_test)
            .filter(date_from__lte=period_end)
            .filter(Q(date_to__isnull=True) | Q(date_to__gte=date_from))
            .exists()
        )
        if overlap_exists:
            raise ValidationError("Новый период пересекается с уже существующим периодом обслуживания этого объекта.")

    @transaction.atomic
    def assign_company(
        self,
        *,
        object_id: int,
        company_id: int,
        date_from: date,
        comment: Optional[str] = None,
        is_test: bool = False,
    ) -> AssignCompanyResult:
        periods_qs = (
            CompanyObjectServicePeriod.objects.select_for_update()
            .select_related("company", "object")
            .filter(object_id=object_id, is_active=True, is_test=is_test)
        )

        current_open = periods_qs.filter(date_to__isnull=True).order_by("-date_from", "-id").first()

        if current_open and current_open.company_id == company_id and current_open.date_from == date_from:
            if comment and current_open.comment != comment:
                current_open.comment = comment
                current_open.save(update_fields=["comment", "updated_at"])
            return AssignCompanyResult(period=current_open, previous_period=None, created=False)

        previous_period = None
        if current_open:
            self.validate_assignment_start(
                object_id=object_id,
                date_from=date_from,
                is_test=is_test,
            )
            previous_period = current_open
            current_open.date_to = date_from - timedelta(days=1)
            current_open.save(update_fields=["date_to", "updated_at"])

        self.validate_period(
            object_id=object_id,
            company_id=company_id,
            date_from=date_from,
            date_to=None,
            exclude_period_id=None,
            is_active=True,
            is_test=is_test,
        )

        new_period = CompanyObjectServicePeriod.objects.create(
            object_id=object_id,
            company_id=company_id,
            date_from=date_from,
            date_to=None,
            comment=comment,
            is_active=True,
            is_test=is_test,
        )
        return AssignCompanyResult(period=new_period, previous_period=previous_period, created=True)
