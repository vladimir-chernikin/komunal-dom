# -*- coding: utf-8 -*-
"""
Административные представления для портала

РђР'РўРћР : Claude Sonnet
ОБНОВЛЕНО: 2026-04-02
ИЗМЕНЕНИЯ:
- Использование UserCompanyMembership вместо UserProfile.role
- Использование mixins для контроля доступа
- Фильтрация по company_id
"""
from io import BytesIO
from pathlib import Path

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.utils import timezone
from openpyxl import load_workbook

from portal.models import UserProfile, AIPrompt, ServiceObject
from portal.mixins import get_primary_membership, get_role_dashboard_url
from file_manager.models import UserFile

# Импорты для КЛАДР статистики
try:
    from kladr.models import KladrAddressObject, Building, ServiceArea
    from kladr.fias_service import FiasAddressService
    KLADR_AVAILABLE = True
except ImportError:
    KLADR_AVAILABLE = False


def _workspace_context(request, membership):
    if request.user.is_superuser and not membership:
        return {
            'company': {'name': 'Все компании'},
            'department': None,
            'user_role': 'superuser',
            'company_scope': None,
        }

    return {
        'company': membership.company,
        'department': membership.department,
        'user_role': membership.role_code,
        'company_scope': getattr(request, 'user_company_ids', None) or [membership.company_id],
    }


def _get_manager_workspace(request, allowed_roles=('direktor_uk', 'chief_engineer')):
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            return None, _workspace_context(request, membership), None
        messages.warning(request, 'Вы не привязаны к компании')
        return None, None, redirect('portal:no_membership')

    if not request.user.is_superuser and membership.role_code not in allowed_roles:
        messages.error(request, 'Доступ запрещен')
        return membership, None, redirect('portal:welcome')

    return membership, _workspace_context(request, membership), None


def _build_scoped_company_object_queryset(company_scope):
    from work_orders.models import CompanyObjectServicePeriod

    periods = CompanyObjectServicePeriod.objects.filter(is_active=True)
    if company_scope:
        if isinstance(company_scope, (list, tuple, set)):
            periods = periods.filter(company_id__in=company_scope)
        else:
            periods = periods.filter(company_id=company_scope)

    object_ids = periods.values_list('object_id', flat=True).distinct()
    return ServiceObject.objects.filter(service_object_id__in=object_ids, is_active=True).order_by('service_object_id')


def _get_or_create_kladr_type(level, short_name, type_name):
    from kladr.models import KladrObjectType

    short_name = (short_name or '').strip() or f'СѓСЂ.{level}'
    type_name = (type_name or '').strip() or f'Уровень {level}'
    type_code = f'fias_{level}_{short_name}'.lower().replace(' ', '_').replace('.', '').replace('-', '_')

    obj = KladrObjectType.objects.filter(level=level, short_name=short_name).first()
    if obj:
        return obj

    obj, _ = KladrObjectType.objects.get_or_create(
        code=type_code[:10],
        defaults={
            'name': type_name[:100],
            'level': level,
            'short_name': short_name[:20],
        }
    )
    if obj.level != level or obj.short_name != short_name:
        obj.level = level
        obj.short_name = short_name[:20]
        obj.name = type_name[:100]
        obj.save(update_fields=['name', 'level', 'short_name'])
    return obj


def _map_fias_hierarchy_level(item):
    object_type = (item.get('object_type') or '').lower()
    type_name = (item.get('type_name') or '').lower()
    level_id = item.get('object_level_id')

    if object_type == 'region' or level_id == 1:
        return 1
    if 'район' in type_name or level_id in {3, 4}:
        return 2
    if 'РіРѕСЂРѕРґ' in type_name or level_id == 5:
        return 3
    if level_id in {6, 7} or any(token in type_name for token in ('посел', 'село', 'деревн', 'территория', 'квартал', 'микрорайон')):
        return 4
    return 5


def _ensure_address_object_chain_from_fias(hierarchy, user):
    parent = None
    street_object = None

    for item in hierarchy:
        if (item.get('object_type') or '').lower() == 'house':
            continue

        kladr_level = _map_fias_hierarchy_level(item)
        obj_type = _get_or_create_kladr_type(
            kladr_level,
            item.get('type_short_name'),
            item.get('type_name'),
        )
        code = item.get('kladr_code') or f"FIAS{item.get('object_id')}"
        address_object = KladrAddressObject.objects.filter(
            Q(fias_object_id=item.get('object_id')) | Q(code=code)
        ).first()
        if address_object is None:
            address_object = KladrAddressObject.objects.create(
                name=(item.get('name') or item.get('full_name') or code)[:255],
                type=obj_type,
                code=code[:20],
                parent=parent,
                fias_object_id=item.get('object_id'),
                fias_object_guid=item.get('object_guid'),
                fias_level_id=item.get('object_level_id'),
                fias_address_type=item.get('address_type'),
                zip_code=(item.get('postal_code') or item.get('zip_code') or '')[:6] or None,
                okato=(item.get('okato') or '')[:11] or None,
                oktmo=(item.get('oktmo') or '')[:11] or None,
                is_active=True,
                created_by=user,
            )
        else:
            updated = False
            new_name = (item.get('name') or item.get('full_name') or address_object.name)[:255]
            if address_object.name != new_name:
                address_object.name = new_name
                updated = True
            if address_object.type_id != obj_type.id:
                address_object.type = obj_type
                updated = True
            if address_object.parent_id != getattr(parent, 'id', None):
                address_object.parent = parent
                updated = True
            for field_name, value in (
                ('fias_object_id', item.get('object_id')),
                ('fias_object_guid', item.get('object_guid')),
                ('fias_level_id', item.get('object_level_id')),
                ('fias_address_type', item.get('address_type')),
            ):
                if getattr(address_object, field_name) != value:
                    setattr(address_object, field_name, value)
                    updated = True
            if updated:
                address_object.save()

        parent = address_object
        street_object = address_object

    return street_object


