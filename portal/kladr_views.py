"""
Представления для управления КЛАДР в административном интерфейсе
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.urls import reverse

from kladr.models import KladrAddressObject, Building, ServiceArea, KladrObjectType, DataImportLog


@login_required
def kladr_management(request):
    """Главная страница управления КЛАДР"""
    # Проверка прав доступа
    if not request.user.userprofile.has_admin_access():
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:admin_page')

    # Статистика
    stats = {
        'address_objects': KladrAddressObject.objects.count(),
        'buildings': Building.objects.count(),
        'service_areas': ServiceArea.objects.count(),
        'active_objects': KladrAddressObject.objects.filter(is_active=True).count(),
    }

    # Последние операции импорта
    recent_imports = DataImportLog.objects.all()[:5]

    context = {
        'stats': stats,
        'recent_imports': recent_imports,
    }
    return render(request, 'portal/kladr/management.html', context)


@login_required
def kladr_objects_list(request):
    """Список адресных объектов КЛАДР"""
    if not request.user.userprofile.has_admin_access():
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:admin_page')

    # Получаем параметры фильтрации
    level = request.GET.get('level')
    search = request.GET.get('search', '')
    is_active = request.GET.get('is_active')

    # Базовый queryset
    objects = KladrAddressObject.objects.select_related('type', 'parent').all()

    # Применяем фильтры
    if level:
        objects = objects.filter(type__level=level)

    if search:
        objects = objects.filter(
            Q(name__icontains=search) |
            Q(code__icontains=search) |
            Q(zip_code__icontains=search)
        )

    if is_active is not None:
        objects = objects.filter(is_active=is_active == 'true')

    # Сортировка
    objects = objects.order_by('type__level', 'name')

    # Пагинация
    paginator = Paginator(objects, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Данные для фильтров
    levels = KladrObjectType.LEVEL_CHOICES

    context = {
        'page_obj': page_obj,
        'levels': levels,
        'current_level': level,
        'search': search,
        'current_active': is_active,
        'total_count': objects.count(),
    }
    return render(request, 'portal/kladr/objects_list.html', context)


@login_required
def kladr_object_detail(request, object_id):
    """Детальная информация об адресном объекте"""
    if not request.user.userprofile.has_admin_access():
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:admin_page')

    obj = get_object_or_404(KladrAddressObject, id=object_id)

    # Получаем дочерние объекты
    children = KladrAddressObject.objects.filter(parent=obj)

    # Получаем здания для этого объекта (если это улица)
    buildings = Building.objects.filter(address_object=obj) if obj.type.level == 5 else []

    context = {
        'object': obj,
        'children': children,
        'buildings': buildings,
    }
    return render(request, 'portal/kladr/object_detail.html', context)


@login_required
def buildings_list(request):
    """Список зданий"""
    if not request.user.userprofile.has_admin_access():
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:admin_page')

    # Получаем параметры фильтрации
    search = request.GET.get('search', '')
    street_id = request.GET.get('street')

    # Базовый queryset
    buildings = Building.objects.select_related('address_object', 'address_object__type').all()

    # Применяем фильтры
    if search:
        buildings = buildings.filter(
            Q(house_number__icontains=search) |
            Q(address_object__name__icontains=search) |
            Q(building_type__icontains=search)
        )

    if street_id:
        buildings = buildings.filter(address_object_id=street_id)

    # Сортировка
    buildings = buildings.order_by('address_object__name', 'house_number')

    # Пагинация
    paginator = Paginator(buildings, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Получаем улицы для фильтра
    streets = KladrAddressObject.objects.filter(type__level=5).order_by('name')

    context = {
        'page_obj': page_obj,
        'streets': streets,
        'current_street': street_id,
        'search': search,
        'total_count': buildings.count(),
    }
    return render(request, 'portal/kladr/buildings_list.html', context)


@login_required
def building_detail(request, building_id):
    """Детальная информация о здании"""
    if not request.user.userprofile.has_admin_access():
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:admin_page')

    building = get_object_or_404(Building, id=building_id)

    # Получаем зоны обслуживания, в которые входит это здание
    service_areas = building.servicearea_set.all()

    context = {
        'building': building,
        'service_areas': service_areas,
    }
    return render(request, 'portal/kladr/building_detail.html', context)


@login_required
def service_areas_list(request):
    """Список зон обслуживания"""
    if not request.user.userprofile.has_admin_access():
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:admin_page')

    # Получаем параметры фильтрации
    search = request.GET.get('search', '')

    # Базовый queryset с аннотацией количества зданий
    areas = ServiceArea.objects.prefetch_related('buildings').annotate(
        building_count=Count('buildings')
    ).all()

    # Применяем фильтры
    if search:
        areas = areas.filter(name__icontains=search)

    # Сортировка
    areas = areas.order_by('name')

    # Пагинация
    paginator = Paginator(areas, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search': search,
        'total_count': areas.count(),
    }
    return render(request, 'portal/kladr/service_areas_list.html', context)


@login_required
def service_area_detail(request, area_id):
    """Детальная информация о зоне обслуживания"""
    if not request.user.userprofile.has_admin_access():
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:admin_page')

    area = get_object_or_404(ServiceArea, id=area_id)
    buildings = area.buildings.select_related('address_object').all()

    context = {
        'area': area,
        'buildings': buildings,
    }
    return render(request, 'portal/kladr/service_area_detail.html', context)


@login_required
def import_logs_list(request):
    """Список логов импорта данных"""
    if not request.user.userprofile.has_admin_access():
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:admin_page')

    logs = DataImportLog.objects.select_related('created_by').all().order_by('-started_at')

    # Пагинация
    paginator = Paginator(logs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'total_count': logs.count(),
    }
    return render(request, 'portal/kladr/import_logs.html', context)


@login_required
def api_search_kladr(request):
    """API для поиска адресных объектов"""
    if not request.user.userprofile.has_admin_access():
        return JsonResponse({'error': 'Доступ запрещен'}, status=403)

    query = request.GET.get('q', '')
    level = request.GET.get('level')

    if len(query) < 2:
        return JsonResponse({'results': []})

    objects = KladrAddressObject.objects.select_related('type').filter(
        name__icontains=query
    )

    if level:
        objects = objects.filter(type__level=level)

    results = []
    for obj in objects[:20]:  # Ограничиваем количество результатов
        results.append({
            'id': obj.id,
            'name': obj.name,
            'full_address': obj.get_full_address(),
            'type': obj.type.name,
            'level': obj.type.level,
            'code': obj.code,
        })

    return JsonResponse({'results': results})