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
from django.views.decorators.cache import never_cache
from openpyxl import load_workbook

from portal.models import UserProfile, ServiceObject
from portal.mixins import get_primary_membership, get_role_dashboard_url

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


def _safe_user_display_name(user):
    full_name = (user.get_full_name() or '').strip()
    compact = full_name.replace(' ', '')
    if full_name and compact and set(compact) != {'?'}:
        return full_name
    return user.username


def get_work_order_statistics(company_scope=None):
    from work_orders.models import WorkOrder

    terminal_status_codes = ['completed', 'closed', 'cancelled']
    completed_status_codes = ['completed', 'closed']

    work_orders = WorkOrder.objects.filter(is_test=False)
    if company_scope:
        if isinstance(company_scope, (list, tuple, set)):
            work_orders = work_orders.filter(company_id__in=company_scope)
        else:
            work_orders = work_orders.filter(company_id=company_scope)

    return {
        'total': work_orders.count(),
        'active': work_orders.exclude(
            current_internal_status__short_code_en__in=terminal_status_codes
        ).count(),
        'completed': work_orders.filter(
            current_internal_status__short_code_en__in=completed_status_codes
        ).count(),
        'cancelled': work_orders.filter(
            current_internal_status__short_code_en='cancelled'
        ).count(),
    }


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
        'kladr_stats': get_kladr_statistics() if KLADR_AVAILABLE else {},
    }

    return render(request, 'portal/admin_page.html', context)