def _extract_import_rows(uploaded_file):
    extension = Path(uploaded_file.name).suffix.lower()
    binary = uploaded_file.read()

    if extension in {'.xlsx', '.xlsm'}:
        workbook = load_workbook(filename=BytesIO(binary), data_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
    else:
        try:
            import pandas as pd
        except Exception as exc:
            raise ValueError('Формат XLS не поддержан на сервере. Загрузите XLSX.') from exc

        try:
            dataframe = pd.read_excel(BytesIO(binary))
        except Exception as exc:
            raise ValueError('Не удалось прочитать файл. Для загрузки используйте XLSX.') from exc

        rows = [tuple(dataframe.columns.tolist())]
        rows.extend(tuple(row) for row in dataframe.itertuples(index=False, name=None))

    if not rows:
        return []

    headers = [str(value).strip().lower() if value is not None else '' for value in rows[0]]
    data_rows = rows[1:]
    address_idx = None
    for candidate in ('адрес', 'address', 'объект', 'объект обслуживания'):
        if candidate in headers:
            address_idx = headers.index(candidate)
            break

    extracted_rows = []
    if address_idx is not None:
        for row_number, row in enumerate(data_rows, start=2):
            address = str(row[address_idx]).strip() if address_idx < len(row) and row[address_idx] is not None else ''
            if address:
                extracted_rows.append({'row_number': row_number, 'address': address})
        return extracted_rows

    column_map = {name: headers.index(name) for name in headers}

    def first_existing_index(*names):
        for name in names:
            if name in column_map:
                return column_map[name]
        return None

    street_idx = first_existing_index('улица', 'street')
    house_idx = first_existing_index('дом', 'house', 'номер дома')
    city_idx = first_existing_index('РіРѕСЂРѕРґ', 'city')
    region_idx = first_existing_index('регион', 'region')

    for row_number, row in enumerate(data_rows, start=2):
        parts = []
        if region_idx is not None and region_idx < len(row) and row[region_idx]:
            parts.append(str(row[region_idx]).strip())
        if city_idx is not None and city_idx < len(row) and row[city_idx]:
            parts.append(str(row[city_idx]).strip())
        if street_idx is not None and street_idx < len(row) and row[street_idx]:
            parts.append(str(row[street_idx]).strip())
        if house_idx is not None and house_idx < len(row) and row[house_idx]:
            parts.append(f"РґРѕРј {str(row[house_idx]).strip()}")
        address = ', '.join(part for part in parts if part)
        if address:
            extracted_rows.append({'row_number': row_number, 'address': address})

    return extracted_rows


@transaction.atomic
def _import_service_object_for_company(address, company, user):
    from work_orders.models import CompanyObjectServicePeriod
    from address_extractor_service import AddressExtractor

    if not KLADR_AVAILABLE:
        raise ValueError('Подсистема КЛАДР недоступна.')

    service = FiasAddressService()
    if not service.is_configured:
        raise ValueError('Не настроен FIAS_API_TOKEN.')

    extractor = AddressExtractor()
    components = extractor.extract_address_components(address)
    validation = extractor.validate_and_match_to_db(components)

    service_object = None
    building = None
    fias_item = {}

    if validation.get('service_object_id'):
        service_object = ServiceObject.objects.filter(
            service_object_id=validation['service_object_id'],
            is_active=True,
        ).first()

    if validation.get('building_id'):
        building = Building.objects.filter(pk=validation['building_id']).first()

    if validation.get('fias_object_id'):
        try:
            fias_item = service.get_address_item_by_id(validation['fias_object_id'])
        except Exception:
            fias_item = {}

    if not fias_item:
        fias_item = service.resolve_building_match(address)
    if not fias_item:
        candidates = [item for item in service.search_address_items(address) if item.get('object_level_id') == 10]
        if candidates:
            fias_item = candidates[0]
    if not fias_item:
        raise ValueError('Адрес не найден в ФИАС.')

    if fias_item.get('object_level_id') != 10:
        object_id = fias_item.get('object_id')
        if object_id:
            resolved = service.get_address_item_by_id(object_id)
            if resolved and resolved.get('object_level_id') == 10:
                fias_item = resolved
    if fias_item.get('object_level_id') != 10:
        raise ValueError('ФИАС не вернул уровень дома по указанному адресу.')

    fias_house_id = fias_item.get('object_id')
    if not fias_house_id:
        raise ValueError('У адреса отсутствует FIAS ID дома.')

    if service_object is None:
        service_object = (
            ServiceObject.objects
            .filter(fias_house_object_id=fias_house_id, unit_id__isnull=True, is_active=True)
            .order_by('service_object_id')
            .first()
        )

    if service_object is None:
        hierarchy = fias_item.get('hierarchy') or []
        street_object = _ensure_address_object_chain_from_fias(hierarchy, user)
        if street_object is None:
            raise ValueError('Не удалось сформировать адресную иерархию для дома.')

        house_entry = next((item for item in hierarchy if (item.get('object_type') or '').lower() == 'house'), None)
        house_number = (
            (house_entry or {}).get('number')
            or ((house_entry or {}).get('full_name') or '').replace('РґРѕРј', '').replace('Рґ.', '').strip()
        )
        if not house_number:
            raise ValueError('Не удалось определить номер дома из ответа ФИАС.')

        if building is None:
            building = Building.objects.filter(fias_object_id=fias_house_id).first()
        if building is None:
            building = Building.objects.filter(address_object=street_object, house_number=house_number).first()
        if building is None:
            building = Building.objects.create(
                address_object=street_object,
                house_number=house_number[:20],
                building_type='',
                has_elevator=False,
                fias_object_id=fias_item.get('object_id'),
                fias_object_guid=fias_item.get('object_guid'),
                fias_level_id=fias_item.get('object_level_id'),
                fias_address_type=fias_item.get('address_type'),
                fias_full_name=fias_item.get('full_name'),
                created_by=user,
            )
        else:
            changed = False
            for field_name, value in (
                ('fias_object_id', fias_item.get('object_id')),
                ('fias_object_guid', fias_item.get('object_guid')),
                ('fias_level_id', fias_item.get('object_level_id')),
                ('fias_address_type', fias_item.get('address_type')),
                ('fias_full_name', fias_item.get('full_name')),
            ):
                if getattr(building, field_name) != value:
                    setattr(building, field_name, value)
                    changed = True
            if changed:
                building.save()

        service_object = ServiceObject.objects.create(
            building_id=building.id,
            unit_id=None,
            created_at=timezone.now(),
            is_active=True,
            fias_house_object_id=fias_house_id,
        )

    today = timezone.localdate()
    existing_binding = CompanyObjectServicePeriod.objects.select_related('company').filter(
        object_id=service_object.service_object_id,
        is_active=True,
        date_from__lte=today,
    ).filter(Q(date_to__isnull=True) | Q(date_to__gte=today)).order_by('-date_from').first()
    if existing_binding:
        same_company = existing_binding.company_id == company.id
        message = (
            'Объект уже привязан к вашей компании.'
            if same_company
            else f'Объект уже привязан к компании "{existing_binding.company.name}".'
        )
        return {
            'status': 'skipped',
            'service_object': service_object,
            'binding': existing_binding,
            'fias_house_object_id': fias_house_id,
            'message': message,
        }

    binding = CompanyObjectServicePeriod.objects.create(
        company=company,
        object_id=service_object.service_object_id,
        date_from=today,
        comment='Загружено из кабинета руководителя',
        is_active=True,
    )
    return {
        'status': 'created',
        'service_object': service_object,
        'binding': binding,
        'fias_house_object_id': fias_house_id,
        'message': 'Объект загружен и привязан к компании.',
    }


@login_required
def admin_page(request):
    """
    Главная страница административного интерфейса УК

    ДОСТУП: direktor_uk, django_admin (через middleware будет редирект для non-superuser)
    """
    # Проверка staff
    if not request.user.is_staff:
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:welcome')

    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Фильтрация по компании
    company_scope = workspace['company_scope']

    # Статистика по пользователям компании
    from work_orders.models import UserCompanyMembership

    user_stats = get_user_statistics(company_scope)

    scoped_objects = _build_scoped_company_object_queryset(company_scope)
    from work_orders.models import CompanyObjectServicePeriod
    scoped_bindings = CompanyObjectServicePeriod.objects.filter(is_active=True)
    if company_scope:
        if isinstance(company_scope, (list, tuple, set)):
            scoped_bindings = scoped_bindings.filter(company_id__in=company_scope)
        else:
            scoped_bindings = scoped_bindings.filter(company_id=company_scope)

    context = {
        'company': workspace['company'],
        'department': workspace['department'],
        'user_role': workspace['user_role'],
        'total_users': user_stats['total'],
        'django_admin_count': user_stats['by_role'].get('Django администратор', 0),
        'director_count': user_stats['by_role'].get('Директор УК', 0),
        'chief_engineer_count': user_stats['by_role'].get('Главный инженер', 0),
        'executor_count': user_stats['by_role'].get('Исполнитель', 0),
        'resident_count': user_stats['by_role'].get('Житель', 0),
        'user_stats': user_stats,
        'file_stats': get_file_statistics(company_scope),
        'prompt_stats': get_prompt_statistics(),
        'kladr_stats': get_kladr_statistics() if KLADR_AVAILABLE else {},
    }

    return render(request, 'portal/admin_page.html', context)


@login_required
def director_page(request):
    """
    Отдельная страница для Директора УК

    ДОСТУП: direktor_uk (ограничение через DirectorMixin в Class-Based Views)
    """
    # Проверка staff
    if not request.user.is_staff:
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:welcome')

    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Проверка роли
    if not request.user.is_superuser and membership.role_code != 'direktor_uk':
        messages.error(request, 'Доступ разрешен только Директорам УК')
        return redirect('portal:welcome')

    # Фильтрация по компании
    company_scope = workspace['company_scope']

    # Статистика по пользователям компании
    user_stats = get_user_statistics(company_scope)
    scoped_objects = _build_scoped_company_object_queryset(company_scope)
    from work_orders.models import CompanyObjectServicePeriod
    scoped_bindings = CompanyObjectServicePeriod.objects.filter(is_active=True)
    if company_scope:
        if isinstance(company_scope, (list, tuple, set)):
            scoped_bindings = scoped_bindings.filter(company_id__in=company_scope)
        else:
            scoped_bindings = scoped_bindings.filter(company_id=company_scope)

    context = {
        'company': workspace['company'],
        'department': workspace['department'],
        'user_role': workspace['user_role'],
        'total_users': user_stats['total'],
        'django_admin_count': user_stats['by_role'].get('Django администратор', 0),
        'director_count': user_stats['by_role'].get('Директор УК', 0),
        'chief_engineer_count': user_stats['by_role'].get('Главный инженер', 0),
        'executor_count': user_stats['by_role'].get('Исполнитель', 0),
        'resident_count': user_stats['by_role'].get('Житель', 0),
        'user_stats': user_stats,
        'file_stats': get_file_statistics(company_scope),
        'prompt_stats': get_prompt_statistics(),
        'kladr_stats': get_kladr_statistics() if KLADR_AVAILABLE else {},
        'total_work_orders': 0,  # TODO: получить из WorkOrder
        'active_work_orders': 0,  # TODO: получить из WorkOrder
        'service_object_count': scoped_objects.count(),
        'service_binding_count': scoped_bindings.count(),
    }

    return render(request, 'portal/director_page.html', context)


@login_required
def chief_engineer_page(request):
    """
    Страница Главного инженера

    ДОСТУП: chief_engineer
    РџР РђР'Рђ:
    - Видит всю компанию (все подразделения)
    - Может перераспределять обращения
    - Может переводить в статус "on_hold"
    - Может переоткрывать из completed
    """

    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Проверка роли
    if not request.user.is_superuser and membership.role_code != 'chief_engineer':
        messages.error(request, 'Доступ разрешен только Главным инженерам')
        return redirect('portal:welcome')

    # Фильтрация по компании
    company_scope = workspace['company_scope']

    # Статистика по пользователям компании
    user_stats = get_user_statistics(company_scope)

    scoped_objects = _build_scoped_company_object_queryset(company_scope)
    from work_orders.models import CompanyObjectServicePeriod
    scoped_bindings = CompanyObjectServicePeriod.objects.filter(is_active=True)
    if company_scope:
        if isinstance(company_scope, (list, tuple, set)):
            scoped_bindings = scoped_bindings.filter(company_id__in=company_scope)
        else:
            scoped_bindings = scoped_bindings.filter(company_id=company_scope)

    context = {
        'company': workspace['company'],
        'department': workspace['department'],
        'user_role': workspace['user_role'],
        'total_users': user_stats['total'],
        'executor_count': user_stats['by_role'].get('Исполнитель', 0),
        'chief_engineer_count': user_stats['by_role'].get('Главный инженер', 0),
        'user_stats': user_stats,
        'service_object_count': scoped_objects.count(),
        'service_binding_count': scoped_bindings.count(),
    }

    return render(request, 'portal/chief_engineer_page.html', context)


def get_user_statistics(company_scope=None):
    """
    Получить статистику по пользователям

    ПАРАМЕТРЫ:
    - company_scope: int или список company_id для фильтрации
    """
    from work_orders.models import UserCompanyMembership

    memberships = UserCompanyMembership.objects.filter(is_active=True)

    if company_scope:
        if isinstance(company_scope, (list, tuple, set)):
            memberships = memberships.filter(company_id__in=company_scope)
        else:
            memberships = memberships.filter(company_id=company_scope)

    stats = {
        'total': memberships.count(),
        'by_role': {},
        'active_recently': memberships.filter(
            user__last_login__isnull=False
        ).count(),
    }

    # Считаем по ролям (используем ROLE_CHOICES из UserCompanyMembership)
    from work_orders.models import UserCompanyMembership as UCM

    for role_code, role_name in UCM.ROLE_CHOICES:
        count = memberships.filter(role_code=role_code).count()
        stats['by_role'][role_name] = count

    return stats


def get_file_statistics(company_scope=None):
    """
    Получить статистику по файлам

    ПАРАМЕТРЫ:
    - company_scope: int или список company_id для фильтрации
    """
    files = UserFile.objects.all()

    # Фильтрация по пользователям компании
    if company_scope:
        from work_orders.models import UserCompanyMembership
        membership_filter = {'is_active': True}
        if isinstance(company_scope, (list, tuple, set)):
            membership_filter['company_id__in'] = company_scope
        else:
            membership_filter['company_id'] = company_scope
        user_ids = UserCompanyMembership.objects.filter(**membership_filter).values_list('user_id', flat=True)
        files = files.filter(user_id__in=user_ids)

    stats = {
        'total': files.count(),
        'total_size': sum(f.file_size for f in files) if files.exists() else 0,
        'unique_users': files.values('user').distinct().count(),
    }

    return stats


def get_prompt_statistics():
    """Получить статистику по AI промптам"""
    prompts = AIPrompt.objects.all()

    stats = {
        'total': prompts.count(),
        'active': prompts.filter(is_active=True).count(),
        'by_type': {},
    }

    # Считаем по типам
    for prompt_type, type_name in AIPrompt.PROMPT_TYPES:
        count = prompts.filter(prompt_type=prompt_type).count()
        stats['by_type'][type_name] = count

    return stats


def get_kladr_statistics():
    """Получить статистику по КЛАДР"""
    stats = {
        'address_objects': KladrAddressObject.objects.count() if KLADR_AVAILABLE else 0,
        'buildings': Building.objects.count() if KLADR_AVAILABLE else 0,
        'service_areas': ServiceArea.objects.count() if KLADR_AVAILABLE else 0,
    }
    return stats


# ИСПРАВЛЕНИЕ (2026-02-03): Удалена функция user_management - дубликат /admin/auth/user/
# Полная функциональность доступна в Django Admin


@login_required
def prompt_management(request):
    """
    Управление AI промптами (быстрый доступ)
    """
    if not request.user.userprofile.has_admin_access():
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:admin_page')

    prompts = AIPrompt.objects.all().order_by('prompt_type', 'prompt_id')

    # Подсчет статистики по типам промптов
    prompt_types_with_stats = [
        (name, code, prompts.filter(prompt_type=code).count())
        for name, code in AIPrompt.PROMPT_TYPES
    ]

    context = {
        'prompts': prompts,
        'prompt_types': AIPrompt.PROMPT_TYPES,
        'prompt_types_with_stats': prompt_types_with_stats,
    }

    return render(request, 'portal/prompt_management.html', context)


@login_required
def director_residents(request):
    """
    Управление жителями ТСЖ (только своей компании)

    ДОСТУП: direktor_uk, chief_engineer
    """
    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Проверка роли (доступно директору и главному инженеру)
    if not request.user.is_superuser and membership.role_code not in ['direktor_uk', 'chief_engineer']:
        messages.error(request, 'Доступ разрешен только Директорам УК и Главным инженерам')
        return redirect('portal:welcome')

    # Фильтрация по компании
    company_scope = workspace['company_scope']

    # Получаем всех пользователей компании (жители + сотрудники)
    from work_orders.models import UserCompanyMembership
    company_memberships = UserCompanyMembership.objects.filter(is_active=True)
    if company_scope:
        if isinstance(company_scope, (list, tuple, set)):
            company_memberships = company_memberships.filter(company_id__in=company_scope)
        else:
            company_memberships = company_memberships.filter(company_id=company_scope)
    company_memberships = company_memberships.select_related('user', 'department').order_by('user__username')

    # Разделяем по ролям
    residents = [m for m in company_memberships if m.role_code == 'resident']
    staff = [m for m in company_memberships if m.role_code != 'resident']

    context = {
        'company': workspace['company'],
        'residents': residents,
        'staff': staff,
        'total_residents': len(residents),
        'total_staff': len(staff),
        'page_title': 'Учетные записи',
        'page_breadcrumb': 'Учетные записи',
    }

    # Breadcrumbs для возврата на правильный дашборд
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title

    return render(request, 'portal/director_residents.html', context)


@login_required
def director_service_objects(request):
    membership, workspace, response = _get_manager_workspace(request)
    if response:
        return response

    company_scope = workspace['company_scope']
    objects = _build_scoped_company_object_queryset(company_scope)
    context = {
        'company': workspace['company'],
        'objects': objects,
        'total_objects': objects.count(),
    }
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title
    return render(request, 'portal/company_service_objects.html', context)


@login_required
def director_object_bindings(request):
    from work_orders.models import CompanyObjectServicePeriod

    membership, workspace, response = _get_manager_workspace(request)
    if response:
        return response

    company_scope = workspace['company_scope']
    bindings = CompanyObjectServicePeriod.objects.filter(is_active=True).select_related('company')
    if company_scope:
        if isinstance(company_scope, (list, tuple, set)):
            bindings = bindings.filter(company_id__in=company_scope)
        else:
            bindings = bindings.filter(company_id=company_scope)
    bindings = bindings.order_by('-date_from', 'object_id')

    context = {
        'company': workspace['company'],
        'bindings': bindings,
        'total_bindings': bindings.count(),
    }
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title
    return render(request, 'portal/company_object_bindings.html', context)


@login_required
def director_import_service_objects(request):
    membership, workspace, response = _get_manager_workspace(request)
    if response:
        return response

    results = []
    summary = None
    if request.method == 'POST':
        uploaded_file = request.FILES.get('import_file')
        if not uploaded_file:
            messages.error(request, 'Выберите XLSX или XLS файл для загрузки.')
        else:
            try:
                extracted_rows = _extract_import_rows(uploaded_file)
            except ValueError as error:
                messages.error(request, str(error))
            else:
                if not extracted_rows:
                    messages.warning(request, 'В файле не найдено строк с адресами.')
                else:
                    created_count = 0
                    skipped_count = 0
                    error_count = 0
                    seen_addresses = set()
                    for row in extracted_rows:
                        address = row['address']
                        normalized_address = ' '.join(address.lower().split())
                        if normalized_address in seen_addresses:
                            results.append({
                                'row_number': row['row_number'],
                                'address': address,
                                'status': 'skipped',
                                'message': 'Адрес уже обработан в этом файле.',
                            })
                            skipped_count += 1
                            continue
                        seen_addresses.add(normalized_address)

                        try:
                            result = _import_service_object_for_company(address, workspace['company'], request.user)
                        except Exception as error:
                            results.append({
                                'row_number': row['row_number'],
                                'address': address,
                                'status': 'error',
                                'message': str(error),
                            })
                            error_count += 1
                        else:
                            result.update({
                                'row_number': row['row_number'],
                                'address': address,
                            })
                            results.append(result)
                            if result['status'] == 'created':
                                created_count += 1
                            else:
                                skipped_count += 1

                    summary = {
                        'processed': len(extracted_rows),
                        'created': created_count,
                        'skipped': skipped_count,
                        'errors': error_count,
                    }
                    if created_count:
                        messages.success(request, f'Загружено объектов: {created_count}.')
                    elif not error_count:
                        messages.info(request, 'Новые объекты не добавлены: все записи уже были привязаны.')

    context = {
        'company': workspace['company'],
        'results': results,
        'summary': summary,
    }
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title
    return render(request, 'portal/company_object_import.html', context)


@login_required
def director_departments(request):
    """
    Управление подразделениями ТСЖ (только своей компании)

    ДОСТУП: direktor_uk, chief_engineer
    """
    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Проверка роли (доступно директору и главному инженеру)
    if not request.user.is_superuser and membership.role_code not in ['direktor_uk', 'chief_engineer']:
        messages.error(request, 'Доступ разрешен только Директорам УК и Главным инженерам')
        return redirect('portal:welcome')

    # Фильтрация по компании
    company_scope = workspace['company_scope']

    # Получаем подразделения компании
    from work_orders.models import CompanyDepartment
    departments = CompanyDepartment.objects.filter(is_active=True)
    if company_scope:
        if isinstance(company_scope, (list, tuple, set)):
            departments = departments.filter(company_id__in=company_scope)
        else:
            departments = departments.filter(company_id=company_scope)
    departments = departments.select_related('parent_department').order_by('sort_order', 'department_name')

    # Статистика по сотрудникам в подразделениях
    from work_orders.models import UserCompanyMembership
    department_list = list(departments)
    staff_counts = dict(
        UserCompanyMembership.objects
        .filter(department_id__in=[dept.id for dept in department_list], is_active=True)
        .values('department_id')
        .annotate(total=Count('id'))
        .values_list('department_id', 'total')
    )

    children_map = {}
    for department in department_list:
        children_map.setdefault(department.parent_department_id, []).append(department)

    for children in children_map.values():
        children.sort(key=lambda item: (item.sort_order, item.department_name.lower(), item.id))

    department_tree_rows = []

    def walk_departments(parent_id=None, depth=0):
        for department in children_map.get(parent_id, []):
            department_tree_rows.append({
                'department': department,
                'staff_count': staff_counts.get(department.id, 0),
                'depth': depth,
                'indent_px': depth * 28,
                'has_children': bool(children_map.get(department.id)),
            })
            walk_departments(department.id, depth + 1)

    walk_departments()

    context = {
        'company': workspace['company'],
        'departments': department_tree_rows,
        'total_departments': len(department_list),
        'can_add_department': bool(membership and membership.role_code == 'direktor_uk'),  # Только директор может добавлять
    }

    # Breadcrumbs для возврата на правильный дашборд
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title

    return render(request, 'portal/director_departments.html', context)


@login_required
def director_add_resident(request):
    """
    Добавление жителя/сотрудника директором ТСЖ

    ДОСТУП: direktor_uk, chief_engineer
    """

    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Проверка роли (доступно директору и главному инженеру)
    if not request.user.is_superuser and membership.role_code not in ['direktor_uk', 'chief_engineer']:
        messages.error(request, 'Доступ разрешен только Директорам УК и Главным инженерам')
        return redirect('portal:welcome')

    superuser_without_membership = request.user.is_superuser and not membership
    companies = None
    company_id = membership.company_id if membership else None
    selected_company_id = request.POST.get('company') or request.GET.get('company')
    account_type = (request.POST.get('account_type') or request.GET.get('account_type') or 'resident').strip().lower()
    if account_type not in {'resident', 'employee'}:
        account_type = 'resident'

    if superuser_without_membership:
        from nsi.models import Company
        companies = Company.objects.filter(is_active=True).order_by('name')
        if selected_company_id:
            try:
                company_id = int(selected_company_id)
            except (TypeError, ValueError):
                company_id = None

    from work_orders.models import CompanyDepartment
    departments = CompanyDepartment.objects.filter(is_active=True)
    if superuser_without_membership and not company_id:
        departments = departments.none()
    elif company_id:
        departments = departments.filter(company_id=company_id)
    departments = departments.select_related('company').order_by('company__name', 'department_name')

    # Обработка формы
    if request.method == 'POST':
        from portal.forms import AddResidentForm
        form = AddResidentForm(request.POST)
        if account_type == 'resident':
            form.fields['role'].choices = [('resident', 'Житель')]
            form.fields['role'].initial = 'resident'
        else:
            form.fields['role'].choices = [
                ('executor', 'Исполнитель'),
                ('chief_engineer', 'Главный инженер'),
            ]
            form.fields['role'].initial = request.POST.get('role') or 'executor'

        form_valid = form.is_valid()
        company = None
        if superuser_without_membership:
            from nsi.models import Company
            if not company_id:
                form.add_error(None, 'Укажите компанию')
                form_valid = False
            else:
                try:
                    company = Company.objects.get(id=company_id, is_active=True)
                except Company.DoesNotExist:
                    form.add_error(None, 'Выбранная компания недоступна')
                    form_valid = False

        if form_valid:
            # Создаем пользователя
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data.get('email', ''),
                first_name=form.cleaned_data.get('first_name', ''),
                last_name=form.cleaned_data.get('last_name', ''),
                password=form.cleaned_data['password'],
                is_staff=False  # Жители - не staff
            )

            # Получаем или создаем UserProfile
            from portal.models import UserProfile
            profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'timezone': 'Europe/Moscow',
                    'role': 'uk_user'
                }
            )

            # Получаем подразделение (обязательно для сотрудников)
            from work_orders.models import CompanyDepartment
            department_id = request.POST.get('department')
            department = None
            role_code = form.cleaned_data['role']

            # Для исполнителей и главного инженера department обязателен
            if role_code in ['executor', 'chief_engineer']:
                if not department_id or department_id == '':
                    messages.error(request, 'Для сотрудников обязательно укажите подразделение!')
                    return render(request, 'portal/director_add_resident.html', {
                        'company': workspace['company'],
                        'form': form,
                        'departments': departments,
                        'companies': companies,
                        'selected_company_id': str(company_id) if company_id else '',
                        'superuser_without_membership': superuser_without_membership,
                    })
                try:
                    department = CompanyDepartment.objects.get(
                        id=int(department_id),
                        company_id=company_id
                    )
                except CompanyDepartment.DoesNotExist:
                    messages.error(request, 'Указанное подразделение не найдено!')
                    return render(request, 'portal/director_add_resident.html', {
                        'company': workspace['company'],
                        'form': form,
                        'departments': departments,
                        'companies': companies,
                        'selected_company_id': str(company_id) if company_id else '',
                        'superuser_without_membership': superuser_without_membership,
                    })
            elif department_id and department_id != '':
                # Для жителей department опционален, но если указан - проверяем
                try:
                    department = CompanyDepartment.objects.get(
                        id=int(department_id),
                        company_id=company_id
                    )
                except CompanyDepartment.DoesNotExist:
                    pass

            # Создаем UserCompanyMembership
            from work_orders.models import UserCompanyMembership
            UserCompanyMembership.objects.create(
                user=user,
                company_id=company_id,
                department=department,
                role_code=role_code,
                is_primary=True,
                is_active=True,
                date_from=timezone.now()
            )

            profile.role = 'resident' if role_code == 'resident' else 'uk_user'
            profile.primary_company_id = company_id
            profile.primary_department = department
            profile.phone = form.cleaned_data.get('phone', '')
            profile.address = form.cleaned_data.get('address', '')
            if role_code == 'chief_engineer':
                profile.job_title = 'chief_engineer'
            profile.save()

            messages.success(request, f'Пользователь {user.username} успешно создан!')
            return redirect('portal:director_residents')
    else:
        from portal.forms import AddResidentForm
        form = AddResidentForm()
        if account_type == 'resident':
            form.fields['role'].choices = [('resident', 'Житель')]
            form.fields['role'].initial = 'resident'
        else:
            form.fields['role'].choices = [
                ('executor', 'Исполнитель'),
                ('chief_engineer', 'Главный инженер'),
            ]
            form.fields['role'].initial = 'executor'

    context = {
        'company': workspace['company'],
        'form': form,
        'departments': departments,
        'companies': companies,
        'selected_company_id': str(company_id) if company_id else '',
        'superuser_without_membership': superuser_without_membership,
        'account_type': account_type,
        'page_title': 'Создать жителя' if account_type == 'resident' else 'Создать сотрудника',
    }

    # Breadcrumbs для возврата на правильный дашборд
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title

    return render(request, 'portal/director_add_resident.html', context)


