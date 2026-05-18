from django import forms
import re

from portal.models import ServiceObject, ServicesCatalog

from .models import WorkOrder


class WorkOrderCreateForm(forms.ModelForm):
    """Форма ручного создания заявки с адресным выбором объекта."""

    object = forms.ModelChoiceField(
        queryset=ServiceObject.objects.none(),
        widget=forms.HiddenInput(),
        label="Объект обслуживания",
    )

    class Meta:
        model = WorkOrder
        fields = ['object', 'service', 'original_request_text', 'priority_code', 'is_emergency']
        widgets = {
            'service': forms.Select(attrs={'class': 'form-select'}),
            'original_request_text': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'priority_code': forms.Select(attrs={'class': 'form-select'}),
            'is_emergency': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        self.fields['service'].queryset = ServicesCatalog.objects.filter(is_active=True).order_by('category_name', 'scenario_name')
        self.selected_object_label = ''
        profile_address = self._get_profile_address()

        selected_object_id = (
            self.data.get('object')
            or self.initial.get('object')
            or getattr(self.instance, 'object_id', None)
        )

        if not self.is_bound and not selected_object_id:
            profile_object = self._resolve_profile_address_object(profile_address)
            if profile_object:
                selected_object_id = profile_object.pk
                self.initial['object'] = profile_object.pk

        if selected_object_id:
            self.fields['object'].queryset = self._get_company_scoped_objects().filter(pk=selected_object_id)
            selected_object = self.fields['object'].queryset.first()
            if selected_object:
                self.selected_object_label = selected_object.get_search_label()
        elif profile_address:
            self.selected_object_label = profile_address

    def _get_profile_address(self):
        if not self.user or not getattr(self.user, 'is_authenticated', False):
            return ''
        profile = getattr(self.user, 'userprofile', None)
        return (getattr(profile, 'address', '') or '').strip()

    def _resolve_profile_address_object(self, profile_address):
        if not profile_address:
            return None

        object_id = self._extract_service_object_id(profile_address)
        if object_id:
            return self._get_company_scoped_objects().filter(pk=object_id).first()

        from portal.models import search_service_objects
        matches = list(search_service_objects(profile_address, queryset=self._get_company_scoped_objects(), limit=2))
        if len(matches) == 1:
            return matches[0]
        return None

    def _get_company_scoped_objects(self):
        if not self.user or not getattr(self.user, 'is_authenticated', False):
            return ServiceObject.objects.none()
        if self.user.is_superuser:
            return ServiceObject.objects.filter(is_active=True)

        from portal.mixins import get_user_scope
        from .models import CompanyObjectServicePeriod

        scope = get_user_scope(self.user)
        primary_membership = scope.get('primary_membership')
        company_ids = []
        if primary_membership:
            company_ids = [primary_membership.company_id]
        else:
            company_ids = list(scope.get('company_ids') or [])

        if not company_ids:
            return ServiceObject.objects.none()

        object_ids = CompanyObjectServicePeriod.objects.filter(
            company_id__in=company_ids,
            is_active=True,
        ).values_list('object_id', flat=True).distinct()

        return ServiceObject.objects.filter(
            service_object_id__in=object_ids,
            is_active=True,
        )

    @staticmethod
    def _extract_service_object_id(profile_address):
        patterns = (
            r'\[объект\s*(\d+)\]',
            r'объект\s*#?\s*(\d+)',
            r'id\s*объекта\s*#?\s*(\d+)',
        )
        lowered = profile_address.lower()
        for pattern in patterns:
            match = re.search(pattern, lowered, flags=re.IGNORECASE)
            if match:
                return int(match.group(1))
        if profile_address.strip().isdigit():
            return int(profile_address.strip())
        return None

    def clean_object(self):
        service_object = self.cleaned_data['object']
        if not service_object.is_active:
            raise forms.ValidationError('Выбранный объект недоступен для создания заявки.')
        if not self._get_company_scoped_objects().filter(pk=service_object.pk).exists():
            raise forms.ValidationError('Выбранный объект не относится к вашей компании.')
        return service_object
