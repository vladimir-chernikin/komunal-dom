"""
Формы для портала

АВТОР: Claude Sonnet
ОБНОВЛЕНО: 2026-04-03
"""
import json

from django import forms
from django.contrib.auth.models import Group, User
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from portal.models import UserProfile
from nsi.models import Company
from work_orders.models import CompanyDepartment
from portal.mixins import get_primary_membership


class AddDepartmentForm(forms.Form):
    """
    Форма добавления подразделения директором ТСЖ
    """

    department_code = forms.CharField(
        label='Код подразделения',
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text='Можно оставить пустым, код будет создан автоматически'
    )

    department_name = forms.CharField(
        label='Название',
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text='Название подразделения'
    )

    parent_department = forms.ChoiceField(
        label='Родительское подразделение',
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Опционально: для создания иерархии'
    )

    def __init__(self, *args, **kwargs):
        departments = kwargs.pop('departments', [])
        super().__init__(*args, **kwargs)

        # Формируем choices для родительского подразделения
        choices = [('', '-- Без родительского подразделения --')]
        for dept in departments:
            choices.append((dept.id, self._department_label(dept)))

        self.fields['parent_department'].choices = choices

    @staticmethod
    def _department_label(department):
        ancestors = []
        parent = getattr(department, 'parent_department', None)
        guard = 0
        while parent and guard < 20:
            ancestors.append(parent.department_name)
            parent = getattr(parent, 'parent_department', None)
            guard += 1
        if ancestors:
            return f"{' / '.join(reversed(ancestors))} / {department.department_name}"
        return department.department_name


class EditDepartmentForm(forms.Form):
    """
    Форма редактирования подразделения директором ТСЖ
    """

    department_code = forms.CharField(
        label='Код подразделения',
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text='Можно оставить пустым, код будет создан автоматически'
    )

    department_name = forms.CharField(
        label='Название',
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text='Название подразделения'
    )

    parent_department = forms.ChoiceField(
        label='Родительское подразделение',
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Опционально: для создания иерархии'
    )

    def __init__(self, *args, **kwargs):
        departments = kwargs.pop('departments', [])
        instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)

        # Формируем choices для родительского подразделения
        choices = [('', '-- Без родительского подразделения --')]
        for dept in departments:
            choices.append((dept.id, AddDepartmentForm._department_label(dept)))

        self.fields['parent_department'].choices = choices