@login_required
def director_add_department(request):
    """
    Добавление подразделения директором ТСЖ

    ДОСТУП: direktor_uk (только директор)
    """
    # Проверка staff

    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Проверка роли (доступно только директору)
    if not request.user.is_superuser and membership.role_code != 'direktor_uk':
        messages.error(request, 'Доступ разрешен только Директорам УК')
        return redirect('portal:welcome')

    superuser_without_membership = request.user.is_superuser and not membership
    companies = None
    company_id = membership.company_id if membership else None
    selected_company_id = request.POST.get('company') or request.GET.get('company')
    selected_parent_id = request.POST.get('parent_department') or request.GET.get('parent_department') or ''

    if superuser_without_membership:
        from nsi.models import Company
        companies = Company.objects.filter(is_active=True).order_by('name')
        if selected_company_id:
            try:
                company_id = int(selected_company_id)
            except (TypeError, ValueError):
                company_id = None

    from work_orders.models import CompanyDepartment
    departments = CompanyDepartment.objects.filter(is_active=True)
    if superuser_without_membership and not company_id:
        departments = departments.none()
    elif company_id:
        departments = departments.filter(company_id=company_id)
    departments = departments.select_related('company', 'parent_department').order_by('company__name', 'sort_order', 'department_name')

    # Обработка формы
    if request.method == 'POST':
        from portal.forms import AddDepartmentForm
        form = AddDepartmentForm(request.POST, departments=departments)

        form_valid = form.is_valid()
        if superuser_without_membership:
            from nsi.models import Company
            if not company_id:
                form.add_error(None, 'Укажите компанию')
                form_valid = False
            elif not Company.objects.filter(id=company_id, is_active=True).exists():
                form.add_error(None, 'Выбранная компания недоступна')
                form_valid = False

        if form_valid:
            # Получаем родительское подразделение (если указан)
            parent_id = request.POST.get('parent_department')
            parent = None
            if parent_id and parent_id != '':
                try:
                    parent = CompanyDepartment.objects.get(
                        id=int(parent_id),
                        company_id=company_id
                    )
                except CompanyDepartment.DoesNotExist:
                    pass

            # Создаем подразделение
            department = CompanyDepartment.objects.create(
                company_id=company_id,
                department_code=form.cleaned_data['department_code'],
                department_name=form.cleaned_data['department_name'],
                parent_department=parent,
                is_active=True,
                is_test=False
            )

            messages.success(request, f'Подразделение "{department.department_name}" успешно создано!')
            return redirect('portal:director_departments')
    else:
        from portal.forms import AddDepartmentForm

        form = AddDepartmentForm(
            departments=departments,
            initial={'parent_department': selected_parent_id} if selected_parent_id else None,
        )

    context = {
        'company': workspace['company'],
        'form': form,
        'companies': companies,
        'selected_company_id': str(company_id) if company_id else '',
        'selected_parent_id': str(selected_parent_id) if selected_parent_id else '',
        'superuser_without_membership': superuser_without_membership,
    }

    # Breadcrumbs для возврата на правильный дашборд
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title

    return render(request, 'portal/director_add_department.html', context)