@login_required
def director_page(request):
    """
    Отдельная страница для Директора УК

    ДОСТУП: direktor_uk (ограничение через DirectorMixin в Class-Based Views)
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

    # Статистика по пользователям компании
    user_stats = get_user_statistics(company_scope)
    work_order_stats = get_work_order_statistics(company_scope)
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
        'kladr_stats': get_kladr_statistics() if KLADR_AVAILABLE else {},
        'total_work_orders': work_order_stats['total'],
        'active_work_orders': work_order_stats['active'],
        'completed_work_orders': work_order_stats['completed'],
        'cancelled_work_orders': work_order_stats['cancelled'],
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
    work_order_stats = get_work_order_statistics(company_scope)

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
        'total_work_orders': work_order_stats['total'],
        'active_work_orders': work_order_stats['active'],
        'completed_work_orders': work_order_stats['completed'],
        'cancelled_work_orders': work_order_stats['cancelled'],
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
    """Совместимость со старой ссылкой управления промптами."""
    return redirect('/llm-tester/')


@never_cache
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

    for item in residents + staff:
        item.display_name = _safe_user_display_name(item.user)

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


# ============================================================================
# Service object import runtime overrides (authoritative final block)
# ============================================================================

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

        dataframe = pd.read_excel(BytesIO(binary))
        rows = [tuple(dataframe.columns.tolist())]
        rows.extend(tuple(row) for row in dataframe.itertuples(index=False, name=None))

    if not rows:
        return []

    headers = [str(value).strip().lower() if value is not None else '' for value in rows[0]]
    data_rows = rows[1:]

    def _find_index(*candidates):
        for candidate in candidates:
            if candidate in headers:
                return headers.index(candidate)
        return None

    address_idx = _find_index('адрес', 'address', 'объект', 'объект обслуживания')
    city_idx = _find_index('город', 'город основной', 'city', 'city_main', 'gorod')
    street_idx = _find_index('улица', 'street', 'ulitsa')
    house_idx = _find_index('дом', 'house', 'nomerdoma')
    unit_idx = _find_index('квартира', 'помещение', 'unit', 'unit_number', 'nomerkvartiry')

    extracted_rows = []
    for row_number, row in enumerate(data_rows, start=2):
        address = ''
        if address_idx is not None and address_idx < len(row) and row[address_idx] is not None:
            address = str(row[address_idx]).strip()

        unit_number = ''
        if unit_idx is not None and unit_idx < len(row) and row[unit_idx] is not None:
            unit_number = str(row[unit_idx]).strip()

        if not address:
            city = str(row[city_idx]).strip() if city_idx is not None and city_idx < len(row) and row[city_idx] is not None else ''
            street = str(row[street_idx]).strip() if street_idx is not None and street_idx < len(row) and row[street_idx] is not None else ''
            house = str(row[house_idx]).strip() if house_idx is not None and house_idx < len(row) and row[house_idx] is not None else ''
            parts = []
            if city:
                parts.append(f'г {city}')
            if street:
                parts.append(f'ул {street}')
            if house:
                parts.append(f'д {house}')
            address = ', '.join(parts).strip(', ')

        if not address:
            continue

        extracted_rows.append({'row_number': row_number, 'address': address, 'unit_number': unit_number})

    return extracted_rows


def _parse_planned_date(raw_value):
    from datetime import date

    if raw_value:
        try:
            return date.fromisoformat(str(raw_value))
        except ValueError:
            pass
    return timezone.localdate()


def _get_object_binding_on_date(service_object_id, on_date):
    from work_orders.models import CompanyObjectServicePeriod

    return (
        CompanyObjectServicePeriod.objects.select_related('company')
        .filter(object_id=service_object_id, is_active=True)
        .filter(date_from__lte=on_date)
        .filter(Q(date_to__isnull=True) | Q(date_to__gte=on_date))
        .order_by('-date_from')
        .first()
    )


def _find_existing_address_entities(components, street_guid, house_guid, house_number, unit_number):
    from address.models import Building, Unit

    building = None
    if house_guid:
        building = Building.objects.filter(fias_guid=house_guid).first()
    if building is None and street_guid and house_number:
        building = Building.objects.filter(street_fias_guid=street_guid, house_number=house_number).first()

    unit = None
    if building is not None and unit_number:
        unit = Unit.objects.filter(building_id=building.id, unit_number=unit_number).first()
    return building, unit


def _validate_import_row_for_batch(address, unit_number, company, planned_date):
    from address.services import build_full_address, normalize_house_number, normalize_unit_number
    from address_extractor_service import AddressExtractor

    extractor = AddressExtractor()
    service = FiasAddressService()
    components = extractor.extract_address_components(address)
    if unit_number and not components.get('apartment_number'):
        components['apartment_number'] = unit_number

    city = components.get('city')
    street = components.get('street')
    house_number = normalize_house_number(components.get('house_number'))
    unit_number_norm = normalize_unit_number(components.get('apartment_number') or unit_number)

    result = {
        'address': address,
        'city': city or '',
        'street': street or '',
        'house': house_number or '',
        'unit_number': unit_number_norm or '',
        'full_address': build_full_address(components),
        'building_fias_guid': '',
        'house_parse_status': '',
        'house_fias_status': '',
        'binding_status': '',
        'unit_status': '',
        'final_status': '',
        'comment': '',
    }

    missing = []
    if not city:
        missing.append('населенный пункт')
    if not street:
        missing.append('улица')
    if not house_number:
        missing.append('дом')
    if missing:
        result.update(
            {
                'house_parse_status': 'incomplete',
                'final_status': 'clarify',
                'comment': f"Неполный адрес: отсутствует {', '.join(missing)}.",
            }
        )
        return result

    fias_result = service.resolve_building_with_fallback(components)
    street_guid = fias_result.get('street_guid')
    house_guid = fias_result.get('house_guid')
    result['building_fias_guid'] = house_guid or ''
    result['full_address'] = fias_result.get('full_address') or result['full_address']
    result['house_parse_status'] = 'parsed'

    if not street_guid:
        result.update(
            {
                'house_fias_status': 'street_not_found',
                'final_status': 'clarify',
                'comment': 'Улица не найдена в ФИАС. Строку нельзя импортировать.',
            }
        )
        return result

    result['house_fias_status'] = 'house_matched' if house_guid else 'street_matched'
    building, unit = _find_existing_address_entities(components, street_guid, house_guid, house_number, unit_number_norm)

    if building is not None:
        house_service_object = (
            ServiceObject.objects.filter(building_id=building.id, unit_id__isnull=True, is_active=True)
            .order_by('service_object_id')
            .first()
        )
        if house_service_object:
            binding = _get_object_binding_on_date(house_service_object.service_object_id, planned_date)
            if binding and binding.company_id != company.id:
                result.update(
                    {
                        'binding_status': 'conflict',
                        'final_status': 'blocked',
                        'comment': f'Дом уже закреплен за компанией "{binding.company.name}" на указанную дату.',
                    }
                )
                return result
            if binding and binding.company_id == company.id:
                result['binding_status'] = 'same_company'
            else:
                result['binding_status'] = 'new_binding'
        else:
            result['binding_status'] = 'new_binding'
    else:
        result['binding_status'] = 'new_building'

    if unit_number_norm:
        if unit is not None and building is not None:
            unit_service_object = (
                ServiceObject.objects.filter(building_id=building.id, unit_id=unit.id, is_active=True)
                .order_by('service_object_id')
                .first()
            )
            if unit_service_object:
                unit_binding = _get_object_binding_on_date(unit_service_object.service_object_id, planned_date)
                if unit_binding and unit_binding.company_id != company.id:
                    result.update(
                        {
                            'unit_status': 'conflict',
                            'final_status': 'blocked',
                            'comment': f'Квартира/помещение уже закреплена за компанией "{unit_binding.company.name}" на указанную дату.',
                        }
                    )
                    return result
                if unit_binding and unit_binding.company_id == company.id:
                    result['unit_status'] = 'same_company'
                else:
                    result['unit_status'] = 'existing_unit'
            else:
                result['unit_status'] = 'existing_unit'
        else:
            result['unit_status'] = 'new_unit'
    else:
        result['unit_status'] = 'house_only'

    if result['binding_status'] == 'same_company' and result['unit_status'] in {'', 'house_only', 'same_company'}:
        result.update(
            {
                'final_status': 'blocked',
                'comment': 'Объект уже привязан к вашей компании на указанную дату.',
            }
        )
        return result

    result.update(
        {
            'final_status': 'ready',
            'comment': 'Строка готова к импорту.',
        }
    )
    return result


def _stage_import_batch(uploaded_file, company, user, planned_date):
    from address.models import ImportBatch, ImportRow

    extracted_rows = _extract_import_rows(uploaded_file)
    if not extracted_rows:
        raise ValueError('В файле не найдено строк с адресами.')

    batch = ImportBatch.objects.create(
        company_id=company.id,
        uploaded_by=user,
        planned_date_from=planned_date,
        status='uploaded',
    )

    seen_rows = set()
    for row in extracted_rows:
        address = row['address']
        unit_number = (row.get('unit_number') or '').strip()
        dedupe_key = (' '.join(address.lower().split()), unit_number.lower())
        if dedupe_key in seen_rows:
            validation = {
                'address': address,
                'city': '',
                'street': '',
                'house': '',
                'unit_number': unit_number,
                'full_address': address,
                'building_fias_guid': '',
                'house_parse_status': 'duplicate',
                'house_fias_status': '',
                'binding_status': '',
                'unit_status': '',
                'final_status': 'blocked',
                'comment': 'Дубликат строки в загруженном файле.',
            }
        else:
            seen_rows.add(dedupe_key)
            validation = _validate_import_row_for_batch(address, unit_number, company, planned_date)

        ImportRow.objects.create(
            batch=batch,
            row_no=row['row_number'],
            raw_address=address,
            city_main=validation['city'],
            street=validation['street'],
            house=validation['house'],
            unit_number=validation['unit_number'],
            house_parse_status=validation['house_parse_status'],
            house_fias_status=validation['house_fias_status'],
            binding_status=validation['binding_status'],
            unit_status=validation['unit_status'],
            final_status=validation['final_status'],
            comment=validation['comment'],
            city_fact=validation['full_address'],
            source_kladr_check=validation['building_fias_guid'],
        )

    batch.status = 'validated'
    batch.save(update_fields=['status'])
    return batch


def _build_import_summary(batch_rows):
    rows = list(batch_rows)
    return {
        'processed': len(rows),
        'ready': sum(1 for row in rows if row.final_status == 'ready'),
        'blocked': sum(1 for row in rows if row.final_status == 'blocked'),
        'clarify': sum(1 for row in rows if row.final_status == 'clarify'),
        'imported': sum(1 for row in rows if row.final_status == 'imported'),
        'errors': sum(1 for row in rows if row.final_status == 'error'),
    }


def _ensure_company_binding(company, service_object, comment, on_date):
    from work_orders.models import CompanyObjectServicePeriod

    existing = (
        CompanyObjectServicePeriod.objects.select_related('company')
        .filter(object_id=service_object.service_object_id, is_active=True)
        .filter(date_from__lte=on_date)
        .filter(Q(date_to__isnull=True) | Q(date_to__gte=on_date))
        .order_by('-date_from')
        .first()
    )
    if existing:
        if existing.company_id != company.id:
            raise ValueError(
                f'В настоящий момент данный объект закреплен за другой организацией: "{existing.company.name}".'
            )
        return existing, False

    binding = CompanyObjectServicePeriod.objects.create(
        company=company,
        object_id=service_object.service_object_id,
        date_from=on_date,
        comment=comment,
        is_active=True,
    )
    return binding, True


@transaction.atomic
def _import_service_object_for_company(address, company, user, unit_number=None, on_date=None):
    from address.models import Building, Unit
    from address.services import build_full_address, normalize_house_number, normalize_unit_number
    from address_extractor_service import AddressExtractor

    service = FiasAddressService()
    if not service.is_configured:
        raise ValueError('Не настроен FIAS_API_TOKEN.')

    extractor = AddressExtractor()
    components = extractor.extract_address_components(address)
    if unit_number and not components.get('apartment_number'):
        components['apartment_number'] = unit_number

    validation = extractor.validate_and_match_to_db(components)
    house_number = normalize_house_number(validation.get('house_number') or components.get('house_number'))
    street_guid = validation.get('street_fias_guid')
    house_guid = validation.get('fias_object_guid')
    unit_number_norm = normalize_unit_number(components.get('apartment_number') or unit_number)
    import_date = on_date or timezone.localdate()

    if not street_guid:
        raise ValueError('Улица не найдена в ФИАС. Дом не сохранен.')
    if not house_number:
        raise ValueError('Не удалось определить номер дома.')

    building = Building.objects.filter(pk=validation.get('building_id')).first() if validation.get('building_id') else None
    fias_result = service.resolve_building_with_fallback(components)
    if building is None and house_guid:
        building = Building.objects.filter(fias_guid=house_guid).first()
    if building is None:
        building = Building.objects.filter(street_fias_guid=street_guid, house_number=house_number).first()

    full_address = validation.get('address_full') or fias_result.get('full_address') or build_full_address(components)
    if building is None:
        building = Building.objects.create(
            fias_guid=house_guid or None,
            street_fias_guid=street_guid,
            house_number=house_number,
            full_address=full_address,
            created_by=user,
        )
        building_created = True
    else:
        building_created = False
        updated = False
        for field_name, value in (
            ('fias_guid', house_guid or building.fias_guid),
            ('street_fias_guid', street_guid),
            ('house_number', house_number),
            ('full_address', full_address),
        ):
            if value and getattr(building, field_name) != value:
                setattr(building, field_name, value)
                updated = True
        if updated:
            building.save(update_fields=['fias_guid', 'street_fias_guid', 'house_number', 'full_address', 'updated_at'])

    house_service_object, house_created = _get_or_create_service_object(building.id, unit_id=None)
    house_binding, house_binding_created = _ensure_company_binding(
        company,
        house_service_object,
        'Загружено из кабинета руководителя',
        import_date,
    )

    result_service_object = house_service_object
    unit_created = False
    unit_binding_created = False

    if unit_number_norm:
        unit = Unit.objects.filter(building_id=building.id, unit_number=unit_number_norm).first()
        if unit is None:
            unit = Unit.objects.create(building_id=building.id, unit_number=unit_number_norm)
            unit_created = True

        result_service_object, _ = _get_or_create_service_object(building.id, unit_id=unit.id)
        _, unit_binding_created = _ensure_company_binding(
            company,
            result_service_object,
            'Загружено из кабинета руководителя (квартира/помещение)',
            import_date,
        )

    created_anything = any([building_created, house_created, house_binding_created, unit_created, unit_binding_created])

    return {
        'status': 'created' if created_anything else 'skipped',
        'service_object': result_service_object,
        'binding': house_binding,
        'building_fias_guid': str(building.fias_guid) if building.fias_guid else '-',
        'message': (
            'Созданы объект дома и объект помещения, привязки обновлены.'
            if unit_number_norm and created_anything
            else 'Объект уже был привязан к вашей компании.'
            if not created_anything
            else 'Объект дома загружен и привязан к компании.'
        ),
    }


@login_required
def director_import_service_objects(request):
    from address.models import ImportBatch

    membership, workspace, response = _get_manager_workspace(request)
    if response:
        return response

    batch = None
    batch_id = request.POST.get('batch_id') or request.GET.get('batch_id')
    if batch_id:
        batch = ImportBatch.objects.filter(id=batch_id, company_id=workspace['company'].id).first()

    if request.method == 'POST':
        action = request.POST.get('action') or 'upload'
        planned_date = _parse_planned_date(request.POST.get('planned_date_from'))

        if action == 'upload':
            uploaded_file = request.FILES.get('import_file')
            if not uploaded_file:
                messages.error(request, 'Выберите XLSX или XLS файл для загрузки.')
            else:
                try:
                    batch = _stage_import_batch(uploaded_file, workspace['company'], request.user, planned_date)
                except ValueError as error:
                    messages.error(request, str(error))
                else:
                    messages.success(request, 'Файл проверен. Подтвердите импорт готовых строк.')
        elif action == 'confirm':
            if not batch:
                messages.error(request, 'Пакет импорта не найден.')
            else:
                ready_rows = list(batch.rows.filter(final_status='ready').order_by('row_no', 'id'))
                imported_count = 0
                error_count = 0
                for row in ready_rows:
                    try:
                        result = _import_service_object_for_company(
                            row.raw_address,
                            workspace['company'],
                            request.user,
                            unit_number=row.unit_number,
                            on_date=batch.planned_date_from,
                        )
                    except Exception as error:
                        row.final_status = 'error'
                        row.comment = str(error)
                        row.save(update_fields=['final_status', 'comment'])
                        error_count += 1
                    else:
                        row.final_status = 'imported'
                        row.comment = result['message']
                        row.source_kladr_check = result.get('building_fias_guid') or row.source_kladr_check
                        row.save(update_fields=['final_status', 'comment', 'source_kladr_check'])
                        imported_count += 1

                batch.status = 'failed' if error_count else 'imported'
                batch.save(update_fields=['status'])
                messages.success(request, f'Импортировано строк: {imported_count}.')
                if error_count:
                    messages.warning(request, f'Строк с ошибками: {error_count}.')

    batch_rows = []
    summary = None
    ready_rows_count = 0
    planned_date_value = timezone.localdate()
    if batch:
        batch_rows = list(batch.rows.order_by('row_no', 'id'))
        summary = _build_import_summary(batch_rows)
        ready_rows_count = summary['ready']
        planned_date_value = batch.planned_date_from

    context = {
        'company': workspace['company'],
        'batch': batch,
        'results': batch_rows,
        'summary': summary,
        'ready_rows_count': ready_rows_count,
        'planned_date_from': planned_date_value,
    }
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title
    return render(request, 'portal/company_object_import.html', context)


# ============================================================================
# FINAL EOF OVERRIDE: two-stage service object import
# ============================================================================

def _parse_planned_date(raw_value):
    from datetime import date

    if raw_value:
        try:
            return date.fromisoformat(str(raw_value))
        except ValueError:
            pass
    return timezone.localdate()


def _get_object_binding_on_date(service_object_id, on_date):
    from work_orders.models import CompanyObjectServicePeriod

    return (
        CompanyObjectServicePeriod.objects.select_related('company')
        .filter(object_id=service_object_id, is_active=True)
        .filter(date_from__lte=on_date)
        .filter(Q(date_to__isnull=True) | Q(date_to__gte=on_date))
        .order_by('-date_from')
        .first()
    )


def _find_existing_address_entities(components, street_guid, house_guid, house_number, unit_number):
    from address.models import Building, Unit

    building = None
    if house_guid:
        building = Building.objects.filter(fias_guid=house_guid).first()
    if building is None and street_guid and house_number:
        building = Building.objects.filter(street_fias_guid=street_guid, house_number=house_number).first()

    unit = None
    if building is not None and unit_number:
        unit = Unit.objects.filter(building_id=building.id, unit_number=unit_number).first()
    return building, unit


def _validate_import_row_for_batch(address, unit_number, company, planned_date):
    from address.services import build_full_address, normalize_house_number, normalize_unit_number
    from address_extractor_service import AddressExtractor

    extractor = AddressExtractor()
    service = FiasAddressService()
    components = extractor.extract_address_components(address)
    if unit_number and not components.get('apartment_number'):
        components['apartment_number'] = unit_number

    city = components.get('city')
    street = components.get('street')
    house_number = normalize_house_number(components.get('house_number'))
    unit_number_norm = normalize_unit_number(components.get('apartment_number') or unit_number)

    result = {
        'address': address,
        'city': city or '',
        'street': street or '',
        'house': house_number or '',
        'unit_number': unit_number_norm or '',
        'full_address': build_full_address(components),
        'building_fias_guid': '',
        'house_parse_status': '',
        'house_fias_status': '',
        'binding_status': '',
        'unit_status': '',
        'final_status': '',
        'comment': '',
    }

    missing = []
    if not city:
        missing.append('населенный пункт')
    if not street:
        missing.append('улица')
    if not house_number:
        missing.append('дом')
    if missing:
        result.update(
            {
                'house_parse_status': 'incomplete',
                'final_status': 'clarify',
                'comment': f"Неполный адрес: отсутствует {', '.join(missing)}.",
            }
        )
        return result

    fias_result = service.resolve_building_with_fallback(components)
    street_guid = fias_result.get('street_guid')
    house_guid = fias_result.get('house_guid')
    result['building_fias_guid'] = house_guid or ''
    result['full_address'] = fias_result.get('full_address') or result['full_address']
    result['house_parse_status'] = 'parsed'

    if not street_guid:
        result.update(
            {
                'house_fias_status': 'street_not_found',
                'final_status': 'clarify',
                'comment': 'Улица не найдена в ФИАС. Строку нельзя импортировать.',
            }
        )
        return result

    result['house_fias_status'] = 'house_matched' if house_guid else 'street_matched'
    building, unit = _find_existing_address_entities(components, street_guid, house_guid, house_number, unit_number_norm)

    if building is not None:
        house_service_object = (
            ServiceObject.objects.filter(building_id=building.id, unit_id__isnull=True, is_active=True)
            .order_by('service_object_id')
            .first()
        )
        if house_service_object:
            binding = _get_object_binding_on_date(house_service_object.service_object_id, planned_date)
            if binding and binding.company_id != company.id:
                result.update(
                    {
                        'binding_status': 'conflict',
                        'final_status': 'blocked',
                        'comment': f'Дом уже закреплен за компанией "{binding.company.name}" на указанную дату.',
                    }
                )
                return result
            if binding and binding.company_id == company.id:
                result['binding_status'] = 'same_company'
            else:
                result['binding_status'] = 'new_binding'
        else:
            result['binding_status'] = 'new_binding'
    else:
        result['binding_status'] = 'new_building'

    if unit_number_norm:
        if unit is not None and building is not None:
            unit_service_object = (
                ServiceObject.objects.filter(building_id=building.id, unit_id=unit.id, is_active=True)
                .order_by('service_object_id')
                .first()
            )
            if unit_service_object:
                unit_binding = _get_object_binding_on_date(unit_service_object.service_object_id, planned_date)
                if unit_binding and unit_binding.company_id != company.id:
                    result.update(
                        {
                            'unit_status': 'conflict',
                            'final_status': 'blocked',
                            'comment': f'Квартира/помещение уже закреплена за компанией "{unit_binding.company.name}" на указанную дату.',
                        }
                    )
                    return result
                if unit_binding and unit_binding.company_id == company.id:
                    result['unit_status'] = 'same_company'
                else:
                    result['unit_status'] = 'existing_unit'
            else:
                result['unit_status'] = 'existing_unit'
        else:
            result['unit_status'] = 'new_unit'
    else:
        result['unit_status'] = 'house_only'

    if result['binding_status'] == 'same_company' and result['unit_status'] in {'', 'house_only', 'same_company'}:
        result.update(
            {
                'final_status': 'blocked',
                'comment': 'Объект уже привязан к вашей компании на указанную дату.',
            }
        )
        return result

    result.update(
        {
            'final_status': 'ready',
            'comment': 'Строка готова к импорту.',
        }
    )
    return result


def _stage_import_batch(uploaded_file, company, user, planned_date):
    from address.models import ImportBatch, ImportRow

    extracted_rows = _extract_import_rows(uploaded_file)
    if not extracted_rows:
        raise ValueError('В файле не найдено строк с адресами.')

    batch = ImportBatch.objects.create(
        company_id=company.id,
        uploaded_by=user,
        planned_date_from=planned_date,
        status='uploaded',
    )

    seen_rows = set()
    for row in extracted_rows:
        address = row['address']
        unit_number = (row.get('unit_number') or '').strip()
        dedupe_key = (' '.join(address.lower().split()), unit_number.lower())
        if dedupe_key in seen_rows:
            validation = {
                'address': address,
                'city': '',
                'street': '',
                'house': '',
                'unit_number': unit_number,
                'full_address': address,
                'building_fias_guid': '',
                'house_parse_status': 'duplicate',
                'house_fias_status': '',
                'binding_status': '',
                'unit_status': '',
                'final_status': 'blocked',
                'comment': 'Дубликат строки в загруженном файле.',
            }
        else:
            seen_rows.add(dedupe_key)
            validation = _validate_import_row_for_batch(address, unit_number, company, planned_date)

        ImportRow.objects.create(
            batch=batch,
            row_no=row['row_number'],
            raw_address=address,
            city_main=validation['city'],
            street=validation['street'],
            house=validation['house'],
            unit_number=validation['unit_number'],
            house_parse_status=validation['house_parse_status'],
            house_fias_status=validation['house_fias_status'],
            binding_status=validation['binding_status'],
            unit_status=validation['unit_status'],
            final_status=validation['final_status'],
            comment=validation['comment'],
            city_fact=validation['full_address'],
            source_kladr_check=validation['building_fias_guid'],
        )

    batch.status = 'validated'
    batch.save(update_fields=['status'])
    return batch


def _build_import_summary(batch_rows):
    rows = list(batch_rows)
    return {
        'processed': len(rows),
        'ready': sum(1 for row in rows if row.final_status == 'ready'),
        'blocked': sum(1 for row in rows if row.final_status == 'blocked'),
        'clarify': sum(1 for row in rows if row.final_status == 'clarify'),
        'imported': sum(1 for row in rows if row.final_status == 'imported'),
        'errors': sum(1 for row in rows if row.final_status == 'error'),
    }


def _ensure_company_binding(company, service_object, comment, on_date):
    from work_orders.models import CompanyObjectServicePeriod

    existing = (
        CompanyObjectServicePeriod.objects.select_related('company')
        .filter(object_id=service_object.service_object_id, is_active=True)
        .filter(date_from__lte=on_date)
        .filter(Q(date_to__isnull=True) | Q(date_to__gte=on_date))
        .order_by('-date_from')
        .first()
    )
    if existing:
        if existing.company_id != company.id:
            raise ValueError(f'В настоящий момент данный объект закреплен за другой организацией: "{existing.company.name}".')
        return existing, False

    binding = CompanyObjectServicePeriod.objects.create(
        company=company,
        object_id=service_object.service_object_id,
        date_from=on_date,
        comment=comment,
        is_active=True,
    )
    return binding, True


@transaction.atomic
def _import_service_object_for_company(address, company, user, unit_number=None, on_date=None):
    from address.models import Building, Unit
    from address.services import build_full_address, normalize_house_number, normalize_unit_number
    from address_extractor_service import AddressExtractor

    service = FiasAddressService()
    if not service.is_configured:
        raise ValueError('Не настроен FIAS_API_TOKEN.')

    extractor = AddressExtractor()
    components = extractor.extract_address_components(address)
    if unit_number and not components.get('apartment_number'):
        components['apartment_number'] = unit_number

    validation = extractor.validate_and_match_to_db(components)
    house_number = normalize_house_number(validation.get('house_number') or components.get('house_number'))
    street_guid = validation.get('street_fias_guid')
    house_guid = validation.get('fias_object_guid')
    unit_number_norm = normalize_unit_number(components.get('apartment_number') or unit_number)
    import_date = on_date or timezone.localdate()

    if not street_guid:
        raise ValueError('Улица не найдена в ФИАС. Дом не сохранен.')
    if not house_number:
        raise ValueError('Не удалось определить номер дома.')

    building = Building.objects.filter(pk=validation.get('building_id')).first() if validation.get('building_id') else None
    fias_result = service.resolve_building_with_fallback(components)
    if building is None and house_guid:
        building = Building.objects.filter(fias_guid=house_guid).first()
    if building is None:
        building = Building.objects.filter(street_fias_guid=street_guid, house_number=house_number).first()

    full_address = validation.get('address_full') or fias_result.get('full_address') or build_full_address(components)
    if building is None:
        building = Building.objects.create(
            fias_guid=house_guid or None,
            street_fias_guid=street_guid,
            house_number=house_number,
            full_address=full_address,
            created_by=user,
        )
        building_created = True
    else:
        building_created = False
        updated = False
        for field_name, value in (
            ('fias_guid', house_guid or building.fias_guid),
            ('street_fias_guid', street_guid),
            ('house_number', house_number),
            ('full_address', full_address),
        ):
            if value and getattr(building, field_name) != value:
                setattr(building, field_name, value)
                updated = True
        if updated:
            building.save(update_fields=['fias_guid', 'street_fias_guid', 'house_number', 'full_address', 'updated_at'])

    house_service_object, house_created = _get_or_create_service_object(building.id, unit_id=None)
    house_binding, house_binding_created = _ensure_company_binding(
        company,
        house_service_object,
        'Загружено из кабинета руководителя',
        import_date,
    )

    result_service_object = house_service_object
    unit_created = False
    unit_binding_created = False

    if unit_number_norm:
        unit = Unit.objects.filter(building_id=building.id, unit_number=unit_number_norm).first()
        if unit is None:
            unit = Unit.objects.create(building_id=building.id, unit_number=unit_number_norm)
            unit_created = True

        result_service_object, _ = _get_or_create_service_object(building.id, unit_id=unit.id)
        _, unit_binding_created = _ensure_company_binding(
            company,
            result_service_object,
            'Загружено из кабинета руководителя (квартира/помещение)',
            import_date,
        )

    created_anything = any([building_created, house_created, house_binding_created, unit_created, unit_binding_created])

    return {
        'status': 'created' if created_anything else 'skipped',
        'service_object': result_service_object,
        'binding': house_binding,
        'building_fias_guid': str(building.fias_guid) if building.fias_guid else '-',
        'message': (
            'Созданы объект дома и объект помещения, привязки обновлены.'
            if unit_number_norm and created_anything
            else 'Объект уже был привязан к вашей компании.'
            if not created_anything
            else 'Объект дома загружен и привязан к компании.'
        ),
    }


@login_required
def director_import_service_objects(request):
    from address.models import ImportBatch

    membership, workspace, response = _get_manager_workspace(request)
    if response:
        return response

    batch = None
    batch_id = request.POST.get('batch_id') or request.GET.get('batch_id')
    if batch_id:
        batch = ImportBatch.objects.filter(id=batch_id, company_id=workspace['company'].id).first()

    if request.method == 'POST':
        action = request.POST.get('action') or 'upload'
        planned_date = _parse_planned_date(request.POST.get('planned_date_from'))

        if action == 'upload':
            uploaded_file = request.FILES.get('import_file')
            if not uploaded_file:
                messages.error(request, 'Выберите XLSX или XLS файл для загрузки.')
            else:
                try:
                    batch = _stage_import_batch(uploaded_file, workspace['company'], request.user, planned_date)
                except ValueError as error:
                    messages.error(request, str(error))
                else:
                    messages.success(request, 'Файл проверен. Подтвердите импорт готовых строк.')
        elif action == 'confirm':
            if not batch:
                messages.error(request, 'Пакет импорта не найден.')
            else:
                ready_rows = list(batch.rows.filter(final_status='ready').order_by('row_no', 'id'))
                imported_count = 0
                error_count = 0
                for row in ready_rows:
                    try:
                        result = _import_service_object_for_company(
                            row.raw_address,
                            workspace['company'],
                            request.user,
                            unit_number=row.unit_number,
                            on_date=batch.planned_date_from,
                        )
                    except Exception as error:
                        row.final_status = 'error'
                        row.comment = str(error)
                        row.save(update_fields=['final_status', 'comment'])
                        error_count += 1
                    else:
                        row.final_status = 'imported'
                        row.comment = result['message']
                        row.source_kladr_check = result.get('building_fias_guid') or row.source_kladr_check
                        row.save(update_fields=['final_status', 'comment', 'source_kladr_check'])
                        imported_count += 1

                batch.status = 'failed' if error_count else 'imported'
                batch.save(update_fields=['status'])
                messages.success(request, f'Импортировано строк: {imported_count}.')
                if error_count:
                    messages.warning(request, f'Строк с ошибками: {error_count}.')

    batch_rows = []
    summary = None
    ready_rows_count = 0
    planned_date_value = timezone.localdate()
    if batch:
        batch_rows = list(batch.rows.order_by('row_no', 'id'))
        summary = _build_import_summary(batch_rows)
        ready_rows_count = summary['ready']
        planned_date_value = batch.planned_date_from

    context = {
        'company': workspace['company'],
        'batch': batch,
        'results': batch_rows,
        'summary': summary,
        'ready_rows_count': ready_rows_count,
        'planned_date_from': planned_date_value,
    }
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title
    return render(request, 'portal/company_object_import.html', context)


# ============================================================================
# Final runtime import overrides (last definition wins)
# ============================================================================

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

        dataframe = pd.read_excel(BytesIO(binary))
        rows = [tuple(dataframe.columns.tolist())]
        rows.extend(tuple(row) for row in dataframe.itertuples(index=False, name=None))

    if not rows:
        return []

    headers = [str(value).strip().lower() if value is not None else '' for value in rows[0]]
    data_rows = rows[1:]

    def _find_index(*candidates):
        for candidate in candidates:
            if candidate in headers:
                return headers.index(candidate)
        return None

    address_idx = _find_index('адрес', 'address', 'объект', 'объект обслуживания')
    city_idx = _find_index('город', 'город основной', 'city', 'city_main', 'gorod')
    street_idx = _find_index('улица', 'street', 'ulitsa')
    house_idx = _find_index('дом', 'house', 'nomerdoma')
    unit_idx = _find_index('квартира', 'помещение', 'unit', 'unit_number', 'nomerkvartiry')

    extracted_rows = []
    for row_number, row in enumerate(data_rows, start=2):
        address = ''
        if address_idx is not None and address_idx < len(row) and row[address_idx] is not None:
            address = str(row[address_idx]).strip()

        unit_number = ''
        if unit_idx is not None and unit_idx < len(row) and row[unit_idx] is not None:
            unit_number = str(row[unit_idx]).strip()

        if not address:
            city = str(row[city_idx]).strip() if city_idx is not None and city_idx < len(row) and row[city_idx] is not None else ''
            street = str(row[street_idx]).strip() if street_idx is not None and street_idx < len(row) and row[street_idx] is not None else ''
            house = str(row[house_idx]).strip() if house_idx is not None and house_idx < len(row) and row[house_idx] is not None else ''
            parts = []
            if city:
                parts.append(f'г {city}')
            if street:
                parts.append(f'ул {street}')
            if house:
                parts.append(f'д {house}')
            address = ', '.join(parts).strip(', ')

        if not address:
            continue

        extracted_rows.append({'row_number': row_number, 'address': address, 'unit_number': unit_number})

    return extracted_rows


@transaction.atomic
def _import_service_object_for_company(address, company, user, unit_number=None, on_date=None):
    from address.models import Building, Unit
    from address.services import build_full_address, normalize_house_number, normalize_unit_number
    from address_extractor_service import AddressExtractor

    service = FiasAddressService()
    if not service.is_configured:
        raise ValueError('Не настроен FIAS_API_TOKEN.')

    extractor = AddressExtractor()
    components = extractor.extract_address_components(address)
    if unit_number and not components.get('apartment_number'):
        components['apartment_number'] = unit_number

    validation = extractor.validate_and_match_to_db(components)
    house_number = normalize_house_number(validation.get('house_number') or components.get('house_number'))
    street_guid = validation.get('street_fias_guid')
    house_guid = validation.get('fias_object_guid')
    unit_number_norm = normalize_unit_number(components.get('apartment_number') or unit_number)
    import_date = on_date or timezone.localdate()

    if not street_guid:
        raise ValueError('Улица не найдена в ФИАС. Дом не сохранен.')
    if not house_number:
        raise ValueError('Не удалось определить номер дома.')

    building = Building.objects.filter(pk=validation.get('building_id')).first() if validation.get('building_id') else None
    fias_result = service.resolve_building_with_fallback(components)
    if building is None and house_guid:
        building = Building.objects.filter(fias_guid=house_guid).first()
    if building is None:
        building = Building.objects.filter(street_fias_guid=street_guid, house_number=house_number).first()

    full_address = validation.get('address_full') or fias_result.get('full_address') or build_full_address(components)
    if building is None:
        building = Building.objects.create(
            fias_guid=house_guid or None,
            street_fias_guid=street_guid,
            house_number=house_number,
            full_address=full_address,
            created_by=user,
        )
        building_created = True
    else:
        building_created = False
        updated = False
        for field_name, value in (
            ('fias_guid', house_guid or building.fias_guid),
            ('street_fias_guid', street_guid),
            ('house_number', house_number),
            ('full_address', full_address),
        ):
            if value and getattr(building, field_name) != value:
                setattr(building, field_name, value)
                updated = True
        if updated:
            building.save(update_fields=['fias_guid', 'street_fias_guid', 'house_number', 'full_address', 'updated_at'])

    house_service_object, house_created = _get_or_create_service_object(building.id, unit_id=None)
    house_binding, house_binding_created = _ensure_company_binding(
        company,
        house_service_object,
        'Загружено из кабинета руководителя',
        import_date,
    )

    result_service_object = house_service_object
    unit_created = False
    unit_binding_created = False

    if unit_number_norm:
        unit = Unit.objects.filter(building_id=building.id, unit_number=unit_number_norm).first()
        if unit is None:
            unit = Unit.objects.create(building_id=building.id, unit_number=unit_number_norm)
            unit_created = True

        result_service_object, _ = _get_or_create_service_object(building.id, unit_id=unit.id)
        _, unit_binding_created = _ensure_company_binding(
            company,
            result_service_object,
            'Загружено из кабинета руководителя (квартира/помещение)',
            import_date,
        )

    created_anything = any([building_created, house_created, house_binding_created, unit_created, unit_binding_created])
    return {
        'status': 'created' if created_anything else 'skipped',
        'service_object': result_service_object,
        'binding': house_binding,
        'building_fias_guid': str(building.fias_guid) if building.fias_guid else '-',
        'message': (
            'Созданы объект дома и объект помещения, привязки обновлены.'
            if unit_number_norm and created_anything
            else 'Объект уже был привязан к вашей компании.'
            if not created_anything
            else 'Объект дома загружен и привязан к компании.'
        ),
    }


@login_required
def director_import_service_objects(request):
    from address.models import ImportBatch

    membership, workspace, response = _get_manager_workspace(request)
    if response:
        return response

    batch = None
    batch_id = request.POST.get('batch_id') or request.GET.get('batch_id')
    if batch_id:
        batch = ImportBatch.objects.filter(id=batch_id, company_id=workspace['company'].id).first()

    if request.method == 'POST':
        action = request.POST.get('action') or 'upload'
        planned_date = _parse_planned_date(request.POST.get('planned_date_from'))

        if action == 'upload':
            uploaded_file = request.FILES.get('import_file')
            if not uploaded_file:
                messages.error(request, 'Выберите XLSX или XLS файл для загрузки.')
            else:
                try:
                    batch = _stage_import_batch(uploaded_file, workspace['company'], request.user, planned_date)
                except ValueError as error:
                    messages.error(request, str(error))
                else:
                    messages.success(request, 'Файл проверен. Подтвердите импорт готовых строк.')
        elif action == 'confirm':
            if not batch:
                messages.error(request, 'Пакет импорта не найден.')
            else:
                ready_rows = list(batch.rows.filter(final_status='ready').order_by('row_no', 'id'))
                imported_count = 0
                error_count = 0
                for row in ready_rows:
                    try:
                        result = _import_service_object_for_company(
                            row.raw_address,
                            workspace['company'],
                            request.user,
                            unit_number=row.unit_number,
                            on_date=batch.planned_date_from,
                        )
                    except Exception as error:
                        row.final_status = 'error'
                        row.comment = str(error)
                        row.save(update_fields=['final_status', 'comment'])
                        error_count += 1
                    else:
                        row.final_status = 'imported'
                        row.comment = result['message']
                        row.source_kladr_check = result.get('building_fias_guid') or row.source_kladr_check
                        row.save(update_fields=['final_status', 'comment', 'source_kladr_check'])
                        imported_count += 1

                batch.status = 'failed' if error_count else 'imported'
                batch.save(update_fields=['status'])
                messages.success(request, f'Импортировано строк: {imported_count}.')
                if error_count:
                    messages.warning(request, f'Строк с ошибками: {error_count}.')

    batch_rows = []
    summary = None
    ready_rows_count = 0
    planned_date_value = timezone.localdate()
    if batch:
        batch_rows = list(batch.rows.order_by('row_no', 'id'))
        summary = _build_import_summary(batch_rows)
        ready_rows_count = summary['ready']
        planned_date_value = batch.planned_date_from

    context = {
        'company': workspace['company'],
        'batch': batch,
        'results': batch_rows,
        'summary': summary,
        'ready_rows_count': ready_rows_count,
        'planned_date_from': planned_date_value,
    }
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title
    return render(request, 'portal/company_object_import.html', context)


# ============================================================================
# Final address import overrides
# ============================================================================

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

        dataframe = pd.read_excel(BytesIO(binary))
        rows = [tuple(dataframe.columns.tolist())]
        rows.extend(tuple(row) for row in dataframe.itertuples(index=False, name=None))

    if not rows:
        return []

    headers = [str(value).strip().lower() if value is not None else '' for value in rows[0]]
    data_rows = rows[1:]

    def _find_index(*candidates):
        for candidate in candidates:
            if candidate in headers:
                return headers.index(candidate)
        return None

    address_idx = _find_index('адрес', 'address', 'объект', 'объект обслуживания')
    city_idx = _find_index('город', 'город основной', 'city', 'city_main', 'gorod')
    street_idx = _find_index('улица', 'street', 'ulitsa')
    house_idx = _find_index('дом', 'house', 'nomerdoma')
    unit_idx = _find_index('квартира', 'помещение', 'unit', 'unit_number', 'nomerkvartiry')

    extracted_rows = []
    for row_number, row in enumerate(data_rows, start=2):
        address = ''
        if address_idx is not None and address_idx < len(row) and row[address_idx] is not None:
            address = str(row[address_idx]).strip()

        unit_number = ''
        if unit_idx is not None and unit_idx < len(row) and row[unit_idx] is not None:
            unit_number = str(row[unit_idx]).strip()

        if not address:
            city = str(row[city_idx]).strip() if city_idx is not None and city_idx < len(row) and row[city_idx] is not None else ''
            street = str(row[street_idx]).strip() if street_idx is not None and street_idx < len(row) and row[street_idx] is not None else ''
            house = str(row[house_idx]).strip() if house_idx is not None and house_idx < len(row) and row[house_idx] is not None else ''
            parts = []
            if city:
                parts.append(f'г {city}')
            if street:
                parts.append(f'ул {street}')
            if house:
                parts.append(f'д {house}')
            address = ', '.join(parts).strip(', ')

        if not address:
            continue

        extracted_rows.append({'row_number': row_number, 'address': address, 'unit_number': unit_number})

    return extracted_rows


@transaction.atomic
def _import_service_object_for_company(address, company, user, unit_number=None, on_date=None):
    from address.models import Building, Unit
    from address.services import build_full_address, normalize_house_number, normalize_unit_number
    from address_extractor_service import AddressExtractor

    service = FiasAddressService()
    if not service.is_configured:
        raise ValueError('Не настроен FIAS_API_TOKEN.')

    extractor = AddressExtractor()
    components = extractor.extract_address_components(address)
    if unit_number and not components.get('apartment_number'):
        components['apartment_number'] = unit_number

    validation = extractor.validate_and_match_to_db(components)
    house_number = normalize_house_number(validation.get('house_number') or components.get('house_number'))
    street_guid = validation.get('street_fias_guid')
    house_guid = validation.get('fias_object_guid')
    unit_number_norm = normalize_unit_number(components.get('apartment_number') or unit_number)
    import_date = on_date or timezone.localdate()

    if not street_guid:
        raise ValueError('Улица не найдена в ФИАС. Дом не сохранен.')
    if not house_number:
        raise ValueError('Не удалось определить номер дома.')

    building = Building.objects.filter(pk=validation.get('building_id')).first() if validation.get('building_id') else None
    fias_result = service.resolve_building_with_fallback(components)
    if building is None and house_guid:
        building = Building.objects.filter(fias_guid=house_guid).first()
    if building is None:
        building = Building.objects.filter(street_fias_guid=street_guid, house_number=house_number).first()

    full_address = validation.get('address_full') or fias_result.get('full_address') or build_full_address(components)
    if building is None:
        building = Building.objects.create(
            fias_guid=house_guid or None,
            street_fias_guid=street_guid,
            house_number=house_number,
            full_address=full_address,
            created_by=user,
        )
        building_created = True
    else:
        building_created = False
        updated = False
        for field_name, value in (
            ('fias_guid', house_guid or building.fias_guid),
            ('street_fias_guid', street_guid),
            ('house_number', house_number),
            ('full_address', full_address),
        ):
            if value and getattr(building, field_name) != value:
                setattr(building, field_name, value)
                updated = True
        if updated:
            building.save(update_fields=['fias_guid', 'street_fias_guid', 'house_number', 'full_address', 'updated_at'])

    house_service_object, house_created = _get_or_create_service_object(building.id, unit_id=None)
    house_binding, house_binding_created = _ensure_company_binding(
        company,
        house_service_object,
        'Загружено из кабинета руководителя',
        import_date,
    )

    result_service_object = house_service_object
    unit_created = False
    unit_binding_created = False

    if unit_number_norm:
        unit = Unit.objects.filter(building_id=building.id, unit_number=unit_number_norm).first()
        if unit is None:
            unit = Unit.objects.create(building_id=building.id, unit_number=unit_number_norm)
            unit_created = True

        result_service_object, _ = _get_or_create_service_object(building.id, unit_id=unit.id)
        _, unit_binding_created = _ensure_company_binding(
            company,
            result_service_object,
            'Загружено из кабинета руководителя (квартира/помещение)',
            import_date,
        )

    created_anything = any([building_created, house_created, house_binding_created, unit_created, unit_binding_created])
    return {
        'status': 'created' if created_anything else 'skipped',
        'service_object': result_service_object,
        'binding': house_binding,
        'building_fias_guid': str(building.fias_guid) if building.fias_guid else '-',
        'message': (
            'Созданы объект дома и объект помещения, привязки обновлены.'
            if unit_number_norm and created_anything
            else 'Объект уже был привязан к вашей компании.'
            if not created_anything
            else 'Объект дома загружен и привязан к компании.'
        ),
    }


@login_required
def director_import_service_objects(request):
    from address.models import ImportBatch

    membership, workspace, response = _get_manager_workspace(request)
    if response:
        return response

    batch = None
    batch_id = request.POST.get('batch_id') or request.GET.get('batch_id')
    if batch_id:
        batch = ImportBatch.objects.filter(id=batch_id, company_id=workspace['company'].id).first()

    if request.method == 'POST':
        action = request.POST.get('action') or 'upload'
        planned_date = _parse_planned_date(request.POST.get('planned_date_from'))

        if action == 'upload':
            uploaded_file = request.FILES.get('import_file')
            if not uploaded_file:
                messages.error(request, 'Выберите XLSX или XLS файл для загрузки.')
            else:
                try:
                    batch = _stage_import_batch(uploaded_file, workspace['company'], request.user, planned_date)
                except ValueError as error:
                    messages.error(request, str(error))
                else:
                    messages.success(request, 'Файл проверен. Подтвердите импорт готовых строк.')
        elif action == 'confirm':
            if not batch:
                messages.error(request, 'Пакет импорта не найден.')
            else:
                ready_rows = list(batch.rows.filter(final_status='ready').order_by('row_no', 'id'))
                imported_count = 0
                error_count = 0
                for row in ready_rows:
                    try:
                        result = _import_service_object_for_company(
                            row.raw_address,
                            workspace['company'],
                            request.user,
                            unit_number=row.unit_number,
                            on_date=batch.planned_date_from,
                        )
                    except Exception as error:
                        row.final_status = 'error'
                        row.comment = str(error)
                        row.save(update_fields=['final_status', 'comment'])
                        error_count += 1
                    else:
                        row.final_status = 'imported'
                        row.comment = result['message']
                        row.source_kladr_check = result.get('building_fias_guid') or row.source_kladr_check
                        row.save(update_fields=['final_status', 'comment', 'source_kladr_check'])
                        imported_count += 1

                batch.status = 'failed' if error_count else 'imported'
                batch.save(update_fields=['status'])
                messages.success(request, f'Импортировано строк: {imported_count}.')
                if error_count:
                    messages.warning(request, f'Строк с ошибками: {error_count}.')

    batch_rows = []
    summary = None
    ready_rows_count = 0
    planned_date_value = timezone.localdate()
    if batch:
        batch_rows = list(batch.rows.order_by('row_no', 'id'))
        summary = _build_import_summary(batch_rows)
        ready_rows_count = summary['ready']
        planned_date_value = batch.planned_date_from

    context = {
        'company': workspace['company'],
        'batch': batch,
        'results': batch_rows,
        'summary': summary,
        'ready_rows_count': ready_rows_count,
        'planned_date_from': planned_date_value,
    }
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title
    return render(request, 'portal/company_object_import.html', context)


def _parse_planned_date(raw_value):
    from datetime import date

    if raw_value:
        try:
            return date.fromisoformat(str(raw_value))
        except ValueError:
            pass
    return timezone.localdate()


def _get_object_binding_on_date(service_object_id, on_date):
    from work_orders.models import CompanyObjectServicePeriod

    return (
        CompanyObjectServicePeriod.objects.select_related('company')
        .filter(object_id=service_object_id, is_active=True)
        .filter(date_from__lte=on_date)
        .filter(Q(date_to__isnull=True) | Q(date_to__gte=on_date))
        .order_by('-date_from')
        .first()
    )


def _find_existing_address_entities(components, street_guid, house_guid, house_number, unit_number):
    from address.models import Building, Unit

    building = None
    if house_guid:
        building = Building.objects.filter(fias_guid=house_guid).first()
    if building is None and street_guid and house_number:
        building = Building.objects.filter(street_fias_guid=street_guid, house_number=house_number).first()

    unit = None
    if building is not None and unit_number:
        unit = Unit.objects.filter(building_id=building.id, unit_number=unit_number).first()
    return building, unit


def _validate_import_row_for_batch(address, unit_number, company, planned_date):
    from address.models import Building
    from address.services import build_full_address, normalize_house_number, normalize_unit_number
    from address_extractor_service import AddressExtractor

    extractor = AddressExtractor()
    service = FiasAddressService()
    components = extractor.extract_address_components(address)
    if unit_number and not components.get('apartment_number'):
        components['apartment_number'] = unit_number

    city = components.get('city')
    street = components.get('street')
    house_number = normalize_house_number(components.get('house_number'))
    unit_number_norm = normalize_unit_number(components.get('apartment_number') or unit_number)

    result = {
        'address': address,
        'city': city or '',
        'street': street or '',
        'house': house_number or '',
        'unit_number': unit_number_norm or '',
        'full_address': build_full_address(components),
        'building_fias_guid': '',
        'house_parse_status': '',
        'house_fias_status': '',
        'binding_status': '',
        'unit_status': '',
        'final_status': '',
        'comment': '',
    }

    missing = []
    if not city:
        missing.append('населенный пункт')
    if not street:
        missing.append('улица')
    if not house_number:
        missing.append('дом')
    if missing:
        result.update(
            {
                'house_parse_status': 'incomplete',
                'final_status': 'clarify',
                'comment': f"Неполный адрес: отсутствует {', '.join(missing)}.",
            }
        )
        return result

    fias_result = service.resolve_building_with_fallback(components)
    street_guid = fias_result.get('street_guid')
    house_guid = fias_result.get('house_guid')
    result['building_fias_guid'] = house_guid or ''
    result['full_address'] = fias_result.get('full_address') or result['full_address']
    result['house_parse_status'] = 'parsed'

    if not street_guid:
        result.update(
            {
                'house_fias_status': 'street_not_found',
                'final_status': 'clarify',
                'comment': 'Улица не найдена в ФИАС. Строку нельзя импортировать.',
            }
        )
        return result

    result['house_fias_status'] = 'house_matched' if house_guid else 'street_matched'
    building, unit = _find_existing_address_entities(components, street_guid, house_guid, house_number, unit_number_norm)

    if building is not None:
        house_service_object = (
            ServiceObject.objects.filter(building_id=building.id, unit_id__isnull=True, is_active=True)
            .order_by('service_object_id')
            .first()
        )
        if house_service_object:
            binding = _get_object_binding_on_date(house_service_object.service_object_id, planned_date)
            if binding and binding.company_id != company.id:
                result.update(
                    {
                        'binding_status': 'conflict',
                        'final_status': 'blocked',
                        'comment': f'Дом уже закреплен за компанией "{binding.company.name}" на указанную дату.',
                    }
                )
                return result
            if binding and binding.company_id == company.id:
                result['binding_status'] = 'same_company'
            else:
                result['binding_status'] = 'new_binding'
        else:
            result['binding_status'] = 'new_binding'
    else:
        result['binding_status'] = 'new_building'

    if unit_number_norm:
        if unit is not None:
            unit_service_object = (
                ServiceObject.objects.filter(building_id=building.id, unit_id=unit.id, is_active=True)
                .order_by('service_object_id')
                .first()
            )
            if unit_service_object:
                unit_binding = _get_object_binding_on_date(unit_service_object.service_object_id, planned_date)
                if unit_binding and unit_binding.company_id != company.id:
                    result.update(
                        {
                            'unit_status': 'conflict',
                            'final_status': 'blocked',
                            'comment': f'Квартира/помещение уже закреплена за компанией "{unit_binding.company.name}" на указанную дату.',
                        }
                    )
                    return result
                if unit_binding and unit_binding.company_id == company.id:
                    result['unit_status'] = 'same_company'
                else:
                    result['unit_status'] = 'existing_unit'
            else:
                result['unit_status'] = 'existing_unit'
        else:
            result['unit_status'] = 'new_unit'
    else:
        result['unit_status'] = 'house_only'

    if result['binding_status'] == 'same_company' and result['unit_status'] in {'', 'house_only', 'same_company'}:
        result.update(
            {
                'final_status': 'blocked',
                'comment': 'Объект уже привязан к вашей компании на указанную дату.',
            }
        )
        return result

    result.update(
        {
            'final_status': 'ready',
            'comment': 'Строка готова к импорту.',
        }
    )
    return result


def _stage_import_batch(uploaded_file, company, user, planned_date):
    from address.models import ImportBatch, ImportRow

    extracted_rows = _extract_import_rows(uploaded_file)
    if not extracted_rows:
        raise ValueError('В файле не найдено строк с адресами.')

    batch = ImportBatch.objects.create(
        company_id=company.id,
        uploaded_by=user,
        planned_date_from=planned_date,
        status='uploaded',
    )

    seen_rows = set()
    for row in extracted_rows:
        address = row['address']
        unit_number = (row.get('unit_number') or '').strip()
        dedupe_key = (' '.join(address.lower().split()), unit_number.lower())
        if dedupe_key in seen_rows:
            validation = {
                'address': address,
                'city': '',
                'street': '',
                'house': '',
                'unit_number': unit_number,
                'full_address': address,
                'building_fias_guid': '',
                'house_parse_status': 'duplicate',
                'house_fias_status': '',
                'binding_status': '',
                'unit_status': '',
                'final_status': 'blocked',
                'comment': 'Дубликат строки в загруженном файле.',
            }
        else:
            seen_rows.add(dedupe_key)
            validation = _validate_import_row_for_batch(address, unit_number, company, planned_date)

        ImportRow.objects.create(
            batch=batch,
            row_no=row['row_number'],
            raw_address=address,
            city_main=validation['city'],
            street=validation['street'],
            house=validation['house'],
            unit_number=validation['unit_number'],
            house_parse_status=validation['house_parse_status'],
            house_fias_status=validation['house_fias_status'],
            binding_status=validation['binding_status'],
            unit_status=validation['unit_status'],
            final_status=validation['final_status'],
            comment=validation['comment'],
            city_fact=validation['full_address'],
            source_kladr_check=validation['building_fias_guid'],
        )

    batch.status = 'validated'
    batch.save(update_fields=['status'])
    return batch


@transaction.atomic
def _import_service_object_for_company(address, company, user, unit_number=None, on_date=None):
    from address.models import Building, Unit
    from address.services import build_full_address, normalize_house_number, normalize_unit_number
    from address_extractor_service import AddressExtractor

    service = FiasAddressService()
    if not service.is_configured:
        raise ValueError('Не настроен FIAS_API_TOKEN.')

    extractor = AddressExtractor()
    components = extractor.extract_address_components(address)
    if unit_number and not components.get('apartment_number'):
        components['apartment_number'] = unit_number

    validation = extractor.validate_and_match_to_db(components)
    house_number = normalize_house_number(validation.get('house_number') or components.get('house_number'))
    street_guid = validation.get('street_fias_guid')
    house_guid = validation.get('fias_object_guid')
    unit_number_norm = normalize_unit_number(components.get('apartment_number') or unit_number)
    import_date = on_date or timezone.localdate()

    if not street_guid:
        raise ValueError('Улица не найдена в ФИАС. Дом не сохранен.')
    if not house_number:
        raise ValueError('Не удалось определить номер дома.')

    building = Building.objects.filter(pk=validation.get('building_id')).first() if validation.get('building_id') else None
    fias_result = service.resolve_building_with_fallback(components)
    if building is None and house_guid:
        building = Building.objects.filter(fias_guid=house_guid).first()
    if building is None:
        building = Building.objects.filter(street_fias_guid=street_guid, house_number=house_number).first()

    full_address = validation.get('address_full') or fias_result.get('full_address') or build_full_address(components)
    if building is None:
        building = Building.objects.create(
            fias_guid=house_guid or None,
            street_fias_guid=street_guid,
            house_number=house_number,
            full_address=full_address,
            created_by=user,
        )
        building_created = True
    else:
        building_created = False
        updated = False
        for field_name, value in (
            ('fias_guid', house_guid or building.fias_guid),
            ('street_fias_guid', street_guid),
            ('house_number', house_number),
            ('full_address', full_address),
        ):
            if value and getattr(building, field_name) != value:
                setattr(building, field_name, value)
                updated = True
        if updated:
            building.save(update_fields=['fias_guid', 'street_fias_guid', 'house_number', 'full_address', 'updated_at'])

    house_service_object, house_created = _get_or_create_service_object(building.id, unit_id=None)
    house_binding, house_binding_created = _ensure_company_binding(
        company,
        house_service_object,
        'Загружено из кабинета руководителя',
        import_date,
    )

    result_service_object = house_service_object
    unit_created = False
    unit_binding_created = False

    if unit_number_norm:
        unit = Unit.objects.filter(building_id=building.id, unit_number=unit_number_norm).first()
        if unit is None:
            unit = Unit.objects.create(building_id=building.id, unit_number=unit_number_norm)
            unit_created = True

        result_service_object, _ = _get_or_create_service_object(building.id, unit_id=unit.id)
        _, unit_binding_created = _ensure_company_binding(
            company,
            result_service_object,
            'Загружено из кабинета руководителя (квартира/помещение)',
            import_date,
        )

    created_anything = any([building_created, house_created, house_binding_created, unit_created, unit_binding_created])

    return {
        'status': 'created' if created_anything else 'skipped',
        'service_object': result_service_object,
        'binding': house_binding,
        'building_fias_guid': str(building.fias_guid) if building.fias_guid else '-',
        'message': (
            'Созданы объект дома и объект помещения, привязки обновлены.'
            if unit_number_norm and created_anything
            else 'Объект уже был привязан к вашей компании.'
            if not created_anything
            else 'Объект дома загружен и привязан к компании.'
        ),
    }


def _build_import_summary(batch_rows):
    rows = list(batch_rows)
    return {
        'processed': len(rows),
        'ready': sum(1 for row in rows if row.final_status == 'ready'),
        'blocked': sum(1 for row in rows if row.final_status == 'blocked'),
        'clarify': sum(1 for row in rows if row.final_status == 'clarify'),
        'imported': sum(1 for row in rows if row.final_status == 'imported'),
        'errors': sum(1 for row in rows if row.final_status == 'error'),
    }


@login_required
def director_import_service_objects(request):
    from address.models import ImportBatch

    membership, workspace, response = _get_manager_workspace(request)
    if response:
        return response

    batch = None
    batch_id = request.POST.get('batch_id') or request.GET.get('batch_id')
    if batch_id:
        batch = ImportBatch.objects.filter(id=batch_id, company_id=workspace['company'].id).first()

    if request.method == 'POST':
        action = request.POST.get('action') or 'upload'
        planned_date = _parse_planned_date(request.POST.get('planned_date_from'))

        if action == 'upload':
            uploaded_file = request.FILES.get('import_file')
            if not uploaded_file:
                messages.error(request, 'Выберите XLSX или XLS файл для загрузки.')
            else:
                try:
                    batch = _stage_import_batch(uploaded_file, workspace['company'], request.user, planned_date)
                except ValueError as error:
                    messages.error(request, str(error))
                else:
                    messages.success(request, 'Файл проверен. Подтвердите импорт готовых строк.')
        elif action == 'confirm':
            if not batch:
                messages.error(request, 'Пакет импорта не найден.')
            else:
                ready_rows = list(batch.rows.filter(final_status='ready').order_by('row_no', 'id'))
                imported_count = 0
                error_count = 0
                for row in ready_rows:
                    try:
                        result = _import_service_object_for_company(
                            row.raw_address,
                            workspace['company'],
                            request.user,
                            unit_number=row.unit_number,
                            on_date=batch.planned_date_from,
                        )
                    except Exception as error:
                        row.final_status = 'error'
                        row.comment = str(error)
                        row.save(update_fields=['final_status', 'comment'])
                        error_count += 1
                    else:
                        row.final_status = 'imported'
                        row.comment = result['message']
                        row.source_kladr_check = result.get('building_fias_guid') or row.source_kladr_check
                        row.save(update_fields=['final_status', 'comment', 'source_kladr_check'])
                        imported_count += 1

                batch.status = 'failed' if error_count else 'imported'
                batch.save(update_fields=['status'])
                messages.success(request, f'Импортировано строк: {imported_count}.')
                if error_count:
                    messages.warning(request, f'Строк с ошибками: {error_count}.')

    batch_rows = []
    summary = None
    ready_rows_count = 0
    planned_date_value = timezone.localdate()
    if batch:
        batch_rows = list(batch.rows.order_by('row_no', 'id'))
        summary = _build_import_summary(batch_rows)
        ready_rows_count = summary['ready']
        planned_date_value = batch.planned_date_from

    context = {
        'company': workspace['company'],
        'batch': batch,
        'results': batch_rows,
        'summary': summary,
        'ready_rows_count': ready_rows_count,
        'planned_date_from': planned_date_value,
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
    departments = departments.select_related('parent_department').order_by('parent_department_id', 'department_name', 'id')

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
        children.sort(key=lambda item: ((item.department_name or '').lower(), item.id))

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


@never_cache
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

    def _get_resident_draft_user(user_id=None, username=None):
        from work_orders.models import UserCompanyMembership

        queryset = User.objects.filter(is_superuser=False)
        if user_id:
            queryset = queryset.filter(id=user_id)
        elif username:
            queryset = queryset.filter(username=username)
        else:
            return None

        draft_user = queryset.select_related('userprofile').first()
        if not draft_user or draft_user.is_staff:
            return None

        has_active_membership = UserCompanyMembership.objects.filter(
            user=draft_user,
            is_active=True,
            date_to__isnull=True,
        ).exists()
        if has_active_membership:
            return None
        return draft_user

    def _get_active_membership_user(user_id=None, username=None):
        from work_orders.models import UserCompanyMembership

        queryset = User.objects.all()
        if user_id:
            queryset = queryset.filter(id=user_id)
        elif username:
            queryset = queryset.filter(username=username)
        else:
            return None, None

        existing_user = queryset.first()
        if not existing_user:
            return None, None

        active_membership = (
            UserCompanyMembership.objects
            .filter(user=existing_user, is_active=True, date_to__isnull=True)
            .select_related('company')
            .first()
        )
        return existing_user, active_membership

    superuser_without_membership = request.user.is_superuser and not membership
    companies = None
    company_id = membership.company_id if membership else None
    selected_company_id = request.POST.get('company') or request.GET.get('company')
    selected_department_id = request.POST.get('department') or request.GET.get('department') or ''
    draft_user_id = request.POST.get('draft_user_id') or request.GET.get('draft_user_id')
    account_type = (request.POST.get('account_type') or request.GET.get('account_type') or 'resident').strip().lower()
    if account_type not in {'resident', 'employee'}:
        account_type = 'resident'
    draft_user = None
    draft_candidate = None

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

    if draft_user_id:
        try:
            draft_user = _get_resident_draft_user(user_id=int(draft_user_id))
        except (TypeError, ValueError):
            draft_user = None

    # Обработка формы
    if request.method == 'POST':
        existing_user, existing_membership = _get_active_membership_user(
            user_id=draft_user_id,
            username=(request.POST.get('username') or '').strip() or None,
        )
        if existing_membership:
            if company_id and existing_membership.company_id == company_id:
                messages.info(
                    request,
                    f'Пользователь {existing_user.username} уже оформлен в компании {existing_membership.company.name}.'
                )
                return redirect('portal:director_residents')
            messages.warning(
                request,
                f'Пользователь {existing_user.username} уже привязан к компании {existing_membership.company.name}.'
            )
            return redirect('portal:director_residents')

        from portal.forms import AddResidentForm
        form = AddResidentForm(request.POST, allowed_existing_user_id=draft_user.id if draft_user else None)
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

        username = (request.POST.get('username') or '').strip()
        if not draft_user and username:
            draft_candidate = _get_resident_draft_user(username=username)
            if draft_candidate and not form_valid:
                form.fields['username'].help_text = (
                    'Этот логин уже занят черновиком без привязки. '
                    'Можно подтянуть его в карточку и завершить оформление.'
                )

        if form_valid:
            from django.core.exceptions import ValidationError as DjangoValidationError
            try:
                with transaction.atomic():
                    if draft_user:
                        user = draft_user
                        user.username = form.cleaned_data['username']
                        user.email = form.cleaned_data.get('email', '')
                        user.first_name = form.cleaned_data.get('first_name', '')
                        user.last_name = form.cleaned_data.get('last_name', '')
                        user.is_staff = False
                        user.set_password(form.cleaned_data['password'])
                        user.save()
                    else:
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
                            raise ValueError('department_required')
                        try:
                            department = CompanyDepartment.objects.get(
                                id=int(department_id),
                                company_id=company_id
                            )
                        except CompanyDepartment.DoesNotExist:
                            messages.error(request, 'Указанное подразделение не найдено!')
                            raise ValueError('department_missing')
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
                    membership = UserCompanyMembership(
                        user=user,
                        company_id=company_id,
                        department=department,
                        role_code=role_code,
                        is_primary=True,
                        is_active=True,
                        date_from=timezone.now()
                    )
                    membership.full_clean()
                    membership.save()

                    profile.role = 'resident' if role_code == 'resident' else 'uk_user'
                    profile.primary_company_id = company_id
                    profile.primary_department = department
                    profile.phone = form.cleaned_data.get('phone', '')
                    profile.address = form.cleaned_data.get('address', '')
                    if role_code == 'chief_engineer':
                        profile.job_title = 'chief_engineer'
                    profile.save()
            except DjangoValidationError as exc:
                if hasattr(exc, 'message_dict'):
                    for field_name, field_errors in exc.message_dict.items():
                        target_field = 'role' if field_name == 'role_code' else field_name
                        for field_error in field_errors:
                            if target_field in form.fields:
                                form.add_error(target_field, field_error)
                            else:
                                form.add_error(None, field_error)
                else:
                    form.add_error(None, '; '.join(exc.messages))
                return render(request, 'portal/director_add_resident.html', {
                    'company': workspace['company'],
                    'form': form,
                    'departments': departments,
                    'companies': companies,
                    'selected_company_id': str(company_id) if company_id else '',
                    'selected_department_id': str(selected_department_id) if selected_department_id else '',
                    'superuser_without_membership': superuser_without_membership,
                    'account_type': account_type,
                    'page_title': 'Добавить жителя' if account_type == 'resident' else 'Добавить сотрудника',
                    'draft_user': draft_user,
                    'draft_candidate': draft_candidate,
                })
            except ValueError:
                return render(request, 'portal/director_add_resident.html', {
                    'company': workspace['company'],
                    'form': form,
                    'departments': departments,
                    'companies': companies,
                    'selected_company_id': str(company_id) if company_id else '',
                    'selected_department_id': str(selected_department_id) if selected_department_id else '',
                    'superuser_without_membership': superuser_without_membership,
                    'account_type': account_type,
                    'page_title': 'Добавить жителя' if account_type == 'resident' else 'Добавить сотрудника',
                    'draft_user': draft_user,
                    'draft_candidate': draft_candidate,
                })

            if draft_user:
                messages.success(request, f'Черновик {user.username} успешно завершен и привязан к компании!')
            else:
                messages.success(request, f'Пользователь {user.username} успешно создан!')
            return redirect('portal:director_residents')
    else:
        from portal.forms import AddResidentForm
        initial = {}
        if draft_user:
            initial = {
                'username': draft_user.username,
                'email': draft_user.email,
                'first_name': draft_user.first_name,
                'last_name': draft_user.last_name,
            }
            try:
                profile = draft_user.userprofile
            except UserProfile.DoesNotExist:
                profile = None
            if profile:
                initial['phone'] = profile.phone or ''
                initial['address'] = profile.address or ''
                if profile.primary_department_id:
                    selected_department_id = str(profile.primary_department_id)
        form = AddResidentForm(initial=initial, allowed_existing_user_id=draft_user.id if draft_user else None)
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
        'selected_department_id': str(selected_department_id) if selected_department_id else '',
        'superuser_without_membership': superuser_without_membership,
        'account_type': account_type,
        'page_title': 'Добавить жителя' if account_type == 'resident' else 'Добавить сотрудника',
        'draft_user': draft_user,
        'draft_candidate': draft_candidate,
    }

    # Breadcrumbs для возврата на правильный дашборд
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title

    return render(request, 'portal/director_add_resident.html', context)


@never_cache
@login_required
def director_edit_resident(request, membership_id):
    """
    Редактирование учетной записи в ЛК директора/главного инженера.
    """
    current_membership = get_primary_membership(request.user)
    if not current_membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, current_membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, current_membership)

    if not request.user.is_superuser and current_membership.role_code not in ['direktor_uk', 'chief_engineer']:
        messages.error(request, 'Доступ разрешен только Директорам УК и Главным инженерам')
        return redirect('portal:welcome')

    company_scope = workspace['company_scope']

    from work_orders.models import UserCompanyMembership, CompanyDepartment

    membership_qs = (
        UserCompanyMembership.objects
        .filter(id=membership_id, is_active=True, date_to__isnull=True)
        .select_related('user', 'company', 'department')
    )
    if company_scope:
        if isinstance(company_scope, (list, tuple, set)):
            membership_qs = membership_qs.filter(company_id__in=company_scope)
        else:
            membership_qs = membership_qs.filter(company_id=company_scope)

    target_membership = membership_qs.first()
    if not target_membership:
        messages.error(request, 'Учетная запись не найдена или недоступна для редактирования')
        return redirect('portal:director_residents')

    target_user = target_membership.user
    account_type = 'resident' if target_membership.role_code == 'resident' else 'employee'
    departments = (
        CompanyDepartment.objects
        .filter(company_id=target_membership.company_id, is_active=True)
        .select_related('company')
        .order_by('company__name', 'department_name')
    )

    def build_context(form, selected_department_id=None):
        dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
        return {
            'company': target_membership.company,
            'form': form,
            'departments': departments,
            'companies': None,
            'selected_company_id': str(target_membership.company_id),
            'selected_department_id': str(selected_department_id if selected_department_id is not None else (target_membership.department_id or '')),
            'superuser_without_membership': False,
            'account_type': account_type,
            'page_title': 'Редактировать жителя' if account_type == 'resident' else 'Редактировать сотрудника',
            'submit_label': 'Сохранить изменения',
            'edit_mode': True,
            'draft_user': None,
            'draft_candidate': None,
            'dashboard_url': dashboard_url,
            'dashboard_title': dashboard_title,
        }

    from portal.forms import AddResidentForm

    if request.method == 'POST':
        selected_department_id = request.POST.get('department') or ''
        form = AddResidentForm(
            request.POST,
            instance=target_user,
            allowed_existing_user_id=target_user.id,
            password_required=False,
        )
        if account_type == 'resident':
            form.fields['role'].choices = [('resident', 'Житель')]
            form.fields['role'].initial = 'resident'
        else:
            form.fields['role'].choices = [
                ('executor', 'Исполнитель'),
                ('chief_engineer', 'Главный инженер'),
            ]
            form.fields['role'].initial = request.POST.get('role') or target_membership.role_code

        if form.is_valid():
            from django.core.exceptions import ValidationError as DjangoValidationError
            try:
                with transaction.atomic():
                    target_user.username = form.cleaned_data['username']
                    target_user.email = form.cleaned_data.get('email', '')
                    target_user.first_name = form.cleaned_data.get('first_name', '')
                    target_user.last_name = form.cleaned_data.get('last_name', '')
                    target_user.is_staff = False
                    if form.cleaned_data.get('password'):
                        target_user.set_password(form.cleaned_data['password'])
                    target_user.save()

                    from portal.models import UserProfile
                    profile, created = UserProfile.objects.get_or_create(
                        user=target_user,
                        defaults={
                            'timezone': 'Europe/Moscow',
                            'role': 'uk_user',
                        }
                    )

                    department = None
                    role_code = form.cleaned_data['role']

                    if role_code in ['executor', 'chief_engineer']:
                        if not selected_department_id:
                            messages.error(request, 'Для сотрудников обязательно укажите подразделение!')
                            raise ValueError('department_required')
                        try:
                            department = CompanyDepartment.objects.get(
                                id=int(selected_department_id),
                                company_id=target_membership.company_id,
                            )
                        except CompanyDepartment.DoesNotExist:
                            messages.error(request, 'Указанное подразделение не найдено!')
                            raise ValueError('department_missing')
                    elif selected_department_id:
                        try:
                            department = CompanyDepartment.objects.get(
                                id=int(selected_department_id),
                                company_id=target_membership.company_id,
                            )
                        except CompanyDepartment.DoesNotExist:
                            department = None

                    target_membership.role_code = role_code
                    target_membership.department = department
                    target_membership.full_clean()
                    target_membership.save()

                    profile.role = 'resident' if role_code == 'resident' else 'uk_user'
                    profile.primary_company_id = target_membership.company_id
                    profile.primary_department = department
                    profile.phone = form.cleaned_data.get('phone', '')
                    profile.address = form.cleaned_data.get('address', '')
                    profile.job_title = 'chief_engineer' if role_code == 'chief_engineer' else None
                    profile.save()
            except DjangoValidationError as exc:
                if hasattr(exc, 'message_dict'):
                    for field_name, field_errors in exc.message_dict.items():
                        target_field = 'role' if field_name == 'role_code' else field_name
                        for field_error in field_errors:
                            if target_field in form.fields:
                                form.add_error(target_field, field_error)
                            else:
                                form.add_error(None, field_error)
                else:
                    form.add_error(None, '; '.join(exc.messages))
                return render(request, 'portal/director_add_resident.html', build_context(form, selected_department_id))
            except ValueError:
                return render(request, 'portal/director_add_resident.html', build_context(form, selected_department_id))

            messages.success(request, f'Данные пользователя {target_user.username} обновлены')
            return redirect('portal:director_residents')
    else:
        from portal.models import UserProfile
        try:
            profile = target_user.userprofile
        except UserProfile.DoesNotExist:
            profile = None

        form = AddResidentForm(
            initial={
                'username': target_user.username,
                'email': target_user.email,
                'first_name': target_user.first_name,
                'last_name': target_user.last_name,
                'phone': profile.phone if profile else '',
                'address': profile.address if profile else '',
                'role': target_membership.role_code,
            },
            instance=target_user,
            allowed_existing_user_id=target_user.id,
            password_required=False,
        )
        if account_type == 'resident':
            form.fields['role'].choices = [('resident', 'Житель')]
            form.fields['role'].initial = 'resident'
        else:
            form.fields['role'].choices = [
                ('executor', 'Исполнитель'),
                ('chief_engineer', 'Главный инженер'),
            ]
            form.fields['role'].initial = target_membership.role_code

    return render(request, 'portal/director_add_resident.html', build_context(form))


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
    departments = departments.select_related('company', 'parent_department').order_by(
        'company__name',
        'parent_department_id',
        'department_name',
        'id',
    )

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
    ).exclude(id=department_id).select_related('company', 'parent_department').order_by(
        'parent_department_id',
        'department_name',
        'id',
    )

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


# ============================================================================
# Address v2 overrides
# ============================================================================

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

        dataframe = pd.read_excel(BytesIO(binary))
        rows = [tuple(dataframe.columns.tolist())]
        rows.extend(tuple(row) for row in dataframe.itertuples(index=False, name=None))

    if not rows:
        return []

    headers = [str(value).strip().lower() if value is not None else '' for value in rows[0]]
    data_rows = rows[1:]

    def _find_index(*candidates):
        for candidate in candidates:
            if candidate in headers:
                return headers.index(candidate)
        return None

    address_idx = _find_index('адрес', 'address', 'объект', 'объект обслуживания')
    city_idx = _find_index('город', 'город основной', 'city', 'city_main', 'gorod')
    street_idx = _find_index('улица', 'street', 'ulitsa')
    house_idx = _find_index('дом', 'house', 'nomerdoma')
    unit_idx = _find_index('квартира', 'помещение', 'unit', 'unit_number', 'nomerkvartiry')

    extracted_rows = []
    for row_number, row in enumerate(data_rows, start=2):
        address = ''
        if address_idx is not None and address_idx < len(row) and row[address_idx] is not None:
            address = str(row[address_idx]).strip()

        unit_number = ''
        if unit_idx is not None and unit_idx < len(row) and row[unit_idx] is not None:
            unit_number = str(row[unit_idx]).strip()

        if not address:
            city = str(row[city_idx]).strip() if city_idx is not None and city_idx < len(row) and row[city_idx] is not None else ''
            street = str(row[street_idx]).strip() if street_idx is not None and street_idx < len(row) and row[street_idx] is not None else ''
            house = str(row[house_idx]).strip() if house_idx is not None and house_idx < len(row) and row[house_idx] is not None else ''
            parts = []
            if city:
                parts.append(f'г {city}')
            if street:
                parts.append(f'ул {street}')
            if house:
                parts.append(f'д {house}')
            address = ', '.join(parts).strip(', ')

        if not address:
            continue

        extracted_rows.append(
            {
                'row_number': row_number,
                'address': address,
                'unit_number': unit_number,
            }
        )

    return extracted_rows


def _get_or_create_service_object(building_id, unit_id=None):
    service_object = (
        ServiceObject.objects.filter(building_id=building_id, unit_id=unit_id, is_active=True)
        .order_by('service_object_id')
        .first()
    )
    if service_object:
        return service_object, False

    service_object = ServiceObject.objects.create(
        building_id=building_id,
        unit_id=unit_id,
        created_at=timezone.now(),
        is_active=True,
    )
    return service_object, True


def _ensure_company_binding(company, service_object, comment, on_date):
    from work_orders.models import CompanyObjectServicePeriod

    existing = (
        CompanyObjectServicePeriod.objects.select_related('company')
        .filter(object_id=service_object.service_object_id, is_active=True)
        .filter(date_from__lte=on_date)
        .filter(Q(date_to__isnull=True) | Q(date_to__gte=on_date))
        .order_by('-date_from')
        .first()
    )
    if existing:
        if existing.company_id != company.id:
            raise ValueError(
                f'В настоящий момент данный объект закреплен за другой организацией: "{existing.company.name}".'
            )
        return existing, False

    binding = CompanyObjectServicePeriod.objects.create(
        company=company,
        object_id=service_object.service_object_id,
        date_from=on_date,
        comment=comment,
        is_active=True,
    )
    return binding, True


@transaction.atomic
def _import_service_object_for_company(address, company, user, unit_number=None, on_date=None):
    from address.models import Building, Unit
    from address.services import build_full_address, normalize_house_number, normalize_unit_number
    from address_extractor_service import AddressExtractor

    service = FiasAddressService()
    if not service.is_configured:
        raise ValueError('?? ???????? FIAS_API_TOKEN.')

    extractor = AddressExtractor()
    components = extractor.extract_address_components(address)
    if unit_number and not components.get('apartment_number'):
        components['apartment_number'] = unit_number

    validation = extractor.validate_and_match_to_db(components)
    house_number = normalize_house_number(validation.get('house_number') or components.get('house_number'))
    street_guid = validation.get('street_fias_guid')
    house_guid = validation.get('fias_object_guid')
    unit_number_norm = normalize_unit_number(components.get('apartment_number') or unit_number)
    import_date = on_date or timezone.localdate()

    if not street_guid:
        raise ValueError('????? ?? ??????? ? ????. ??? ?? ????????.')
    if not house_number:
        raise ValueError('?? ??????? ?????????? ????? ????.')

    building = Building.objects.filter(pk=validation.get('building_id')).first() if validation.get('building_id') else None
    fias_result = service.resolve_building_with_fallback(components)
    if building is None and house_guid:
        building = Building.objects.filter(fias_guid=house_guid).first()
    if building is None:
        building = Building.objects.filter(street_fias_guid=street_guid, house_number=house_number).first()

    full_address = validation.get('address_full') or fias_result.get('full_address') or build_full_address(components)
    if building is None:
        building = Building.objects.create(
            fias_guid=house_guid or None,
            street_fias_guid=street_guid,
            house_number=house_number,
            full_address=full_address,
            created_by=user,
        )
        building_created = True
    else:
        building_created = False
        updated = False
        for field_name, value in (
            ('fias_guid', house_guid or building.fias_guid),
            ('street_fias_guid', street_guid),
            ('house_number', house_number),
            ('full_address', full_address),
        ):
            if value and getattr(building, field_name) != value:
                setattr(building, field_name, value)
                updated = True
        if updated:
            building.save(update_fields=['fias_guid', 'street_fias_guid', 'house_number', 'full_address', 'updated_at'])

    house_service_object, house_created = _get_or_create_service_object(building.id, unit_id=None)
    house_binding, house_binding_created = _ensure_company_binding(
        company,
        house_service_object,
        '????????? ?? ???????? ????????????',
        import_date,
    )

    result_service_object = house_service_object
    unit_created = False
    unit_binding_created = False

    if unit_number_norm:
        unit = Unit.objects.filter(building_id=building.id, unit_number=unit_number_norm).first()
        if unit is None:
            unit = Unit.objects.create(building_id=building.id, unit_number=unit_number_norm)
            unit_created = True

        result_service_object, _ = _get_or_create_service_object(building.id, unit_id=unit.id)
        _, unit_binding_created = _ensure_company_binding(
            company,
            result_service_object,
            '????????? ?? ???????? ???????????? (????????/?????????)',
            import_date,
        )

    created_anything = any([building_created, house_created, house_binding_created, unit_created, unit_binding_created])

    return {
        'status': 'created' if created_anything else 'skipped',
        'service_object': result_service_object,
        'binding': house_binding,
        'building_fias_guid': str(building.fias_guid) if building.fias_guid else '-',
        'message': (
            '??????? ?????? ???? ? ?????? ?????????, ???????? ?????????.'
            if unit_number_norm and created_anything
            else '?????? ??? ??? ???????? ? ????? ????????.'
            if not created_anything
            else '?????? ???? ???????? ? ???????? ? ????????.'
        ),
    }


@login_required
def director_import_service_objects(request):
    from address.models import ImportBatch

    membership, workspace, response = _get_manager_workspace(request)
    if response:
        return response

    batch = None
    batch_id = request.POST.get('batch_id') or request.GET.get('batch_id')
    if batch_id:
        batch = ImportBatch.objects.filter(id=batch_id, company_id=workspace['company'].id).first()

    if request.method == 'POST':
        action = request.POST.get('action') or 'upload'
        planned_date = _parse_planned_date(request.POST.get('planned_date_from'))

        if action == 'upload':
            uploaded_file = request.FILES.get('import_file')
            if not uploaded_file:
                messages.error(request, '???????? XLSX ??? XLS ???? ??? ????????.')
            else:
                try:
                    batch = _stage_import_batch(uploaded_file, workspace['company'], request.user, planned_date)
                except ValueError as error:
                    messages.error(request, str(error))
                else:
                    messages.success(request, '???? ????????. ??????????? ?????? ??????? ?????.')
        elif action == 'confirm':
            if not batch:
                messages.error(request, '????? ??????? ?? ??????.')
            else:
                ready_rows = list(batch.rows.filter(final_status='ready').order_by('row_no', 'id'))
                imported_count = 0
                error_count = 0
                for row in ready_rows:
                    try:
                        result = _import_service_object_for_company(
                            row.raw_address,
                            workspace['company'],
                            request.user,
                            unit_number=row.unit_number,
                            on_date=batch.planned_date_from,
                        )
                    except Exception as error:
                        row.final_status = 'error'
                        row.comment = str(error)
                        row.save(update_fields=['final_status', 'comment'])
                        error_count += 1
                    else:
                        row.final_status = 'imported'
                        row.comment = result['message']
                        row.source_kladr_check = result.get('building_fias_guid') or row.source_kladr_check
                        row.save(update_fields=['final_status', 'comment', 'source_kladr_check'])
                        imported_count += 1

                batch.status = 'failed' if error_count else 'imported'
                batch.save(update_fields=['status'])
                messages.success(request, f'????????????? ?????: {imported_count}.')
                if error_count:
                    messages.warning(request, f'????? ? ????????: {error_count}.')

    batch_rows = []
    summary = None
    ready_rows_count = 0
    planned_date_value = timezone.localdate()
    if batch:
        batch_rows = list(batch.rows.order_by('row_no', 'id'))
        summary = _build_import_summary(batch_rows)
        ready_rows_count = summary['ready']
        planned_date_value = batch.planned_date_from

    context = {
        'company': workspace['company'],
        'batch': batch,
        'results': batch_rows,
        'summary': summary,
        'ready_rows_count': ready_rows_count,
        'planned_date_from': planned_date_value,
    }
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title
    return render(request, 'portal/company_object_import.html', context)
