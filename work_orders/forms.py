from django import forms

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

        selected_object_id = (
            self.data.get('object')
            or self.initial.get('object')
            or getattr(self.instance, 'object_id', None)
        )

        if selected_object_id:
            self.fields['object'].queryset = ServiceObject.objects.filter(pk=selected_object_id, is_active=True)
            selected_object = self.fields['object'].queryset.first()
            if selected_object:
                self.selected_object_label = selected_object.get_search_label()

    def clean_object(self):
        service_object = self.cleaned_data['object']
        if not service_object.is_active:
            raise forms.ValidationError('Выбранный объект недоступен для создания заявки.')
        return service_object