@login_required
def director_edit_department(request, department_id):
    """
    Редактирование подразделения директором ТСЖ

    ДОСТУП: direktor_uk
    """
    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Проверка роли (доступно только директору)
    if not request.user.is_superuser and membership.role_code != 'direktor_uk':
        messages.error(request, 'Доступ разрешен только Директорам УК')
        return redirect('portal:welcome')

    from work_orders.models import CompanyDepartment

    # Получаем подразделение
    try:
        department = CompanyDepartment.objects.get(id=department_id)
    except CompanyDepartment.DoesNotExist:
        messages.error(request, 'Подразделение не найдено')
        return redirect('portal:director_departments')

    # Проверка доступа к компании
    company_scope = workspace['company_scope']
    if not request.user.is_superuser:
        if isinstance(company_scope, (list, tuple, set)):
            if department.company_id not in company_scope:
                messages.error(request, 'Доступ к этому подразделению запрещен')
                return redirect('portal:director_departments')
        else:
            if department.company_id != company_scope:
                messages.error(request, 'Доступ к этому подразделению запрещен')
                return redirect('portal:director_departments')

    # Получаем все подразделения для выбора родительского
    departments = CompanyDepartment.objects.filter(
        is_active=True,
        company_id=department.company_id
    ).exclude(id=department_id).select_related('company', 'parent_department').order_by('sort_order', 'department_name')

    # Обработка формы
    if request.method == 'POST':
        from portal.forms import EditDepartmentForm
        form = EditDepartmentForm(request.POST, departments=departments, instance=department)

        if form.is_valid():
            # Получаем родительское подразделение (если указан)
            parent_id = request.POST.get('parent_department')
            parent = None
            if parent_id and parent_id != '':
                try:
                    parent = CompanyDepartment.objects.get(
                        id=int(parent_id),
                        company_id=department.company_id
                    )
                except CompanyDepartment.DoesNotExist:
                    pass

            # Обновляем подразделение
            department.department_code = form.cleaned_data['department_code']
            department.department_name = form.cleaned_data['department_name']
            department.parent_department = parent
            department.save()

            messages.success(request, f'Подразделение "{department.department_name}" успешно обновлено!')
            return redirect('portal:director_departments')
    else:
        from portal.forms import EditDepartmentForm

        # Инициализируем форму текущими значениями
        initial_data = {
            'department_code': department.department_code,
            'department_name': department.department_name,
            'parent_department': department.parent_department_id if department.parent_department else '',
        }
        form = EditDepartmentForm(initial=initial_data, departments=departments, instance=department)

    context = {
        'company': workspace['company'],
        'department': department,
        'form': form,
        'is_edit': True,
    }

    # Breadcrumbs для возврата на правильный дашборд
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title

    return render(request, 'portal/director_add_department.html', context)