class AddResidentForm(forms.ModelForm):
    """
    Форма добавления жителя директором ТСЖ

    Создает:
    - User в auth_user
    - UserCompanyMembership с role_code='resident'
    """

    # Поля пользователя
    username = forms.CharField(
        label='Логин',
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text='Уникальное имя для входа в систему'
    )

    email = forms.EmailField(
        label='Email',
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )

    first_name = forms.CharField(
        label='Имя',
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    last_name = forms.CharField(
        label='Фамилия',
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    password = forms.CharField(
        label='Пароль',
        required=True,
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        help_text='Минимум 8 символов'
    )

    # Дополнительные поля
    phone = forms.CharField(
        label='Телефон',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+7 (XXX) XXX-XX-XX'})
    )

    address = forms.CharField(
        label='Адрес',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ул. Пример, д. 1, кв. 10'})
    )

    role = forms.ChoiceField(
        label='Роль',
        choices=[
            ('resident', 'Житель'),
            ('executor', 'Исполнитель'),
            ('chief_engineer', 'Главный инженер'),
        ],
        initial='resident',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    notes = forms.CharField(
        label='Заметки',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']

    def clean_username(self):
        """Проверка уникальности username"""
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Пользователь с таким логином уже существует')
        return username

    def clean_password(self):
        """Проверка сложности пароля"""
        password = self.cleaned_data.get('password')
        if len(password) < 8:
            raise forms.ValidationError('Пароль должен быть минимум 8 символов')
        return password


class UserAdminExtraFieldsMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['primary_company'].queryset = self._get_company_queryset()
        self.fields['primary_department'].queryset = CompanyDepartment.objects.none()

        profile = self._get_or_create_profile()
        selected_company_id = None
        department_map = self._build_department_map()

        if profile:
            self.initial.setdefault('profile_job_title', profile.job_title or '')

        if self.is_bound:
            company_value = self.data.get('primary_company')
            if company_value:
                try:
                    selected_company_id = int(company_value)
                except (TypeError, ValueError):
                    selected_company_id = None
        elif profile and profile.primary_company_id:
            selected_company_id = profile.primary_company_id
            self.initial.setdefault('primary_company', profile.primary_company_id)
            self.initial.setdefault('primary_department', profile.primary_department_id)

        if selected_company_id:
            self.fields['primary_department'].queryset = CompanyDepartment.objects.filter(
                company_id=selected_company_id,
                is_active=True,
            ).order_by('department_name')
            self.fields['primary_department'].widget.attrs.pop('disabled', None)
        else:
            self.fields['primary_department'].queryset = CompanyDepartment.objects.none()
            self.fields['primary_department'].widget.attrs['disabled'] = 'disabled'

        self.fields['primary_company'].widget.attrs['data-primary-department-target'] = 'id_primary_department'
        self.fields['primary_company'].widget.attrs['onchange'] = (
            'window.rebuildPrimaryDepartmentOptions && window.rebuildPrimaryDepartmentOptions();'
        )
        self.fields['primary_department'].widget.attrs['data-departments-by-company'] = json.dumps(
            department_map,
            ensure_ascii=False,
        )
        self.fields['primary_department'].widget.attrs['data-initial-value'] = str(
            self.initial.get('primary_department') or ''
        )

    def _get_company_queryset(self):
        from nsi.models import Company
        return Company.objects.filter(is_active=True).order_by('name')

    def _get_or_create_profile(self):
        if not self.instance or not self.instance.pk:
            return None
        profile, _ = UserProfile.objects.get_or_create(
            user=self.instance,
            defaults={'role': 'uk_user'},
        )
        return profile

    def _build_department_map(self):
        result = {}
        departments = CompanyDepartment.objects.filter(
            is_active=True,
        ).order_by('company__name', 'department_name')
        for department in departments:
            result.setdefault(str(department.company_id), []).append({
                'id': department.id,
                'name': department.department_name,
            })
        return result

    def clean(self):
        cleaned_data = super().clean()
        company = cleaned_data.get('primary_company')
        department = cleaned_data.get('primary_department')

        if department and company and department.company_id != company.id:
            self.add_error(
                'primary_department',
                'Подразделение должно принадлежать выбранной основной компании.',
            )
        if department and not company:
            self.add_error(
                'primary_company',
                'Сначала выберите основную компанию.',
            )
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            self.save_profile(user)
        return user

    def save_profile(self, user=None):
        user = user or self.instance
        if not user or not user.pk:
            return None

        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={'role': 'uk_user'},
        )
        profile.primary_company = self.cleaned_data.get('primary_company')
        profile.primary_department = self.cleaned_data.get('primary_department')
        profile.job_title = self.cleaned_data.get('profile_job_title') or None
        profile.save(update_fields=['primary_company', 'primary_department', 'job_title'])
        return profile


class UserAdminAddForm(UserAdminExtraFieldsMixin, UserCreationForm):
    primary_company = forms.ModelChoiceField(
        queryset=Company.objects.none(),
        required=False,
        label='Основная компания',
        help_text='Основная компания пользователя для типового сценария 1-к-1.',
    )
    primary_department = forms.ModelChoiceField(
        queryset=CompanyDepartment.objects.none(),
        required=False,
        label='Основное подразделение',
        help_text='Основное подразделение внутри выбранной основной компании.',
    )
    profile_job_title = forms.ChoiceField(
        choices=[('', 'Не указана')] + [
            (value, label)
            for value, label in UserProfile._meta.get_field('job_title').choices
            if value is not None
        ],
        required=False,
        label='Должность',
        help_text='Должность сотрудника из профиля пользователя.',
    )
    is_active = forms.BooleanField(required=False, initial=True, label='Активен')
    is_staff = forms.BooleanField(required=False, initial=True, label='Доступ в систему')
    is_superuser = forms.BooleanField(required=False, label='Суперпользователь')
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        label='Группы',
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            'username',
            'password1',
            'password2',
            'first_name',
            'last_name',
            'email',
            'is_active',
            'is_staff',
            'is_superuser',
            'groups',
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data.get('first_name', '')
        user.last_name = self.cleaned_data.get('last_name', '')
        user.email = self.cleaned_data.get('email', '')
        user.is_active = self.cleaned_data.get('is_active', True)
        user.is_staff = self.cleaned_data.get('is_staff', True)
        user.is_superuser = self.cleaned_data.get('is_superuser', False)

        if commit:
            user.save()
            self.save_m2m()
            self.save_profile(user)
        return user


class UserAdminChangeForm(UserAdminExtraFieldsMixin, UserChangeForm):
    primary_company = forms.ModelChoiceField(
        queryset=Company.objects.none(),
        required=False,
        label='Основная компания',
        help_text='Основная компания пользователя для типового сценария 1-к-1.',
    )
    primary_department = forms.ModelChoiceField(
        queryset=CompanyDepartment.objects.none(),
        required=False,
        label='Основное подразделение',
        help_text='Основное подразделение внутри выбранной основной компании.',
    )
    profile_job_title = forms.ChoiceField(
        choices=[('', 'Не указана')] + [
            (value, label)
            for value, label in UserProfile._meta.get_field('job_title').choices
            if value is not None
        ],
        required=False,
        label='Должность',
        help_text='Должность сотрудника из профиля пользователя.',
    )

    class Meta(UserChangeForm.Meta):
        model = User
        fields = '__all__'