# ========== ВРЕМЕННЫЕ VIEW ФУНКЦИИ ДЛЯ НОВЫХ DASHBOARD (2026-04-06) ==========

@login_required
def director_page_new(request):
    """
    Временная функция для просмотра нового dashboard директора с 3D дизайном

    TODO: После утверждения дизайна - заменить director_page.html на director_page_new.html
    """
    # Проверка доступа
    if not request.user.is_staff:
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:welcome')

    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    company_scope = workspace['company_scope']

    # Статистика
    user_stats = get_user_statistics(company_scope)

    context = {
        'company': workspace['company'],
        'total_users': user_stats['total'],
        'resident_count': user_stats['by_role'].get('Житель', 0),
    }

    return render(request, 'portal/director_page_new.html', context)


@login_required
def chief_engineer_page_new(request):
    """
    Временная функция для просмотра нового dashboard главного инженера с 3D дизайном

    TODO: После утверждения дизайна - заменить chief_engineer_page.html на chief_engineer_page_new.html
    """
    # Проверка доступа
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.error(request, 'Доступ запрещен!')
            return redirect('portal:welcome')
    else:
        workspace = _workspace_context(request, membership)

    if not request.user.is_superuser and membership.role_code != 'chief_engineer':
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:welcome')

    company_scope = workspace['company_scope']

    # Статистика
    user_stats = get_user_statistics(company_scope)

    context = {
        'company': workspace['company'],
        'total_users': user_stats['total'],
        'executor_count': user_stats['by_role'].get('Исполнитель', 0),
    }

    return render(request, 'portal/chief_engineer_page_new.html', context)


@login_required
def director_sla(request):
    """
    Управление SLA политиками организации

    ДОСТУП: direktor_uk
    """
    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Проверка роли
    if not request.user.is_superuser and membership.role_code != 'direktor_uk':
        messages.error(request, 'Доступ разрешен только Директорам УК')
        return redirect('portal:welcome')

    # Фильтрация по компании
    company_scope = workspace['company_scope']

    # Получаем SLA политики компании
    from work_orders.models import SLAPolicy

    sla_policies = SLAPolicy.objects.filter(is_active=True)
    if company_scope:
        if isinstance(company_scope, (list, tuple, set)):
            sla_policies = sla_policies.filter(company_id__in=company_scope)
        else:
            sla_policies = sla_policies.filter(company_id=company_scope)

    sla_policies = sla_policies.select_related('company', 'service').order_by('-created_at')

    context = {
        'company': workspace['company'],
        'sla_policies': sla_policies,
        'total_policies': sla_policies.count(),
    }

    return render(request, 'portal/director_sla.html', context)


@login_required
def director_employees(request):
    """
    Управление сотрудниками организации

    ДОСТУП: direktor_uk
    """
    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Проверка роли
    if not request.user.is_superuser and membership.role_code != 'direktor_uk':
        messages.error(request, 'Доступ разрешен только Директорам УК')
        return redirect('portal:welcome')

    # Фильтрация по компании
    company_scope = workspace['company_scope']

    # Получаем сотрудников компании (все роли кроме "Житель")
    from work_orders.models import UserCompanyMembership

    employee_roles = ['direktor_uk', 'chief_engineer', 'executor', 'django_admin']

    employees = UserCompanyMembership.objects.filter(
        is_active=True,
        role_code__in=employee_roles
    )

    if company_scope:
        if isinstance(company_scope, (list, tuple, set)):
            employees = employees.filter(company_id__in=company_scope)
        else:
            employees = employees.filter(company_id=company_scope)

    employees = employees.select_related('user', 'company', 'department').order_by('user__last_name', 'user__first_name')

    context = {
        'company': workspace['company'],
        'employees': employees,
        'total_employees': employees.count(),
    }

    return render(request, 'portal/director_employees.html', context)

