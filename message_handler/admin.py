from django.contrib import admin
from django.utils.safestring import mark_safe
from django.utils.html import escape
from asgiref.sync import sync_to_async
import json
import asyncio
import numpy as np
import inspect
from datetime import datetime
from .models import MessageLog, APIErrorLog


# ========================================
# ДИНАМИЧЕСКОЕ ЧТЕНИЕ КОДА (inspect)
# ========================================

def get_code_info(module_path, class_name, method_name):
    """
    Динамически читает код и возвращает актуальную информацию

    Args:
        module_path: Путь к модулю (например, 'message_handler_service')
        class_name: Имя класса
        method_name: Имя метода

    Returns:
        dict: Информация о методе
    """
    try:
        # Импортируем модуль
        import importlib
        module = importlib.import_module(module_path)

        # Получаем класс
        cls = getattr(module, class_name)

        # Получаем метод
        method = getattr(cls, method_name)

        # Получаем исходный код
        source = inspect.getsource(method)
        lines = source.split('\n')

        # Вычисляем строки в исходном файле
        source_file = inspect.getsourcefile(method)
        with open(source_file, 'r') as f:
            file_lines = f.readlines()

        # Находим начало метода в файле
        method_start_line = None
        method_def = f'def {method_name}'

        for i, line in enumerate(file_lines, 1):
            if method_def in line:
                method_start_line = i
                break

        return {
            'source': source,
            'total_lines': len(lines),
            'start_line': method_start_line,
            'end_line': method_start_line + len(lines) if method_start_line else None,
            'file': source_file
        }
    except Exception as e:
        return {
            'error': str(e),
            'source': None,
            'total_lines': 0,
            'start_line': None,
            'end_line': None,
            'file': None
        }


def find_all_steps_in_code(source):
    """
    АВТОМАТИЧЕСКИ находит ВСЕ шаги в коде промпта

    Ищет строки вида "## Шаг X", "## Шаг X." и извлекает информацию

    Args:
        source: Исходный код метода

    Returns:
        list: Список найденных шагов [{'number': '2', 'line': 48, 'text': '...'}, ...]
    """
    if not source:
        return []

    steps_found = []
    lines = source.split('\n')

    for i, line in enumerate(lines, 1):
        # Ищем строки с "## Шаг" (кириллица)
        if '## Шаг' in line:
            # Извлекаем номер шага
            import re
            # Паттерны: "## Шаг 2", "## Шаг 2.", "## Шаг 2.2"
            match = re.search(r'## Шаг\s+(\d+\.?\d*)\.?', line)
            if match:
                step_number = match.group(1)
                steps_found.append({
                    'number': step_number,
                    'line': i,
                    'text': line.strip(),
                    'full_context_start': max(0, i - 2),
                    'full_context_end': min(len(lines), i + 3)
                })

    return steps_found


def find_step_by_keywords(source, keywords):
    """
    Ищет конкретный шаг по ключевым словам

    Args:
        source: Исходный код метода
        keywords: Список ключевых слов

    Returns:
        dict: Информация о найденном шаге
    """
    if not source:
        return None

    lines = source.split('\n')
    for i, line in enumerate(lines, 1):
        for keyword in keywords:
            if keyword.lower() in line.lower():
                context_start = max(0, i - 5)
                context_end = min(len(lines), i + 5)
                context = '\n'.join([f"{j+1}: {line}" for j, line in enumerate(lines[context_start:context_end], context_start)])

                return {
                    'line': i,
                    'keyword': keyword,
                    'context': context
                }

    return None


def detect_aggregation_bug(source_code):
    """
    ДИНАМИЧЕСКИ определяет метод агрегации confidence (AVG или MAX)

    Args:
        source_code: Исходный код метода _deduplicate_and_prioritize_candidates

    Returns:
        dict: ФАКТЫ о методе агрегации
    """
    if not source_code:
        return None

    lines = source_code.split('\n')

    # Ищем строку с avg_confidence
    avg_line = None
    for i, line in enumerate(lines):
        if 'avg_confidence' in line.lower() and '=' in line:
            avg_line = i + 1
            break

    # Ищем строку с max_confidence
    max_line = None
    for i, line in enumerate(lines):
        if 'max_confidence' in line.lower() and '=' in line:
            max_line = i + 1
            break

    # Определяем что используется (ФАКТЫ)
    if avg_line and not max_line:
        return {
            'detected': True,
            'aggregation': 'AVG',
            'line': avg_line
        }
    elif max_line and not avg_line:
        return {
            'detected': True,
            'aggregation': 'MAX',
            'line': max_line
        }
    else:
        return {
            'detected': False
        }


def detect_missing_param_in_method(source_code, param_name):
    """
    ДИНАМИЧЕСКИ проверяет передается ли параметр в метод

    Args:
        source_code: Исходный код метода
        param_name: Имя параметра для поиска

    Returns:
        dict: Информация о наличии параметра
    """
    if not source_code:
        return None

    # Парсим сигнатуру метода
    lines = source_code.split('\n')
    signature_line = lines[0] if lines else ''

    # Проверяем есть ли параметр в сигнатуре
    param_present = param_name in signature_line

    return {
        'param_name': param_name,
        'present_in_signature': param_present,
        'signature': signature_line.strip()
    }


@admin.register(MessageLog)
class MessageLogAdmin(admin.ModelAdmin):
    """Админка для логов сообщений - УЛУЧШЕННАЯ"""

    # Список с ключевыми полями
    list_display = [
        'timestamp',
        'channel',
        'direction',
        'user_id',
        'text_preview',
        'service_detected_preview',
        'category_preview',
        'session_id'
    ]

    list_filter = ['channel', 'direction', 'message_type', 'processing_stage', 'timestamp']
    search_fields = ['message_content', 'user_id', 'session_id', 'message_id']

    date_hierarchy = 'timestamp'

    # Только чтение - все поля
    readonly_fields = [
        'timestamp',
        'channel_display',
        'direction_display',
        'user_id',
        'session_id',
        'text_content_display',
        'service_detected_display',
        'txtPrb_display',
        'accumulated_fields_display',
        'established_filters_display',
        'ai_orchestrator_display',
        'microservices_results_display',
        'performance_display',
        # Ольга (2026-01-18): Визуализация архитектуры обработки сообщения
        'logic_visualization_display',
    ]

    # Группировка полей на детальной странице
    fieldsets = (
        ('Основное', {
            'fields': ('timestamp', 'channel_display', 'direction_display', 'user_id', 'session_id')
        }),
        ('Содержание сообщения', {
            'fields': ('text_content_display',)
        }),
        ('Блокнот (txtPrb) и накопленные поля', {
            'fields': ('txtPrb_display', 'accumulated_fields_display'),
            'classes': ('wide',),
            'description': 'Извлеченная и накопленная информация из диалога'
        }),
        ('Установленные фильтры', {
            'fields': ('established_filters_display',),
            'classes': ('wide',),
            'description': 'Фильтры каталога (категория, локация, тип инцидента)'
        }),
        ('Результат определения услуги', {
            'fields': ('service_detected_display', 'ai_orchestrator_display', 'microservices_results_display'),
            'classes': ('wide',),
            'description': 'Кандидаты услуг и решение AI Orchestrator'
        }),
        # Ольга (2026-01-18): Визуализация архитектуры обработки сообщения
        ('Архитектура (логика обработки)', {
            'fields': ('logic_visualization_display',),
            'classes': ('wide',),
            'description': '🏗️ Пошаговая визуализация процесса обработки сообщения (структура кода + реальные данные)'
        }),
        ('Актуальные промпты (зеркало кода)', {
            'fields': ('current_prompts_display',),
            'classes': ('wide',),
            'description': '📝 Показывает промпты которые СЕЙЧАС используются в коде (динамическое чтение через inspect)'
        }),
        ('Производительность', {
            'fields': ('performance_display',),
            'classes': ('collapse',),
        }),
    )

    def text_preview(self, obj):
        """Предпросмотр текста (обрезанный)"""
        content = obj.message_content if hasattr(obj, 'message_content') else ''
        if content:
            return content[:80] + '...' if len(content) > 80 else content
        return '-'
    text_preview.short_description = 'Текст'

    def service_detected_preview(self, obj):
        """Предпросмотр услуги в списке"""
        metadata = self._get_metadata(obj)
        service_id = metadata.get('service_id')
        service_name = metadata.get('service_name')

        if service_id:
            return f'ID:{service_id} - {service_name[:30] if service_name else ""}'
        return '-'
    service_detected_preview.short_description = 'Услуга'

    def category_preview(self, obj):
        """Предпросмотр категории в списке"""
        metadata = self._get_metadata(obj)
        filters = metadata.get('established_filters', {})

        if filters and isinstance(filters, dict):
            category = filters.get('category', {})
            if isinstance(category, dict):
                return category.get('value', '-')
        return '-'
    category_preview.short_description = 'Категория'

    def channel_display(self, obj):
        """Канал связи с цветовой индикацией"""
        channel_colors = {
            'telegram': '#0088cc',
            'web': '#28a745',
            'whatsapp': '#25D366',
            'test_bot': '#6c757d',
        }
        color = channel_colors.get(obj.channel, '#6c757d')
        return mark_safe(f'<span style="color: {color}; font-weight: bold;">{obj.get_channel_display()}</span>')
    channel_display.short_description = 'Канал'

    def direction_display(self, obj):
        """Направление с иконкой"""
        icon = '→' if obj.direction == 'inbound' else '←'
        color = '#28a745' if obj.direction == 'inbound' else '#dc3545'
        return mark_safe(f'<span style="color: {color}; font-weight: bold;">{icon} {obj.get_direction_display()}</span>')
    direction_display.short_description = 'Направление'

    def text_content_display(self, obj):
        """Текст сообщения с форматированием"""
        return mark_safe(f'<div style="background: #f8f9fa; padding: 15px; border-radius: 5px; border-left: 4px solid #007bff; white-space: pre-wrap;">{escape(obj.message_content)}</div>')
    text_content_display.short_description = 'Текст сообщения'

    def _get_metadata(self, obj):
        """Безопасное извлечение metadata"""
        if obj.metadata:
            if isinstance(obj.metadata, dict):
                return obj.metadata
            elif isinstance(obj.metadata, str):
                try:
                    return json.loads(obj.metadata)
                except:
                    pass
        return {}

    def service_detected_display(self, obj):
        """Определенная услуга"""
        metadata = self._get_metadata(obj)

        # Пытаемся найти service_id и service_name
        service_id = metadata.get('service_id')
        service_name = metadata.get('service_name')

        # Проверяем в candidates
        if not service_id:
            candidates = metadata.get('candidates', [])
            if candidates and isinstance(candidates, list) and len(candidates) > 0:
                service_id = candidates[0].get('service_id') if isinstance(candidates[0], dict) else None
                service_name = candidates[0].get('service_name') if isinstance(candidates[0], dict) else None

        if service_id:
            confidence = metadata.get('confidence', 0)
            conf_pct = int(confidence * 100) if confidence <= 1 else int(confidence)
            conf_color = '#28a745' if conf_pct >= 70 else '#ffc107' if conf_pct >= 40 else '#dc3545'

            return mark_safe(f'''
                <div style="border: 2px solid #007bff; padding: 10px; border-radius: 5px; background: #f0f8ff;">
                    <div style="font-size: 14px; font-weight: bold; color: #007bff;">
                        Услуга ID: {service_id}
                    </div>
                    <div style="font-size: 16px; margin: 5px 0;">
                        {escape(service_name) if service_name else 'Не указано'}
                    </div>
                    <div style="margin-top: 5px;">
                        <span style="background: {conf_color}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 12px;">
                            Confidence: {conf_pct}%
                        </span>
                    </div>
                </div>
            ''')

        # Если услуга не определена
        stage = metadata.get('processing_stage', 'unknown')
        return mark_safe(f'<span style="color: #6c757d; font-style: italic;">Не определено (stage: {stage})</span>')
    service_detected_display.short_description = 'Определенная услуга'

    def txtPrb_display(self, obj):
        """Блокнот с накопленным описанием проблемы"""
        metadata = self._get_metadata(obj)
        txtPrb = metadata.get('txtPrb', '')

        if not txtPrb:
            return mark_safe('<span style="color: #dc3545; font-style: italic;">Пусто (еще не заполнено)</span>')

        return mark_safe(f'''
            <div style="background: #fff3cd; padding: 15px; border-radius: 5px; border-left: 5px solid #ffc107;">
                <div style="font-weight: bold; color: #856404; margin-bottom: 10px;">Блокнот (txtPrb):</div>
                <div style="font-size: 14px; color: #333; white-space: pre-wrap;">{escape(txtPrb)}</div>
            </div>
        ''')
    txtPrb_display.short_description = 'Блокнот (txtPrb)'

    def accumulated_fields_display(self, obj):
        """Накопленные поля"""
        metadata = self._get_metadata(obj)
        fields = metadata.get('accumulated_fields', {})

        if not fields:
            return mark_safe('<span style="color: #6c757d;">Нет данных</span>')

        rows = []
        for key, value in fields.items():
            if value:
                icon_map = {
                    'problem': '🔴',
                    'location': '📍',
                    'source': '🔧',
                    'category': '📁',
                    'object': '🏠',
                    'severity': '⚠️',
                    'intensity': '💪',
                }
                icon = icon_map.get(key, '•')
                rows.append(f'<tr><td style="padding: 5px; font-weight: bold;">{icon} {key}</td><td style="padding: 5px;">{escape(str(value))}</td></tr>')

        if not rows:
            return mark_safe('<span style="color: #6c757d;">Нет значимых данных</span>')

        return mark_safe(f'''
            <table style="width: 100%; border-collapse: collapse;">
                {"".join(rows)}
            </table>
        ''')
    accumulated_fields_display.short_description = 'Накопленные поля'

    def established_filters_display(self, obj):
        """Установленные фильтры"""
        metadata = self._get_metadata(obj)
        filters = metadata.get('established_filters', {})

        if not filters:
            return mark_safe('<span style="color: #6c757d;">Фильтры не установлены</span>')

        badges = []
        for filter_name, filter_data in filters.items():
            if isinstance(filter_data, dict):
                value = filter_data.get('value', 'N/A')
                confidence = filter_data.get('confidence', 0)
                conf_pct = int(confidence * 100) if confidence <= 1 else int(confidence)

                # Цвет по уверенности
                if conf_pct >= 80:
                    color = '#28a745'
                elif conf_pct >= 60:
                    color = '#ffc107'
                else:
                    color = '#dc3545'

                badges.append(f'<span style="background: {color}; color: white; padding: 5px 10px; border-radius: 4px; margin-right: 5px; margin-bottom: 5px; display: inline-block;">{filter_name}: {escape(str(value))} ({conf_pct}%)</span>')

        return mark_safe(f'<div style="line-height: 2;">{"".join(badges)}</div>')
    established_filters_display.short_description = 'Установленные фильтры'

    def ai_orchestrator_display(self, obj):
        """Результат AI Orchestrator"""
        metadata = self._get_metadata(obj)
        orchestrator = metadata.get('ai_orchestrator', {})

        if not orchestrator:
            return mark_safe('<span style="color: #6c757d;">Нет данных AI Orchestrator</span>')

        status = orchestrator.get('status', 'unknown')
        message = orchestrator.get('message', '')
        service_name = orchestrator.get('service_name', '')

        # Цвет статуса
        status_colors = {
            'SUCCESS': '#28a745',
            'AMBIGUOUS': '#ffc107',
            'ERROR': '#dc3545',
        }
        status_color = status_colors.get(status, '#6c757d')

        return mark_safe(f'''
            <div style="border: 2px solid {status_color}; padding: 12px; border-radius: 5px; background: #f8f9fa;">
                <div style="margin-bottom: 8px;">
                    <span style="background: {status_color}; color: white; padding: 3px 8px; border-radius: 3px; font-weight: bold;">STATUS: {escape(status)}</span>
                </div>
                {f'<div style="font-size: 15px; font-weight: bold; margin: 8px 0;">{escape(service_name)}</div>' if service_name else ''}
                <div style="margin-top: 8px; padding: 8px; background: white; border-radius: 3px;">
                    <strong>Сообщение:</strong> {escape(message)}
                </div>
            </div>
        ''')
    ai_orchestrator_display.short_description = 'AI Orchestrator'

    def microservices_results_display(self, obj):
        """Результаты микросервисов"""
        metadata = self._get_metadata(obj)
        microservices = metadata.get('microservices_results', {})

        if not microservices:
            return mark_safe('<span style="color: #6c757d;">Нет данных микросервисов</span>')

        sections = []
        for service_name, result in microservices.items():
            if isinstance(result, dict):
                status = result.get('status', 'unknown')
                candidates = result.get('candidates', [])

                # Цвет статуса
                status_color = '#28a745' if status == 'success' else '#dc3545' if status == 'error' else '#ffc107'

                # Кандидаты
                candidates_html = ''
                if candidates:
                    cand_items = []
                    for cand in candidates[:3]:  # Максимум 3 кандидата
                        if isinstance(cand, dict):
                            name = cand.get('service_name', cand.get('object', 'N/A'))
                            conf = cand.get('confidence', 0)
                            conf_pct = int(conf * 100) if conf <= 1 else int(conf)
                            cand_items.append(f'• {escape(str(name))} ({conf_pct}%)')
                    candidates_html = f'<div style="margin-top: 5px; font-size: 12px; color: #555;">{"<br>".join(cand_items)}</div>'

                sections.append(f'''
                    <div style="margin-bottom: 10px; padding: 8px; border-left: 3px solid {status_color}; background: #f8f9fa;">
                        <div style="font-weight: bold; color: {status_color};">{service_name}</div>
                        {candidates_html}
                    </div>
                ''')

        return mark_safe(f'<div style="max-height: 300px; overflow-y: auto;">{"".join(sections)}</div>')
    microservices_results_display.short_description = 'Результаты микросервисов'

    def performance_display(self, obj):
        """Производительность"""
        items = []

        if obj.processing_time_ms:
            time_sec = obj.processing_time_ms / 1000
            items.append(f'Время обработки: <strong>{time_sec:.2f} сек</strong>')

        if obj.tokens_used:
            items.append(f'Токены: <strong>{obj.tokens_used}</strong>')

        if obj.cost_rub:
            items.append(f'Стоимость: <strong>{obj.cost_rub:.4f} руб</strong>')

        if obj.llm_provider:
            items.append(f'LLM: <strong>{escape(obj.llm_provider)} / {escape(obj.llm_model or "N/A")}</strong>')

        if not items:
            return mark_safe('<span style="color: #6c757d;">Нет данных</span>')

        return mark_safe(f'<div style="line-height: 1.8;">{"".join(f"<div>{item}</div>" for item in items)}</div>')
    performance_display.short_description = 'Производительность'

    def current_prompts_display(self, obj):
        """
        Актуальные промпты из кода (ЗЕРКАЛО)

        ДИНАМИЧЕСКИ читает исходный код и показывает промпты которые СЕЙЧАС используются.
        Если промпт в коде меняется - админка автоматически покажет новую версию.
        """
        html_parts = []

        # ===== ПРОМПТ 1: FilterDetectionService =====
        try:
            filter_code = get_code_info(
                'filter_detection_service',
                'FilterDetectionService',
                '_create_filter_detection_prompt'
            )

            if filter_code.get('source'):
                # Извлекаем промпт из исходного кода
                source_lines = filter_code['source'].split('\n')

                # Ищем где начинается промпт (обычно после docstring)
                prompt_started = False
                prompt_lines = []

                for line in source_lines:
                    # Пропускаем пустые строки и комментарии в начале
                    if not prompt_started:
                        if line.strip().startswith('"""') or line.strip().startswith("'''"):
                            prompt_started = True
                            continue
                        if line.strip() and not line.strip().startswith('#'):
                            # Начался код без строки-разделителя
                            if 'return' in line or 'prompt' in line.lower():
                                prompt_started = True
                            continue
                        continue

                    # Собираем строки промпта до return
                    if 'return' in line and 'prompt' in line.lower():
                        break
                    if line.strip():
                        prompt_lines.append(line)

                prompt_text = '\n'.join(prompt_lines).strip()

                # Если промпт не найден, показываем весь метод
                if not prompt_text or len(prompt_text) < 50:
                    prompt_text = filter_code['source']

                html_parts.append(f'''
                    <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                        <h4 style="color: #495057; margin-bottom: 10px;">
                            📋 FilterDetectionService промпт
                        </h4>
                        <div style="font-size: 11px; color: #6c757d; margin-bottom: 10px;">
                            📁 Файл: filter_detection_service.py<br>
                            📍 Метод: FilterDetectionService._create_filter_detection_prompt()<br>
                            🔢 Строки: {filter_code['start_line']}-{filter_code['end_line']}
                        </div>
                        <pre style="background: #ffffff; padding: 15px; border-radius: 5px; font-size: 11px; max-height: 600px; overflow: auto; white-space: pre-wrap; border: 1px solid #dee2e6;">{escape(prompt_text[:5000])}{'...' if len(prompt_text) > 5000 else ''}</pre>
                    </div>
                ''')
            else:
                html_parts.append(f'''
                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                        ⚠️ Не удалось прочитать FilterDetectionService: {filter_code.get('error', 'Неизвестная ошибка')}
                    </div>
                ''')
        except Exception as e:
            html_parts.append(f'''
                <div style="background: #ffe6e6; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                    ❌ Ошибка чтения FilterDetectionService: {escape(str(e)[:100])}
                </div>
            ''')

        # ===== ПРОМПТ 2: AI Agent ( Orchestrator) =====
        try:
            ai_code = get_code_info(
                'main_agent',
                'MainAgent',
                '_build_dynamic_prompt'
            )

            if ai_code.get('source'):
                source_lines = ai_code['source'].split('\n')

                # Ищем системный промпт
                system_prompt_started = False
                system_prompt_lines = []

                for i, line in enumerate(source_lines):
                    # Ищем начало системного блока
                    if 'system_block' in line or 'Система' in line or 'Ты - AI' in line:
                        system_prompt_started = True

                    if system_prompt_started:
                        # Собираем до конца строки или закрывающих кавычек
                        system_prompt_lines.append(line)
                        if "'''" in line or '"""' in line:
                            # Проверяем что это закрывающая кавычка
                            if system_prompt_lines.count("'''") >= 2 or system_prompt_lines.count('"""') >= 2:
                                break

                        # Ограничиваем длину
                        if len(system_prompt_lines) > 50:
                            break

                system_prompt_text = '\n'.join(system_prompt_lines).strip()

                # Если не нашли, показываем ключевые части
                if not system_prompt_text or len(system_prompt_text) < 30:
                    # Ищем строки с описанием задачи
                    task_lines = []
                    for line in source_lines:
                        if any(keyword in line for keyword in ['ТВОЯ ЗАДАЧА', 'Ты - ', 'Стратегии:']):
                            task_lines.append(line)
                            if len(task_lines) > 20:
                                break
                    system_prompt_text = '\n'.join(task_lines) if task_lines else ai_code['source'][:1000]

                html_parts.append(f'''
                    <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                        <h4 style="color: #495057; margin-bottom: 10px;">
                            🤖 AI Orchestrator промпт
                        </h4>
                        <div style="font-size: 11px; color: #6c757d; margin-bottom: 10px;">
                            📁 Файл: main_agent.py<br>
                            📍 Метод: MainAgent._build_dynamic_prompt()<br>
                            🔢 Строки: {ai_code['start_line']}-{ai_code['end_line']}
                        </div>
                        <pre style="background: #ffffff; padding: 15px; border-radius: 5px; font-size: 11px; max-height: 600px; overflow: auto; white-space: pre-wrap; border: 1px solid #dee2e6;">{escape(system_prompt_text[:5000])}{'...' if len(system_prompt_text) > 5000 else ''}</pre>
                    </div>
                ''')
            else:
                html_parts.append(f'''
                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                        ⚠️ Не удалось прочитать MainAgent: {ai_code.get('error', 'Неизвестная ошибка')}
                    </div>
                ''')
        except Exception as e:
            html_parts.append(f'''
                <div style="background: #ffe6e6; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                    ❌ Ошибка чтения MainAgent: {escape(str(e)[:100])}
                </div>
            ''')

        # ===== ИНФОРМАЦИЯ: Актуальность =====
        html_parts.insert(0, f'''
            <div style="background: #d1ecf1; padding: 10px; border-radius: 5px; margin-bottom: 15px; border-left: 5px solid #0c5460;">
                <div style="font-size: 13px; color: #0c5460;">
                    <strong>🔄 ДИНАМИЧЕСКОЕ ЧТЕНИЕ КОДА</strong><br>
                    Промпты читаются из исходного кода через Python inspect.<br>
                    Если промпт в коде меняется → админка АВТОМАТИЧЕСКИ покажет новую версию.<br>
                    Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </div>
            </div>
        ''')

        return mark_safe(''.join(html_parts))

    current_prompts_display.short_description = 'Актуальные промпты'

    # ИСПРАВЛЕНИЕ (2026-02-02): Упрощенное отображение для outbound сообщений
    def _render_outbound_display(self, obj, metadata, service_result):
        """
        Упрощенная визуализация для outbound сообщений

        Outbound сообщения не проходят через MainAgent, это просто логирование ответа бота.
        Показываем только текст ответа и связь с inbound сообщением.
        """
        html_parts = []

        # Заголовок
        html_parts.append('''
            <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                <h2 style="margin: 0; font-size: 24px;">📤 Ответ бота</h2>
                <div style="margin-top: 10px; font-size: 14px; opacity: 0.9;">Упрощенное отображение (логирование ответа)</div>
            </div>
        ''')

        # Текст ответа
        response_text = obj.message_content or ''

        html_parts.append(f'''
            <div style="background: #d4edda; padding: 15px; border-radius: 5px; border-left: 5px solid #28a745; margin-bottom: 20px;">
                <div style="font-weight: bold; color: #155724; margin-bottom: 10px; font-size: 16px;">💬 Текст ответа:</div>
                <div style="font-size: 15px; color: #212529; white-space: pre-wrap;">{escape(response_text)}</div>
            </div>
        ''')

        # Информация об ответе
        info_parts = []
        info_parts.append(f"📨 Message ID: {obj.message_id if hasattr(obj, 'message_id') else 'N/A'}")
        info_parts.append(f"⏰ Время: {obj.timestamp if hasattr(obj, 'timestamp') else 'N/A'}")
        info_parts.append(f"👤 Пользователь: {obj.user_id}")
        info_parts.append(f"📡 Канал: {obj.channel}")
        info_parts.append(f"🆔 Сессия: {obj.session_id}")

        html_parts.append(f'''
            <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; border-left: 4px solid #6c757d; margin-bottom: 20px;">
                <div style="font-weight: bold; margin-bottom: 10px; color: #495057;">ℹ️ Информация:</div>
                <div style="line-height: 1.8;">{'<br>'.join(info_parts)}</div>
            </div>
        ''')

        # Пояснение что это логирование
        html_parts.append(f'''
            <div style="background: #fff3cd; padding: 15px; border-radius: 5px; border-left: 5px solid #ffc107; margin-bottom: 20px;">
                <div style="font-weight: bold; color: #856404; margin-bottom: 10px;">⚠️ Важно:</div>
                <div style="color: #856404; line-height: 1.6;">
                    Это <strong>outbound сообщение</strong> (ответ бота).<br>
                    Оно <strong>не проходит</strong> через обработку MainAgent.<br>
                    Это просто <strong>логирование ответа</strong> в БД для истории диалога.<br>
                    <br>
                    Чтобы увидеть архитектуру обработки - откройте <strong>inbound сообщение</strong>,
                    которое вызвало этот ответ.
                </div>
            </div>
        ''')

        # Попытка найти связанное inbound сообщение
        try:
            from .models import MessageLog
            related_inbound = MessageLog.objects.filter(
                session_id=obj.session_id,
                direction='inbound'
            ).order_by('-timestamp').first()

            if related_inbound:
                html_parts.append(f'''
                    <div style="background: #e7f3ff; padding: 15px; border-radius: 5px; border-left: 5px solid #007bff;">
                        <div style="font-weight: bold; color: #004085; margin-bottom: 10px;">🔗 Связанное inbound сообщение:</div>
                        <div style="color: #004085;">
                            📝 Текст: {escape(related_inbound.message_content[:80])}{'...' if len(related_inbound.message_content) > 80 else ''}<br>
                            ⏰ Время: {related_inbound.timestamp}<br>
                            📨 Message ID: {related_inbound.message_id}<br>
                        </div>
                    </div>
                ''')
        except Exception as e:
            pass

        return mark_safe(''.join(html_parts))

    # Ольга (2026-01-18): Визуализация логики обработки сообщения по шагам
    # Показывает архитектуру процесса от ввода до создания заявки
    # ИСПРАВЛЕНО (2026-02-02): Для outbound упрощенная визуализация
    def logic_visualization_display(self, obj):
        """
        Визуализация логики обработки сообщения (ARCHITECTURE FLOW)

        Для inbound: Показывает пошаговый процесс
        1. Ввод сообщения
        2. ProblemAccumulationService → accumulated_fields
        3. FilterDetectionService → established_filters
        4. Микросервисы (Vector, Tag, Semantic)
        5. AI Orchestrator → решение
        6. Создание заявки или вопрос

        Для outbound: Показывает только информацию об ответе
        (архитектура не применима - это просто логирование ответа)

        Подсвечивает проблемные места 🔴
        """
        metadata = self._get_metadata(obj)
        service_result = metadata.get('service_result', {})
        microservices = metadata.get('microservices_results', {})

        # === ИСПРАВЛЕНИЕ (2026-02-02): Для outbound упрощенная визуализация ===
        # Outbound сообщения не проходят через MainAgent, это просто INSERT в БД
        if hasattr(obj, 'direction') and obj.direction == 'outbound':
            return self._render_outbound_display(obj, metadata, service_result)

        # Извлекаем ai_orchestrator заранее (используется в ШАГ 2 и ШАГ 6)
        ai_orchestrator = service_result.get('_metadata', {}).get('ai_orchestrator', {})

        # Собираем данные для каждого шага
        steps = []

        # ШАГ 1: Ввод сообщения (INSERT в БД - ПРАВДА о том что заполнено)
        # ИСПРАВЛЕНО (2026-01-19): Показываем metadata НА МОМЕНТ INSERT, не финальный!
        user_message = obj.message_content or ''
        timestamp = obj.timestamp if hasattr(obj, 'timestamp') else 'N/A'
        message_id = obj.message_id if hasattr(obj, 'message_id') else 'N/A'
        direction = obj.direction if hasattr(obj, 'direction') else 'N/A'
        message_type = obj.message_type if hasattr(obj, 'message_type') else 'N/A'
        dialog_id = obj.dialog_id if hasattr(obj, 'dialog_id') else 'N/A'
        django_user_id = obj.django_user_id if hasattr(obj, 'django_user_id') else None

        # Основные поля (9 штук) - каждая строка отдельно
        step1_basic = [
            f"⏰ Время: {timestamp}<br>",
            f"📨 Message ID: {message_id}<br>",
            f"↔️ Направление: {direction}<br>",
            f"📋 Message Type: {message_type}<br>",
            f"👤 Пользователь: {obj.user_id}<br>",
        ]

        if django_user_id:
            step1_basic.append(f"👤 Django User ID: {django_user_id}<br>")

        step1_basic.extend([
            f"📡 Канал: {obj.channel}<br>",
            f"🆔 Сессия: {obj.session_id}<br>",
            f"🔗 Dialog ID: {dialog_id}<br>",
            f"📏 Длина сообщения: {len(user_message)} символов"
        ])

        # NULL поля (9 штук) - важно для отладки!
        step1_nulls = [
            f"Processing Stage: {obj.processing_stage if hasattr(obj, 'processing_stage') and obj.processing_stage else 'NULL'}<br>",
            f"Confidence Score: {obj.confidence_score if hasattr(obj, 'confidence_score') and obj.confidence_score is not None else 'NULL'}<br>",
            f"Service Detected ID: {obj.service_detected_id if hasattr(obj, 'service_detected_id') and obj.service_detected_id is not None else 'NULL'}<br>",
            f"Address Extracted: {obj.address_extracted if hasattr(obj, 'address_extracted') and obj.address_extracted else 'NULL'}<br>",
            f"Processing Time: {obj.processing_time_ms if hasattr(obj, 'processing_time_ms') and obj.processing_time_ms is not None else 'NULL'}<br>",
            f"LLM Provider: {obj.llm_provider if hasattr(obj, 'llm_provider') and obj.llm_provider else 'NULL'}<br>",
            f"LLM Model: {obj.llm_model if hasattr(obj, 'llm_model') and obj.llm_model else 'NULL'}<br>",
            f"Tokens Used: {obj.tokens_used if hasattr(obj, 'tokens_used') and obj.tokens_used is not None else 'NULL'}<br>",
            f"Cost Rub: {obj.cost_rub if hasattr(obj, 'cost_rub') and obj.cost_rub is not None else 'NULL'}",
        ]

        # ИСПРАВЛЕНО (2026-01-19): Показываем РЕАЛЬНЫЙ metadata из БД (ПРАВДА)
        # Получаем реальный metadata из объекта (ПОСЛЕ всех обновлений)
        real_metadata = metadata if metadata else {}
        metadata_keys = list(real_metadata.keys())

        # Форматируем metadata для отображения
        if len(str(real_metadata)) > 800:
            # Если слишком большой - обрезаем но показываем ключи
            metadata_preview = {k: (type(v).__name__) for k, v in real_metadata.items()}
            metadata_display = f"{json.dumps(metadata_preview, ensure_ascii=False, indent=2)}\n\n⚠️ ПОЛНЫЙ metadata обрезан (всего {len(str(real_metadata))} символов)"
        else:
            metadata_display = json.dumps(real_metadata, ensure_ascii=False, indent=2)

        # Форматируем с <br> для переносов строк в HTML
        step1_details = ''.join(step1_basic)
        step1_nulls_str = ''.join(step1_nulls)

        steps.append({
            'step': 1,
            'name': '📝 Ввод сообщения (INSERT в БД)',
            'status': 'success',
            'data': user_message[:100] + ('...' if len(user_message) > 100 else ''),
            'details': f"ℹ️ ОСНОВНЫЕ ПОЛЯ:<br>{step1_details}<br><br>ℹ️ NULL ПОЛЯ (пустые на этом шаге):<br>{step1_nulls_str}<br><br>ℹ️ РЕАЛЬНЫЙ METADATA (из БД, {len(metadata_keys)} ключей):<br><pre style='background: #f5f5f5; padding: 10px; border-radius: 5px; white-space: pre-wrap; font-size: 11px;'>{metadata_display}</pre>",
        })

        # ШАГ 1.2: Get History (строка 122 в message_handler_service.py)
        # ИСПРАВЛЕНО (2026-01-19): Показываем ПРАВДУ - история извлекается из БД
        # Проблема: dialog_history НЕ сохраняется в metadata! Только в Python памяти.
        # Админка НЕ МОЖЕТ показать реальное количество из metadata.

        # Пытаемся определить количество по сервисному результату
        dialog_history_count = 'НЕИЗВЕСТНО'
        service_result = metadata.get('service_result', {})
        if service_result:
            candidates = service_result.get('candidates', [])
            is_followup = service_result.get('is_followup', False)
            if is_followup:
                dialog_history_count = 'Была история (followup)'

        steps.append({
            'step': '1.2',
            'name': '📜 Get History',
            'status': 'warning',  # Warning т.к. не сохраняется в metadata
            'data': f'Излечено из БД (не в metadata)' if dialog_history_count == 'НЕИЗВЕСТНО' else dialog_history_count,
            'details': f'ℹ️ Код: message_handler_service.py:122<br>ℹ️ Извлекает: _get_dialog_history(session_id, limit=10)<br>ℹ️ Хранение: Python память (НЕ в БД metadata)<br>⚠️ ПЕРЕДАЕТСЯ в MainAgent через user_context<br>⚠️ НЕ сохраняется в metadata при UPDATE<br>⚠️ Админка НЕ МОЖЕТ показать реальное количество',
            'issues': ['dialog_history не сохраняется в metadata!']
        })

        # ШАГ 1.3: MessageCleaner (строка 127 в message_handler_service.py)
        # ИСПРАВЛЕНО (2026-01-19): Показываем очистку сообщения
        # Проблема: cleaned_text НЕ сохраняется в БД! Только в памяти Python.
        steps.append({
            'step': '1.3',
            'name': '🧹 MessageCleaner',
            'status': 'warning',
            'data': 'cleaned_text (НЕ сохранен)',
            'details': 'ℹ️ Удаляет: приветствия, insignificant words<br>⚠️ НЕ сохраняется в metadata<br>ℹ️ Передается в микросервисы через search_text',
            'issues': ['cleaned_text не сохраняется в metadata']
        })

        # ШАГ 1.5: AddressExtractor (строка 326 в main_agent.py)
        # ИСПРАВЛЕНО (2026-01-19): Показываем что данные НЕ сохраняются
        address_components = metadata.get('address_components', {})
        address_status = 'warning'  # Warning т.к. данные не сохраняются
        address_issues = ['address_components не сохраняется в metadata!']

        if address_components:
            address_details = f"ℹ️ Извлечено: {len(address_components)} компонентов<br>ℹ️ Данные: {address_components}<br>⚠️ НЕ сохраняется в metadata"
        else:
            address_details = "ℹ️ Извлечено: 0 компонентов<br>⚠️ Адрес не найден в тексте<br>⚠️ НЕ сохраняется в metadata"

        steps.append({
            'step': '1.5',
            'name': '🏠 AddressExtractor',
            'status': address_status,
            'data': f'{len(address_components)} компонентов' if address_components else 'Не найдено',
            'details': address_details,
            'issues': address_issues
        })

        # ШАГ 2: ProblemAccumulationService (metadata НА МОМЕНТ этого шага)
        accumulated_fields = metadata.get('accumulated_fields', {})
        txtPrb = metadata.get('txtPrb', '')

        acc_status = 'success'
        acc_issues = []
        acc_details = []

        # Заголовок
        acc_details.append("ℹ️ Использует: YandexGPT для извлечения 7 полей")
        acc_details.append("")

        if not accumulated_fields:
            acc_status = 'warning'
            acc_issues.append('accumulated_fields пустой')
            acc_details.append("⚠️ Поля не извлечены")
        else:
            # Детальный анализ всех 7 полей
            field_icons = {
                'problem': '🔴',
                'location': '📍',
                'source': '🔧',
                'category': '📁',
                'object': '🏠',
                'severity': '⚠️',
                'intensity': '💪'
            }

            present_fields = []
            missing_fields = []

            for key, icon in field_icons.items():
                value = accumulated_fields.get(key)
                if value:
                    present_fields.append(f"{icon} {key}: {value}")
                else:
                    missing_fields.append(f"⸺ {key}: (пусто)")

            if present_fields:
                acc_details.append(f"Извлечено полей: {len(present_fields)}/7")
                acc_details.extend(present_fields)

            if missing_fields:
                acc_details.append(f"")
                acc_details.append(f"Не извлечено: {len(missing_fields)}/7")
                acc_details.extend(missing_fields[:5])  # Показываем первые 5

            # Проверка критически важных полей
            if not accumulated_fields.get('problem'):
                acc_status = 'warning'
                acc_issues.append('❌ Нет поля problem (что случилось?)')
#             if not accumulated_fields.get('category'):
#                 acc_status = 'warning'
#                 acc_issues.append('❌ Нет поля category (какая система?)')
            if not accumulated_fields.get('location'):
                acc_issues.append('⚠️ Нет поля location (где именно?)')

            if acc_issues and acc_status != 'warning':
                acc_status = 'warning'

            # ИСПРАВЛЕНИЕ (2026-02-14): Если category УЖЕ установлен в established_filters - НЕ спрашивать! ПРОВЕРКА: Дублирование вызова AI
            # ИСПРАВЛЕНИЕ (2026-02-14): Если category УЖЕ установлен в established_filters - НЕ спрашивать! Если accumulated_fields заполнен → был ПЕРВЫЙ вызов extract_and_accumulate
            # ИСПРАВЛЕНИЕ (2026-02-14): Если category УЖЕ установлен в established_filters - НЕ спрашивать! Если есть AI Orchestrator → был ВТОРОЙ вызов в _build_question_prompt
            # ИСПРАВЛЕНИЕ (2026-02-14): Если category УЖЕ установлен в established_filters - НЕ спрашивать! через _extract_known_info → ДУБЛИРОВАНИЕ!
            if accumulated_fields and ai_orchestrator:
                acc_duplicate_issue = False

                # Проверяем: есть ли признаки дублирования
                # Признаки: accumulated_fields заполнен И есть AI Orchestrator
                # (значит генерировался вопрос через _build_question_prompt)

                # Детекция по количеству полей
                field_count = sum(1 for v in accumulated_fields.values() if v)

                # Если есть 3+ полей И есть AI Orchestrator → скорее всего дублирование
                if field_count >= 3:
                    acc_duplicate_issue = True
                    acc_details.append(f"")
                    acc_details.append(f"⚠️ ВОЗМОЖНОЕ ДУБЛИРОВАНИЕ ВЫЗОВА AI:")
                    acc_details.append(f"   → accumulated_fields заполнен (был 1-й вызов)")
                    acc_details.append(f"   → Есть AI Orchestrator (была генерация вопроса)")
                    acc_details.append(f"   → _build_question_prompt вызывает _extract_known_info")
                    acc_details.append(f"   → _extract_known_info ЗАНОВО вызывает ProblemAccumulationService")
                    acc_details.append(f"")
                    acc_details.append(f"   💰 СТОИМОСТЬ: Лишний вызов YandexGPT (~0.5-2 руб)")
                    acc_details.append(f"   ⏱️ ВРЕМЯ: +1-3 секунды к обработке")
                    acc_details.append(f"   ⚠️ РИСК: Может вернуть ДРУГИЕ поля (рассинхронизация)")

                    if acc_status == 'success':
                        acc_status = 'warning'

        # txtPrb
        if txtPrb:
            acc_details.append(f"")
            acc_details.append(f"📝 txtPrb: {txtPrb[:80]}...")

        steps.append({
            'step': 2,
            'name': '🔍 ProblemAccumulationService',
            'status': acc_status,
            'data': f'{len(accumulated_fields)}/7 полей' if accumulated_fields else 'Нет данных',
            'details': '<br>'.join(acc_details) if acc_details else 'Нет данных',
            'issues': acc_issues
        })

        # ШАГ 3: FilterDetectionService (детальная диагностика)
        established_filters = metadata.get('established_filters', {})
        filter_status = 'success'
        filter_issues = []
        filter_details = []

        # Информация о процессе
        filter_details.append("ℹ️ Вычисляет confidence для фильтров (0-100%)")
        filter_details.append("ℹ️ Порог: 80% - ниже не попадет в AI промт")
        filter_details.append("")

        # Извлекаем объект из сообщения для диагностики (если есть)
        extracted_obj = metadata.get('extracted_obj', metadata.get('OBJ', ''))
        if not extracted_obj:
            # Пытаемся извлечь из ai_orchestrator_response
            ai_response = metadata.get('ai_orchestrator_response', {})
            if isinstance(ai_response, dict):
                extracted_obj = ai_response.get('OBJ', '')

        if not established_filters:
            filter_status = 'warning'
            filter_issues.append('established_filters пустой')
            filter_details.append("⚠️ Фильтры не установлены")
        else:
            # Детальный анализ каждого фильтра
            filter_details.append(f"Установлено фильтров: {len(established_filters)}")

            for filter_name, filter_data in established_filters.items():
                if isinstance(filter_data, dict):
                    value = filter_data.get('value', 'N/A')
                    conf = filter_data.get('confidence', 0)
                    conf_pct = int(conf * 100) if conf <= 1 else int(conf)

                    # Проверка порога 0.8
                    if conf >= 0.8:
                        status_icon = "✅"
                        status_text = f"{conf_pct}% >= порог 80% → попадет в 'УЖЕ ИЗВЕСТНЫЕ ФАКТЫ'"
                    else:
                        status_icon = "❌"
                        status_text = f"{conf_pct}% < порог 80% → НЕ попадет в промт! 🔴"
                        if filter_name == 'category':
                            filter_status = 'error'
                            filter_issues.append(f'category.confidence = {conf:.0%} < порог 0.8')
                            filter_issues.append(f'   Проверка: {conf:.2f} >= 0.8? → НЕТ')
                            filter_issues.append(f'   Результат: AI не узнает категорию → лишний вопрос!')

                    filter_details.append(f"{status_icon} {filter_name}: {value} ({conf_pct}%)")
                    filter_details.append(f"      └─ {status_text}")

            # УНИВЕРСАЛЬНАЯ ДИАГНОСТИКА: Проверка фильтров SQL-запросами
            # ИСПРАВЛЕНО (2026-01-19): Проверяем каждый фильтр отдельно
            filter_details.append("")
            filter_details.append("🔍 ДИАГНОСТИКА: Проверка фильтров SQL-запросами")

            try:
                from django.db import connection

                # Формируем условия WHERE для каждого фильтра
                incident_type_value = None
                location_type_value = None
                category_value = None

                if 'incident_type' in established_filters:
                    it_data = established_filters['incident_type']
                    incident_type_value = it_data.get('value') if isinstance(it_data, dict) else it_data

                if 'location_type' in established_filters:
                    lt_data = established_filters['location_type']
                    location_type_value = lt_data.get('value') if isinstance(lt_data, dict) else lt_data

                if 'category' in established_filters:
                    cat_data = established_filters['category']
                    category_value = cat_data.get('value') if isinstance(cat_data, dict) else cat_data

                # Базовый SQL (все услуги)
                base_sql = """
                    SELECT COUNT(*)
                    FROM services_catalog sc
                    LEFT JOIN ref_service_types rst ON sc.type_id = rst.type_id
                    LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
                    LEFT JOIN ref_localization rl ON sc.localization_id = rl.localization_id
                    WHERE sc.is_active = TRUE
                """

                # 1. Проверяем location_type
                if location_type_value:
                    filter_details.append("")
                    filter_details.append("📊 Проверка: location_type")

                    with connection.cursor() as cursor:
                        # С фильтром location_type
                        sql_with_loc = base_sql + " AND (%s = '' OR rl.localization_name = %s)"
                        cursor.execute(sql_with_loc, [location_type_value, location_type_value])
                        count_with_loc = cursor.fetchone()[0]

                        # БЕЗ фильтра location_type (но с остальными)
                        sql_without_loc = base_sql + " AND (%s = '' OR rst.type_name = %s) AND (%s = '' OR rc.category_name = %s)"
                        cursor.execute(sql_without_loc, [
                            incident_type_value or '', incident_type_value or '',
                            category_value or '', category_value or ''
                        ])
                        count_without_loc = cursor.fetchone()[0]

                    filter_details.append(f"   • С фильтром location_type='{location_type_value}': {count_with_loc} услуг")
                    filter_details.append(f"   • БЕЗ фильтра location_type: {count_without_loc} услуг")

                    if count_with_loc == 0 and count_without_loc > 0:
                        filter_status = 'error'
                        filter_issues.append(f'⚠️ FilterDetectionService ОШИБСЯ на location_type!')
                        filter_issues.append(f'   • Определил: "{location_type_value}"')
                        filter_issues.append(f'   • Факт: услуги имеют ДРУГОЕ location_type или NULL')
                        filter_issues.append(f'   • Результат: отсеяно {count_without_loc} услуг')
                        filter_details.append(f"   ❌ ПРОБЛЕМА: location_type отсеял {count_without_loc} услуг!")
                        filter_details.append("")
                        filter_details.append(f"📁 ГДЕ ОШИБКА (ДИНАМИЧЕСКОЕ ЧТЕНИЕ КОДА):")

                        # ДИНАМИЧЕСКИ читаем код
                        code_info = get_code_info('filter_detection_service', 'FilterDetectionService', '_create_filter_detection_prompt')

                        if code_info.get('source'):
                            # АВТОМАТИЧЕСКИ находим ВСЕ шаги
                            all_steps = find_all_steps_in_code(code_info['source'])

                            if all_steps:
                                filter_details.append(f"   • Метод: FilterDetectionService._create_filter_detection_prompt()")
                                filter_details.append(f"   • Файл: filter_detection_service.py")
                                filter_details.append(f"   • Строка: {code_info['start_line']} (начало метода)")
                                filter_details.append(f"   • ВСЕГО найдено шагов: {len(all_steps)}")

                                # Показываем все шаги
                                filter_details.append(f"   • Структура промпта:")
                                for step in all_steps:
                                    filter_details.append(f"     - Шаг {step['number']}: {step['text'][:50]}...")

                                # Ищем конкретный шаг про location_type
                                location_step = find_step_by_keywords(
                                    code_info['source'],
                                    ['PLACE_SCOPE', 'location_type', 'Определи location_type', 'внутриквартирное']
                                )

                                if location_step:
                                    filter_details.append(f"   • Логика location_type: найдена строка {location_step['line']}")
                                else:
                                    filter_details.append(f"   • Логика location_type: не найдена (шаг может быть переименован)")

                                if extracted_obj:
                                    filter_details.append(f"   • Объект в запросе: \"{extracted_obj}\"")
                            else:
                                filter_details.append(f"   ⚠️ В промпте не найдено шагов (формат может измениться)")
                                filter_details.append(f"   • Метод: _create_filter_detection_prompt()")
                                filter_details.append(f"   • Строки: {code_info['start_line']}-{code_info['end_line']}")
                        else:
                            filter_details.append(f"   ❌ Не удалось прочитать код: {code_info.get('error', 'Неизвестная ошибка')}")

                # 2. Проверяем category
                if category_value:
                    filter_details.append("")
                    filter_details.append("📊 Проверка: category")

                    with connection.cursor() as cursor:
                        # С фильтром category
                        sql_with_cat = base_sql + " AND (%s = '' OR rc.category_name = %s)"
                        cursor.execute(sql_with_cat, [category_value, category_value])
                        count_with_cat = cursor.fetchone()[0]

                        # БЕЗ фильтра category
                        sql_without_cat = base_sql + " AND (%s = '' OR rst.type_name = %s) AND (%s = '' OR rl.localization_name = %s)"
                        cursor.execute(sql_without_cat, [
                            incident_type_value or '', incident_type_value or '',
                            location_type_value or '', location_type_value or ''
                        ])
                        count_without_cat = cursor.fetchone()[0]

                    filter_details.append(f"   • С фильтром category='{category_value}': {count_with_cat} услуг")
                    filter_details.append(f"   • БЕЗ фильтра category: {count_without_cat} услуг")

                    if count_with_cat == 0 and count_without_cat > 0:
                        filter_status = 'error'
                        filter_issues.append(f'⚠️ FilterDetectionService ОШИБСЯ на category!')
                        filter_issues.append(f'   • Определил: "{category_value}"')
                        filter_issues.append(f'   • Факт: услуги имеют ДРУГУЮ category или NULL')
                        filter_issues.append(f'   • Результат: отсеяно {count_without_cat} услуг')
                        filter_details.append(f"   ❌ ПРОБЛЕМА: category отсеял {count_without_cat} услуг!")
                        filter_details.append("")
                        filter_details.append(f"📁 ГДЕ ОШИБКА (ДИНАМИЧЕСКОЕ ЧТЕНИЕ КОДА):")

                        # ДИНАМИЧЕСКИ читаем код
                        code_info = get_code_info('filter_detection_service', 'FilterDetectionService', '_create_filter_detection_prompt')

                        if code_info.get('source'):
                            # АВТОМАТИЧЕСКИ находим ВСЕ шаги
                            all_steps = find_all_steps_in_code(code_info['source'])

                            if all_steps:
                                filter_details.append(f"   • Метод: FilterDetectionService._create_filter_detection_prompt()")
                                filter_details.append(f"   • ВСЕГО найдено шагов: {len(all_steps)}")

                                # Ищем конкретный шаг про category
                                category_step = find_step_by_keywords(
                                    code_info['source'],
                                    ['Определи category', 'Множество1', '3 множества вероятностей']
                                )

                                if category_step:
                                    filter_details.append(f"   • Логика category: найдена строка {category_step['line']}")
                                    filter_details.append(f"   • Что проверить: примеры '{category_value}' в промпте")
                                else:
                                    filter_details.append(f"   • Логика category: не найдена (шаг может быть переименован)")
                                    filter_details.append(f"   • Рекомендация: Добавить '{category_value}' в примеры")
                            else:
                                filter_details.append(f"   ⚠️ В промпте не найдено шагов")
                        else:
                            filter_details.append(f"   ❌ Не удалось прочитать код: {code_info.get('error', 'Неизвестная ошибка')}")

                # 3. Проверяем incident_type
                if incident_type_value:
                    filter_details.append("")
                    filter_details.append("📊 Проверка: incident_type")

                    with connection.cursor() as cursor:
                        # С фильтром incident_type
                        sql_with_inc = base_sql + " AND (%s = '' OR rst.type_name = %s)"
                        cursor.execute(sql_with_inc, [incident_type_value, incident_type_value])
                        count_with_inc = cursor.fetchone()[0]

                        # БЕЗ фильтра incident_type
                        sql_without_inc = base_sql + " AND (%s = '' OR rc.category_name = %s) AND (%s = '' OR rl.localization_name = %s)"
                        cursor.execute(sql_without_inc, [
                            category_value or '', category_value or '',
                            location_type_value or '', location_type_value or ''
                        ])
                        count_without_inc = cursor.fetchone()[0]

                    filter_details.append(f"   • С фильтром incident_type='{incident_type_value}': {count_with_inc} услуг")
                    filter_details.append(f"   • БЕЗ фильтра incident_type: {count_without_inc} услуг")

                    if count_with_inc == 0 and count_without_inc > 0:
                        filter_status = 'error'
                        filter_issues.append(f'⚠️ FilterDetectionService ОШИБСЯ на incident_type!')
                        filter_issues.append(f'   • Определил: "{incident_type_value}"')
                        filter_issues.append(f'   • Факт: услуги имеют ДРУГОЙ incident_type или NULL')
                        filter_issues.append(f'   • Результат: отсеяно {count_without_inc} услуг')
                        filter_details.append(f"   ❌ ПРОБЛЕМА: incident_type отсеял {count_without_inc} услуг!")
                        filter_details.append("")
                        filter_details.append(f"📁 ГДЕ ОШИБКА (ДИНАМИЧЕСКОЕ ЧТЕНИЕ КОДА):")

                        # ДИНАМИЧЕСКИ читаем код
                        code_info = get_code_info('filter_detection_service', 'FilterDetectionService', '_create_filter_detection_prompt')

                        if code_info.get('source'):
                            # АВТОМАТИЧЕСКИ находим ВСЕ шаги
                            all_steps = find_all_steps_in_code(code_info['source'])

                            if all_steps:
                                filter_details.append(f"   • ВСЕГО найдено шагов: {len(all_steps)}")

                                # Ищем конкретный шаг про incident_type
                                incident_step = find_step_by_keywords(
                                    code_info['source'],
                                    ['Определи incident_type', 'S3 (блокировка функций)', 'блокировка функций']
                                )

                                if incident_step:
                                    filter_details.append(f"   • Логика incident_type: найдена строка {incident_step['line']}")
                                else:
                                    filter_details.append(f"   • Логика incident_type: не найдена")
                            else:
                                filter_details.append(f"   ⚠️ В промпте не найдено шагов")
                        else:
                            filter_details.append(f"   ❌ Не удалось прочитать код: {code_info.get('error', 'Неизвестная ошибка')}")

            except Exception as e:
                filter_details.append(f"")
                filter_details.append(f"⚠️ Ошибка диагностики: {str(e)[:100]}")

        steps.append({
            'step': 3,
            'name': '🎯 FilterDetectionService',
            'status': filter_status,
            'data': f'{len(established_filters)} фильтров' if established_filters else 'Нет данных',
            'details': '<br>'.join(filter_details) if filter_details else 'Нет данных',
            'issues': filter_issues
        })

        # ШАГ 3.5: SemanticPreCheck (упущенный шаг!)
        # ИСПРАВЛЕНО (2026-01-18): Добавлен в визуализацию
        semantic_check = metadata.get('semantic_check', {})
        semantic_status = 'success'
        semantic_details = []
        semantic_issues = []

        semantic_details.append("ℹ️ Дополнительный поиск фильтров через AI")
        semantic_details.append("ℹ️ Защита: НЕ переопределяет фильтры с confidence >= 75%")
        semantic_details.append("")

        if semantic_check.get('filters'):
            semantic_details.append(f"✅ Найдено: {len(semantic_check['filters'])} фильтров")
            for filter_name, filter_data in semantic_check['filters'].items():
                value = filter_data.get('value', 'N/A')
                conf = filter_data.get('confidence', 0)
                conf_pct = int(conf * 100) if conf <= 1 else int(conf)
                semantic_details.append(f"   → {filter_name}: {value} ({conf_pct}%)")
        else:
            semantic_details.append("⚠️ Дополнительных фильтров не найдено")
            semantic_status = 'warning'

        steps.append({
            'step': '3.5',
            'name': '🔍 SemanticPreCheck',
            'status': semantic_status,
            'data': f'{len(semantic_check.get("filters", {}))} фильтров' if semantic_check.get('filters') else 'Нет',
            'details': '<br>'.join(semantic_details),
            'issues': semantic_issues
        })

        # ШАГ 4: Микросервисы (детальная диагностика)
        vector_results = microservices.get('vector_search', {}).get('candidates', [])
        tag_results = microservices.get('tag_search', {}).get('candidates', [])
        semantic_results = microservices.get('semantic_search', {}).get('candidates', [])

        micro_status = 'success'
        micro_issues = []

        # Детальный анализ каждого микросервиса
        micro_details = []

        # Данные для диагностики
        search_text = metadata.get('search_text', user_message[:100])
        established_filters = metadata.get('established_filters', {})

        # Vector Search
        micro_details.append("🔹 VectorSearchService:")

        if vector_results:
            v_conf = vector_results[0].get('confidence', 0)
            v_name = vector_results[0].get('service_name', 'N/A')[:30]
            micro_details.append(f"   ✅ Найдено: {len(vector_results)} услуг")
            micro_details.append(f"   → Топ: {v_name} (conf={v_conf:.3f})")
        else:
            micro_details.append("   ❌ Пустой результат (candidates=[])")
            micro_details.append("")
            micro_details.append("   → ПОШАГОВО ЧТО ПРОИЗОШЛО:")

            try:
                from django.db import connection
                with connection.cursor() as cursor:
                    # Извлекаем фильтры
                    inc_filter = established_filters.get('incident_type', {}) if established_filters else {}
                    inc_value = inc_filter.get('value', '') if isinstance(inc_filter, dict) else inc_filter
                    inc_conf = inc_filter.get('confidence', 0) if isinstance(inc_filter, dict) else 0

                    cat_filter = established_filters.get('category', {}) if established_filters else {}
                    cat_value = cat_filter.get('value', '') if isinstance(cat_filter, dict) else cat_filter

                    loc_filter = established_filters.get('location_type', {}) if established_filters else {}
                    loc_value = loc_filter.get('value', '') if isinstance(loc_filter, dict) else loc_filter

                    # Формируем условия WHERE для показа
                    where_conditions = []
                    if inc_value:
                        where_conditions.append(f"incident_type='{inc_value}'")
                    if cat_value:
                        where_conditions.append(f"category='{cat_value}'")
                    if loc_value:
                        where_conditions.append(f"location_type='{loc_value}'")

                    # ШАГ 1: SQL с фильтрами
                    micro_details.append("")
                    micro_details.append(f"   ШАГ 1: VectorSearchService._search_by_tags()")
                    micro_details.append(f"      SQL с фильтрами:")
                    micro_details.append(f"      WHERE {' AND '.join(where_conditions)}")

                    cursor.execute("""
                        SELECT COUNT(*)
                        FROM services_catalog sc
                        LEFT JOIN ref_service_types rst ON sc.type_id = rst.type_id
                        LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
                        LEFT JOIN ref_localization rl ON sc.localization_id = rl.localization_id
                        WHERE sc.is_active = TRUE
                          AND (%s = '' OR rst.type_name = %s)
                          AND (%s = '' OR rc.category_name = %s)
                          AND (%s = '' OR rl.localization_name = %s)
                    """, [inc_value or '', inc_value or '',
                          cat_value or '', cat_value or '',
                          loc_value or '', loc_value or ''])

                    count_with = cursor.fetchone()[0]
                    micro_details.append(f"      Результат: {count_with} строк")

                    if count_with == 0:
                        micro_details.append(f"      ❌ НЕТ данных для вычисления косинусного сходства")
                    else:
                        micro_details.append(f"      ✅ Загружено embedding, вычисляем cosine similarity")

                    # ШАГ 2: SQL БЕЗ проблемного фильтра (если есть проблема)
                    if inc_value and count_with == 0:
                        micro_details.append("")
                        micro_details.append(f"   ШАГ 2: Проверка БЕЗ фильтра incident_type")
                        micro_details.append(f"      SQL БЕЗ incident_type:")
                        where_without_inc = [c for c in where_conditions if 'incident_type' not in c]
                        micro_details.append(f"      WHERE {' AND '.join(where_without_inc) if where_without_inc else 'sc.is_active = TRUE'}")

                        cursor.execute("""
                            SELECT sc.service_id, sc.scenario_name
                            FROM services_catalog sc
                            LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
                            LEFT JOIN ref_localization rl ON sc.localization_id = rl.localization_id
                            WHERE sc.is_active = TRUE
                              AND (%s = '' OR rc.category_name = %s)
                              AND (%s = '' OR rl.localization_name = %s)
                            ORDER BY sc.scenario_name
                            LIMIT 10
                        """, [cat_value or '', cat_value or '',
                              loc_value or '', loc_value or ''])

                        found_services = cursor.fetchall()
                        micro_details.append(f"      Результат: {len(found_services)} услуг")

                        if found_services:
                            for service_id, scenario_name in found_services:
                                micro_details.append(f"      ✅ • {scenario_name} (ID={service_id})")

                        # ВЫВОД
                        micro_details.append("")
                        micro_details.append(f"   ВЫВОД: VectorSearchService НЕ нашел услуг из-за фильтров")
                        micro_details.append(f"")
                        micro_details.append(f"   → ПРИЧИНА ОШИБКИ: filter_detection_service.py:237")
                        micro_details.append(f"      Правило S3: \"не работает лифт/вентиляция\" → Инцидент")
                        micro_details.append(f"      LLM применил к \"не работает розетка\" → incident_type='Инцидент'")
                        micro_details.append(f"      НО в БД у услуги incident_type='Запрос'")
                        micro_details.append(f"      → SQL с фильтром вернул 0 строк")

            except Exception as e:
                micro_details.append(f"      ⚠️ Не удалось проверить: {str(e)[:60]}")

        micro_details.append("")


        # Tag Search
        micro_details.append("🔸 TagSearchService:")

        if tag_results:
            t_conf = tag_results[0].get('confidence', 0)
            t_name = tag_results[0].get('service_name', 'N/A')[:30]
            n_tags = len(tag_results)
            # Проверяем природу confidence
            if t_conf <= 0.6:
                micro_details.append(f"   ✅ Найдено: {n_tags} услуг (равномерное распределение 1/n)")
                micro_details.append(f"   → Топ: {t_name} (conf={t_conf:.3f} = 1.0/{n_tags})")
            else:
                micro_details.append(f"   ✅ Найдено: {n_tags} услуг")
                micro_details.append(f"   → Топ: {t_name} (conf={t_conf:.3f})")
        else:
            micro_details.append("   ❌ Пустой результат (candidates=[])")
            micro_details.append("   → ПРИЧИНА:")
            micro_details.append("      ⚠️ НЕТ тегов с word_similarity > 0.3")
            micro_details.append("      ⚠️ Либо pymorphy2/rapidfuzz не нашли совпадений")
            micro_details.append("")
            micro_details.append("   → Детальная диагностика (вычислено в админке):")

            # Диагностика TagSearchService - проверяем теги
            try:
                from django.db import connection
                with connection.cursor() as cursor:
                    # 1. Проверяем есть ли тег "розетка"
                    cursor.execute("""
                        SELECT tag_name, is_active
                        FROM ref_tags
                        WHERE tag_name ILIKE %s
                        ORDER BY tag_name
                        LIMIT 5
                    """, ['%розетк%'])

                    found_tags = cursor.fetchall()
                    if found_tags:
                        micro_details.append(f"      ✅ Тег 'розетка' найден в ref_tags: {', '.join([t[0] for t in found_tags])}")
                    else:
                        micro_details.append(f"      ❌ Тег 'розетка' НЕ найден в ref_tags")

                    # 2. Проверяем word_similarity
                    cursor.execute("""
                        SELECT rt.tag_name, word_similarity(%s, rt.tag_name) as similarity
                        FROM ref_tags rt
                        WHERE rt.is_active = TRUE
                        ORDER BY similarity DESC
                        LIMIT 5
                    """, [search_text])

                    similar_tags = cursor.fetchall()
                    if similar_tags:
                        micro_details.append(f"      → word_similarity с топ-5 тегами:")
                        for tag_name, sim in similar_tags:
                            status = "✅" if sim > 0.3 else "❌" if sim > 0.1 else "⚠️"
                            micro_details.append(f"         {status} '{tag_name}' sim={sim:.4f} {'(прошел порог 0.3)' if sim > 0.3 else '(ниже порога 0.3)'}")

                    # 3. Проверяем связанные услуги
                    cursor.execute("""
                        SELECT COUNT(DISTINCT st.service_id)
                        FROM service_tags st
                        JOIN ref_tags rt ON st.tag_id = rt.tag_id
                        WHERE rt.tag_name ILIKE %s AND rt.is_active = TRUE
                    """, ['%розетк%'])

                    linked_count = cursor.fetchone()[0]
                    if linked_count > 0:
                        micro_details.append(f"      ✅ Тег связан с {linked_count} услугами")
                    else:
                        micro_details.append(f"      ❌ Тег НЕ связан ни с одной услугой")

                    # 4. Проверяем pg_trgm
                    cursor.execute("""
                        SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'
                    """)
                    has_trgm = cursor.fetchone()
                    if has_trgm:
                        micro_details.append(f"      ✅ pg_trgm установлен")
                    else:
                        micro_details.append(f"      ❌ pg_trgm НЕ установлен!")

                    # 5. Проверяем логику _has_match (pymorphy2 + rapidfuzz)
                    micro_details.append("")
                    micro_details.append(f"      → Проверка логики _has_match (pymorphy2 + rapidfuzz):")

                    # Извлекаем слова из search_text (минимум 4 буквы)
                    import re
                    search_words = [w for w in re.findall(r'\b\w+\b', search_text.lower()) if len(w) >= 4]
                    micro_details.append(f"         • Слова из запроса (>= 4 букв): {search_words}")

                    # Проверяем прямое совпадение с тегом 'розетка'
                    if 'розетка' in search_words:
                        micro_details.append(f"         ✅ ПРЯМОЕ СОВПАДЕНИЕ: 'розетка' в запросе")
                        micro_details.append(f"         ✅ Должно пройти проверку _has_match!")
                    else:
                        micro_details.append(f"         ❌ НЕТ прямого совпадения с 'розетка'")

                    # Проверяем связанные услуги и их теги
                    cursor.execute("""
                        SELECT sc.service_id, sc.scenario_name,
                               STRING_AGG(rt.tag_name, ', ') as tags
                        FROM service_tags st
                        JOIN services_catalog sc ON st.service_id = sc.service_id
                        JOIN ref_tags rt ON st.tag_id = rt.tag_id
                        WHERE rt.tag_name ILIKE %s AND sc.is_active = TRUE
                        GROUP BY sc.service_id, sc.scenario_name
                        LIMIT 3
                    """, ['%розетк%'])

                    services_with_tag = cursor.fetchall()
                    if services_with_tag:
                        micro_details.append(f"         • Услуги с тегом 'розетка':")
                        for service_id, scenario_name, tags in services_with_tag:
                            micro_details.append(f"           - {scenario_name} (ID={service_id})")
                            micro_details.append(f"             Теги: {tags}")

                    # Проверяем фильтры (возможно услуга отсеяна фильтрами)
                    if established_filters:
                        loc_filter = established_filters.get('location_type', {})
                        if isinstance(loc_filter, dict):
                            loc_value = loc_filter.get('value', '')
                            if loc_value:
                                micro_details.append(f"")
                                micro_details.append(f"         ⚠️ ПРОВЕРКА: Отсеял ли фильтр location_type?")

                                # Извлекаем другие фильтры для SQL
                                cat_filter = established_filters.get('category', {})
                                cat_value = cat_filter.get('value', '') if isinstance(cat_filter, dict) else ''

                                inc_filter = established_filters.get('incident_type', {})
                                inc_value = inc_filter.get('value', '') if isinstance(inc_filter, dict) else ''

                                # SQL С фильтром location_type
                                cursor.execute("""
                                    SELECT COUNT(DISTINCT sc.service_id)
                                    FROM services_catalog sc
                                    JOIN service_tags st ON sc.service_id = st.service_id
                                    JOIN ref_tags rt ON st.tag_id = rt.tag_id
                                    LEFT JOIN ref_service_types rst ON sc.type_id = rst.type_id
                                    LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
                                    LEFT JOIN ref_localization rl ON sc.localization_id = rl.localization_id
                                    WHERE sc.is_active = TRUE
                                      AND rt.is_active = TRUE
                                      AND rt.tag_name ILIKE %s
                                      AND (%s = '' OR rl.localization_name = %s)
                                      AND (%s = '' OR rc.category_name = %s)
                                      AND (%s = '' OR rst.type_name = %s)
                                """, ['%розетк%', loc_value, loc_value, cat_value or '', cat_value or '',
                                      inc_value or '', inc_value or ''])

                                count_with_filter = cursor.fetchone()[0]

                                # SQL БЕЗ фильтра location_type (но с остальными)
                                cursor.execute("""
                                    SELECT COUNT(DISTINCT sc.service_id)
                                    FROM services_catalog sc
                                    JOIN service_tags st ON sc.service_id = st.service_id
                                    JOIN ref_tags rt ON st.tag_id = rt.tag_id
                                    LEFT JOIN ref_service_types rst ON sc.type_id = rst.type_id
                                    LEFT JOIN ref_categories rc ON sc.category_id = rc.category_name
                                    LEFT JOIN ref_localization rl ON sc.localization_id = rl.localization_id
                                    WHERE sc.is_active = TRUE
                                      AND rt.is_active = TRUE
                                      AND rt.tag_name ILIKE %s
                                      AND (%s = '' OR rc.category_name = %s)
                                      AND (%s = '' OR rst.type_name = %s)
                                """, ['%розетк%', cat_value or '', cat_value or '',
                                      inc_value or '', inc_value or ''])

                                count_without_filter = cursor.fetchone()[0]

                                micro_details.append(f"         • С location_type='{loc_value}': {count_with_filter} услуг")
                                micro_details.append(f"         • БЕЗ location_type: {count_without_filter} услуг")

                                if count_with_filter == 0 and count_without_filter > 0:
                                    micro_details.append(f"")
                                    micro_details.append(f"         ❌ ДОКАЗАНО: location_type='{loc_value}' отсеял {count_without_filter} услуг!")
                                    micro_details.append(f"         ❌ TagSearchService._load_services вернул пустой cache")
                                    micro_details.append(f"         ❌ ШАГ 2 (pymorphy2/rapidfuzz) НЕ выполнялся - нечего проверять")
                                elif count_with_filter > 0:
                                    micro_details.append(f"")
                                    micro_details.append(f"         ✅ С фильтром найдено {count_with_filter} услуг")
                                    micro_details.append(f"         ⚠️ Значит проблема НЕ в фильтрах!")
                                    micro_details.append(f"         ⚠️ Возможно, проблема в pymorphy2/rapidfuzz")

            except Exception as e:
                micro_details.append(f"      ⚠️ Не удалось проверить теги: {str(e)[:40]}")

        micro_details.append("")


        # Semantic Search
        micro_details.append("🔺 SemanticSearchService:")

        if semantic_results:
            s_conf = semantic_results[0].get('confidence', 0)
            s_name = semantic_results[0].get('service_name', 'N/A')[:30]
            s_matched = semantic_results[0].get('matched_terms', 0)
            micro_details.append(f"   ✅ Найдено: {len(semantic_results)} услуг")
            micro_details.append(f"   → Топ: {s_name} (conf={s_conf:.3f})")
            micro_details.append(f"   → Совпало терминов: {s_matched}")
        else:
            micro_details.append("   ❌ Пустой результат (candidates=[])")
            micro_details.append("   → ПРИЧИНА:")
            micro_details.append("      ⚠️ НЕТ услуг с proportion совпавших терминов ≥ 0.5")
            micro_details.append("      ⚠️ Максимум совпавших слов дает confidence < 0.5")
            micro_details.append("")
            micro_details.append("   → Детальная диагностика (вычислено в админке):")

            # Диагностика SemanticSearchService - проверяем совпадение терминов
            try:
                from django.db import connection
                import re

                # Извлекаем слова из search_text (минимум 4 буквы)
                search_words = set(re.findall(r'\b[А-Яа-яA-Za-z]{4,}\b', search_text.lower()))

                with connection.cursor() as cursor:
                    # Проверяем совпадение слов с scenario_name + category + object_name
                    cursor.execute("""
                        SELECT s.service_id, s.scenario_name,
                               COALESCE(c.category_name, '') as category,
                               COALESCE(o.object_name, '') as object_name
                        FROM services_catalog s
                        LEFT JOIN ref_categories c ON s.category_id = c.category_id
                        LEFT JOIN ref_objects o ON s.object_id = o.object_id
                        WHERE s.is_active = true
                        ORDER BY s.scenario_name
                        LIMIT 50
                    """)

                    services = cursor.fetchall()
                    matches = []

                    for service_id, scenario_name, category, object_name in services:
                        # Ищем в scenario_name + category + object_name (как в коде)
                        combined_text = f"{scenario_name} {category} {object_name}".lower()

                        # Находим совпавшие слова
                        matched_words = search_words.intersection(
                            set(re.findall(r'\b[А-Яа-яA-Za-z]{4,}\b', combined_text))
                        )

                        if matched_words:
                            # Вычисляем пропорцию (как в SemanticSearchService)
                            total_terms = len(search_words)
                            matched_count = len(matched_words)
                            confidence = matched_count / total_terms if total_terms > 0 else 0

                            if confidence >= 0.3:  # Показываем если хотя бы 30%
                                matches.append((scenario_name, confidence, matched_words, matched_count))

                    # Сортируем по confidence DESC
                    matches.sort(key=lambda x: x[1], reverse=True)

                    if matches:
                        micro_details.append(f"      → Топ-3 совпадений по терминам:")
                        for i, (name, conf, words, count) in enumerate(matches[:3], 1):
                            status = "✅" if conf >= 0.5 else "⚠️"
                            words_str = ', '.join(list(words)[:3])
                            micro_details.append(f"         {status} {name[:35]}")
                            micro_details.append(f"            conf={conf:.2f} ({count} слов: {words_str})")
                            micro_details.append(f"            {'(прошел бы порог)' if conf >= 0.5 else '(ниже порога 0.5)'}")
                    else:
                        micro_details.append(f"      ❌ НЕТ совпадения терминов")
                        micro_details.append(f"         Из запроса извлечены слова: {', '.join(list(search_words)[:5])}")
                        micro_details.append(f"         Ни одна услуга не содержит эти слова")

            except Exception as e:
                micro_details.append(f"      ⚠️ Не удалось проверить термины: {str(e)[:40]}")

        # ДИНАМИЧЕСКАЯ ПРОВЕРКА: AVG vs MAX
        if vector_results:
            v_conf = vector_results[0].get('confidence', 0)
            if v_conf > 0.9:
                # Проверяем дедупликацию
                candidates = service_result.get('candidates', [])
                if candidates:
                    final_conf = candidates[0].get('confidence', 0)
                    if final_conf < v_conf:
                        # ДИНАМИЧЕСКИ читаем код и детектируем BUG
                        dedup_code_info = get_code_info('main_agent', 'MainAgent', '_deduplicate_and_prioritize_candidates')

                        if dedup_code_info.get('source'):
                            bug_detection = detect_aggregation_bug(dedup_code_info['source'])

                            if bug_detection and bug_detection.get('detected'):
                                # Показываем ФАКТЫ: какой метод агрегации используется
                                aggregation_type = bug_detection.get('aggregation', 'UNKNOWN')
                                aggregation_line = bug_detection.get('line', 'UNKNOWN')

                                micro_details.append(f"")
                                micro_details.append(f"📊 Агрегация confidence:")
                                micro_details.append(f"   • Метод: {aggregation_type}")
                                micro_details.append(f"   • Строка: {aggregation_line}")
                                micro_details.append(f"   • Файл: main_agent.py")

                                if aggregation_type == 'AVG':
                                    micro_details.append(f"")
                                    micro_details.append(f"📐 Формула: avg_confidence = sum(confidences) / len(confidences)")
                                    micro_details.append(f"   • Усредняет confidence от всех микросервисов")
                                    micro_details.append(f"   • Понижает общий confidence при нескольких источниках")
                                elif aggregation_type == 'MAX':
                                    micro_details.append(f"")
                                    micro_details.append(f"📐 Формула: max_confidence = max(confidences)")
                                    micro_details.append(f"   • Берет максимум confidence от всех микросервисов")
                                    micro_details.append(f"   • Сохраняет лучший результат")
                            else:
                                micro_status = 'warning'
                                micro_details.append(f"")
                                micro_details.append(f"⚠️ Не удалось детектировать метод агрегации автоматически")
                        else:
                            micro_status = 'warning'
                            micro_details.append(f"")
                            micro_details.append(f"⚠️ Не удалось прочитать код дедупликации")

        # ПРОВЕРКА: Если все микросервисы вернули пусто
        if not vector_results and not tag_results and not semantic_results:
            micro_status = 'warning'
            micro_issues.append('❌ НИ ОДИН микросервис не нашел услуги!')
            micro_issues.append(f'   • search_text: "{search_text}"')
            if established_filters:
                filters_str = ', '.join([f"{k}={v.get('value') if isinstance(v, dict) else v}" for k, v in list(established_filters.items())[:3]])
                micro_issues.append(f'   • filters: {filters_str}')
            micro_issues.append('')

        micro_data = []
        if vector_results:
            micro_data.append(f"Vector: {len(vector_results)} (conf={vector_results[0].get('confidence', 0):.3f})")
        if tag_results:
            micro_data.append(f"Tag: {len(tag_results)}")
        if semantic_results:
            micro_data.append(f"Semantic: {len(semantic_results)}")

        steps.append({
            'step': 4,
            'name': '🔬 Микросервисы (поиск)',
            'status': micro_status,
            'data': ' | '.join(micro_data) if micro_data else 'Нет результатов',
            'details': '<br>'.join(micro_details) if micro_details else f'Всего: {len(vector_results) + len(tag_results) + len(semantic_results)}',
            'issues': micro_issues
        })

        # ШАГ 5: Дедупликация (детальная диагностика)
        unique_candidates = service_result.get('candidates', [])
        dedup_status = 'success'
        dedup_issues = []
        dedup_details = []

        # Информация о процессе
        dedup_details.append("🔧 ПРОЦЕСС:")
        dedup_details.append("   → Вызывается: MainAgent._merge_and_deduplicate_candidates()")
        dedup_details.append("   → Объединяет: результаты от 3 микросервисов")
        dedup_details.append("   → Агрегация: AVG (среднее арифметическое) confidence [BUG!]")
        dedup_details.append("   → Должно быть: MAX (максимум) вместо AVG")
        dedup_details.append("   → Фильтр: порог 0.9 (90%) - выше создает заявку")
        dedup_details.append("   → Удаление: дубликаты по service_id")
        dedup_details.append("")

        if unique_candidates:
            candidate = unique_candidates[0]
            conf = candidate.get('confidence', 0)
            sources = candidate.get('sources', [])
            priority = candidate.get('priority', 0)

            dedup_details.append(f"Услуг: {len(unique_candidates)}, Confidence: {conf:.3f}")
            dedup_details.append(f"Источники: {', '.join(sources)}")
            dedup_details.append(f"Priority: {priority:.3f}")

            # Проверка порога
            if len(unique_candidates) == 1:
                if conf >= 0.9:
                    dedup_details.append("✅ Confidence >= 0.9 → SUCCESS (создать заявку)")
                else:
                    dedup_status = 'error'
                    dedup_issues.append(f'❌ 1 кандидат с confidence={conf:.3f} < порог 0.9')
                    dedup_issues.append(f'   Проверка: {conf:.3f} >= 0.9? → НЕТ')
                    dedup_issues.append(f'   Результат: AMBIGUOUS (лишний вопрос!) 🔴')
        else:
            dedup_details.append("Кандидатов нет после дедупликации")

        steps.append({
            'step': 5,
            'name': '🔄 Дедупликация и фильтрация',
            'status': dedup_status,
            'data': f'{len(unique_candidates)} уникальных услуг',
            'details': '<br>'.join(dedup_details) if dedup_details else 'Нет кандидатов',
            'issues': dedup_issues
        })

        # ШАГ 6: AI Orchestrator (детальная диагностика)
        # ai_orchestrator уже извлечен в начале метода (строка 406)
        final_status = service_result.get('status', 'UNKNOWN')

        ai_status = 'success' if final_status == 'SUCCESS' else 'warning'
        ai_issues = []
        ai_details = []

        # Информация о процессе
        ai_details.append("🔧 ПРОЦЕСС:")
        ai_details.append("   → Вызывается: MainAgent._orchestrate_microservices()")
        ai_details.append("   → Анализирует: search_results + dialog_history")
        ai_details.append("   → Использует: YandexGPT (LLM) для объединения результатов")
        ai_details.append("   → Промпт: _build_dynamic_prompt()")
        ai_details.append("   → Решение: SUCCESS (1 кандидат) или AMBIGUOUS (уточнение)")
        ai_details.append("")

        # Детальная информация
        ai_message = service_result.get('message', '')[:100]
        service_id = service_result.get('service_id')
        service_name = service_result.get('service_name', '')

        ai_details.append(f"📊 РЕЗУЛЬТАТ:")
        ai_details.append(f"   → Статус: {final_status}")
        if service_id:
            ai_details.append(f"   → Услуга ID: {service_id}")
            ai_details.append(f"   → Название: {service_name[:40] if service_name else ''}{'...' if len(service_name) > 40 else ''}")
        ai_details.append(f"   → Сообщение: {ai_message}{'...' if len(service_result.get('message', '')) > 100 else ''}")

        # ФАКТЫ: accumulated_fields и txtPrb
        ai_details.append("")
        if accumulated_fields:
            ai_details.append("📋 accumulated_fields (из metadata):")
            for key in ['problem', 'location', 'source', 'category', 'object', 'severity', 'intensity']:
                if accumulated_fields.get(key):
                    ai_details.append(f"   • {key}: {accumulated_fields[key]}")
        else:
            ai_details.append("📋 accumulated_fields: ПУСТОЙ")

        # txtPrb
        ai_details.append("")
        ai_details.append(f"📝 txtPrb: {txtPrb if txtPrb else '(пусто)'}")

        # Цепочка передачи данных
        ai_details.append("")
        ai_details.append("🔧 ЦЕПОЧКА ПЕРЕДАЧИ ДАННЫХ:")
        ai_details.append("   accumulated_fields (структура)")
        ai_details.append("      ↓ ProblemAccumulationService")
        ai_details.append("   txtPrb (текст)")
        ai_details.append("      ↓ _build_dynamic_prompt(txtPrb=txtPrb)")
        ai_details.append("   AI промпт")
        ai_details.append("      ↓ YandexGPT")
        ai_details.append("   Ответ AI")

        steps.append({
            'step': 6,
            'name': '🤖 AI Orchestrator (решение)',
            'status': ai_status,
            'data': f'Статус: {final_status}',
            'details': '<br>'.join(ai_details) if ai_details else ai_message,
            'issues': ai_issues
        })

        # ШАГ 7: UPDATE metadata (строка 226 в message_handler_service.py)
        # ИСПРАВЛЕНО (2026-01-19): Показываем когда результаты обработки попадают в БД
        update_details = []
        update_details.append("ℹ️ Обновляет metadata в БД результатами обработки")
        update_details.append("ℹ️ Добавляет: txtPrb, accumulated_fields, established_filters, semantic_check, address_components, microservices_results, ai_orchestrator")
        update_details.append("")
        update_details.append("✅ РЕЗУЛЬТАТ: Всю обработку сохраняет в БД!")
        update_details.append("")
        update_details.append("ℹ️ SQL: UPDATE dialog_logs SET metadata = '{...}' WHERE id = message_id")

        # Проверяем что metadata действительно был обновлен
        final_metadata = obj.metadata if hasattr(obj, 'metadata') else {}
        has_full_metadata = bool(final_metadata.get('ai_orchestrator'))

        steps.append({
            'step': 7,
            'name': '💾 UPDATE metadata (результаты в БД)',
            'status': 'success' if has_full_metadata else 'warning',
            'data': f'{"metadata обновлен"}' if has_full_metadata else 'metadata пустой',
            'details': '<br>'.join(update_details),
        })

        # ШАГ 8: INSERT outbound (строки 263-271 в message_handler_service.py)
        # ИСПРАВЛЕНО (2026-01-19): Показываем логирование ответа бота
        outbound_details = []
        outbound_details.append("ℹ️ Логирует ответ бота в dialog_logs")
        outbound_details.append("ℹ️ Направление: outbound (от бота к пользователю)")
        outbound_details.append("")
        outbound_details.append("✅ РЕЗУЛЬТАТ: Ответ бота записан как НОВАЯ запись")
        outbound_details.append("")

        # Проверяем есть ли outbound сообщения
        if hasattr(obj, 'session_id'):
            # Это inbound сообщение, outbound будет другим объектом
            outbound_details.append("ℹ️ OUTBOUND сообщение - это ОТДЕЛЬНАЯ запись в БД")
            outbound_details.append("ℹ️ Будет видна в списке сообщений этой сессии")

        steps.append({
            'step': 8,
            'name': '📤 INSERT outbound (ответ бота)',
            'status': 'success',
            'data': f'Новая запись в dialog_logs',
            'details': '<br>'.join(outbound_details),
        })

        # Генерируем HTML
        html_parts = []

        # Заголовок
        html_parts.append('''
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                <h2 style="margin: 0; font-size: 24px;">🏗️ АРХИТЕКТУРА ОБРАБОТКИ СООБЩЕНИЯ</h2>
                <div style="margin-top: 10px; font-size: 14px; opacity: 0.9;">Пошаговая визуализация процесса с выявлением проблем</div>
            </div>
        ''')

        # Визуализация шагов
        for step in steps:
            # Цвет статуса
            status_colors = {
                'success': '#28a745',
                'warning': '#ffc107',
                'error': '#dc3545'
            }
            status_color = status_colors.get(step['status'], '#6c757d')

            # Иконка статуса
            status_icons = {
                'success': '✅',
                'warning': '⚠️',
                'error': '🔴'
            }
            status_icon = status_icons.get(step['status'], '•')

            # HTML шага
            html_parts.append(f'''
                <div style="margin-bottom: 20px; border-left: 4px solid {status_color}; padding-left: 15px;">
                    <div style="display: flex; align-items: center; margin-bottom: 8px;">
                        <span style="background: {status_color}; color: white; padding: 5px 12px; border-radius: 20px; font-weight: bold; margin-right: 10px;">
                            ШАГ {step['step']}
                        </span>
                        <span style="font-size: 18px; font-weight: bold;">{step['name']}</span>
                        <span style="margin-left: auto; font-size: 24px;">{status_icon}</span>
                    </div>

                    <div style="background: #f8f9fa; padding: 12px; border-radius: 5px; margin-bottom: 8px;">
                        <div style="font-weight: bold; margin-bottom: 5px; color: #495057;">Данные:</div>
                        <div style="font-size: 14px; color: #212529;">{step['data']}</div>
                    </div>

                    {f'<div style="font-size: 13px; color: #6c757d; margin-bottom: 8px;">ℹ️ {step["details"]}</div>' if step.get('details') else ''}

                    {f'<div style="background: #ffe6e6; padding: 10px; border-radius: 5px; border-left: 3px solid #dc3545;">{"<br>".join(f"• {issue}" for issue in step["issues"])}</div>' if step.get('issues') else ''}
                </div>
            ''')

        # Итоговая статистика
        total_issues = sum(len(s.get('issues', [])) for s in steps)
        if total_issues > 0:
            html_parts.append(f'''
                <div style="background: #fff3cd; padding: 15px; border-radius: 5px; border-left: 5px solid #ffc107; margin-top: 20px;">
                    <div style="font-weight: bold; color: #856404; margin-bottom: 10px;">⚠️ НАЙДЕНО ОСОБЕННОСТЕЙ: {total_issues}</div>
                    <div style="font-size: 14px; color: #856404;">
                        Показаны шаги с особенностями (данные не сохраняются в metadata)
                    </div>
                </div>
            ''')
        else:
            html_parts.append(f'''
                <div style="background: #d4edda; padding: 15px; border-radius: 5px; border-left: 5px solid #28a745; margin-top: 20px;">
                    <div style="font-weight: bold; color: #155724; font-size: 16px;">✅ Обработка завершена</div>
                </div>
            ''')

        return mark_safe(''.join(html_parts))
    logic_visualization_display.short_description = '🏗️ Архитектура (логика)'

    # Ольга (2026-01-17): Добавлена диагностика багов для отладки конфликтов в логике бота
    # Показывает противоречия между AI Orchestrator и финальным статусом
    def bug_diagnostics_display(self, obj):
        """
        Диагностика багов - показывает конфликты в логике принятия решений

        Ольга (2026-01-17): Добавлено для выявления багов где AI Orchestrator
        возвращает AMBIGUOUS, но финальный статус становится SUCCESS из-за LLM ранжирования.
        """
        metadata = self._get_metadata(obj)
        service_result = metadata.get('service_result', {})

        bugs = []

        # Проверяем конфликт: AI Orchestrator vs Final Status
        ai_orchestrator = service_result.get('_metadata', {}).get('ai_orchestrator', {})
        ai_orch_status = ai_orchestrator.get('status')
        final_status = service_result.get('status')

        if ai_orch_status == 'AMBIGUOUS' and final_status == 'SUCCESS':
            bugs.append(f"⚠️ <strong>Конфликт: бот отправил не тот вопрос</strong>")

            # Показываем потерянный правильный вопрос
            ai_message = ai_orchestrator.get('message', '')
            if ai_message:
                bugs.append(f"📝 <strong>Правильный вопрос:</strong> \"{escape(ai_message[:150])}\"")

            # Показываем неправильный вопрос который был отправлен
            final_message = service_result.get('message', '')
            if final_message and final_message != ai_message:
                bugs.append(f"❌ <strong>Отправлен вопрос:</strong> \"{escape(final_message[:150])}\"")

            # Пытаемся определить причину
            confidence = service_result.get('confidence', 0)
            if confidence >= 0.7:
                bugs.append(f"🔍 <strong>Причина:</strong> LLM ранжирование (confidence={confidence}) переопределило решение")

        # Ольга (2026-01-17): Проверка лишних вопросов - accumulated_fields заполнен, но AI Orchestrator задает вопрос
        accumulated_fields = metadata.get('accumulated_fields', {})
        ai_orch_message = ai_orchestrator.get('message', '')

        # Проверяем: accumulated_fields содержит данные, но AI Orchestrator все равно задает вопрос
        # Это значит AI Orchestrator НЕ использует accumulated_fields (Bug #3)
        if accumulated_fields and ai_orch_message:
            # accumulated_fields считается заполненным если есть хоть одно поле с данными
            has_data = any(accumulated_fields.get(field) for field in ['object', 'location', 'source', 'category', 'problem', 'severity', 'intensity'])

            if has_data:
                # Показываем какие поля заполнены
                filled_fields = [f"{k}={v}" for k, v in accumulated_fields.items() if v and k in ['object', 'location', 'source', 'category', 'problem', 'severity', 'intensity']]
                bugs.append(
                    f"⚠️ <strong>Лишний вопрос:</strong> accumulated_fields содержит данные "
                    f"({', '.join(filled_fields) if filled_fields else 'заполнены'}), но AI Orchestrator не использует их"
                )
                bugs.append(f"📝 <strong>Вопрос AI Orchestrator:</strong> \"{escape(ai_orch_message[:100])}\"")

        # Если багов нет - показываем что все ок
        if not bugs:
            return mark_safe('<span style="color: #28a745; font-weight: bold;">✅ Багов не обнаружено</span>')

        # Показываем баги красным блоком
        bugs_html = '<br>'.join(bugs)
        return mark_safe(f'''
            <div style="background: #ffe6e6; padding: 15px; border-radius: 5px; border-left: 5px solid #dc3545;">
                <div style="font-weight: bold; color: #dc3545; margin-bottom: 10px;">⚠️ ДИАГНОСТИКА БАГОВ</div>
                {bugs_html}
            </div>
        ''')
    bug_diagnostics_display.short_description = 'Диагностика багов'

    def has_add_permission(self, request):
        """Запрет добавления через админку"""
        return False

    def has_change_permission(self, request, obj=None):
        """Запрет изменения через админку"""
        return False


@admin.register(APIErrorLog)
class APIErrorLogAdmin(admin.ModelAdmin):
    """
    Админ-интерфейс для логирования ошибок API

    ИСПОЛЬЗОВАНИЕ (2026-03-05):
    - Просмотр и фильтрация ошибок по дате, IP, UUID
    - Поиск по session_id, request_id, nomer, client_ip
    - Анализ проблем с интеграциями
    """

    # Отображение в списке
    list_display = [
        'timestamp',
        'error_type',
        'status_code',
        'client_ip',
        'client_system',
        'session_id_preview',
        'error_message_preview',
        'nomer'
    ]

    # Фильтры
    list_filter = [
        'error_type',
        'status_code',
        'client_system',
        'timestamp',
    ]

    # Поля поиска
    search_fields = [
        'session_id',
        'request_id',
        'error_message',
        'user_id',
        'nomer',
        'client_ip',
    ]

    # Иерархия по дате
    date_hierarchy = 'timestamp'

    # Сортировка
    ordering = ['-timestamp']

    # Поля только для чтения (логи нельзя редактировать)
    readonly_fields = [
        'error_type',
        'status_code',
        'error_message',
        'error_details',
        'session_id',
        'request_id',
        'client_ip',
        'client_system',
        'token_preview',
        'request_data',
        'message_preview',
        'user_id',
        'nomer',
        'timestamp',
    ]

    # Кнопка действий отключена (нельзя редактировать логи)
    actions = None

    # Пагинация
    list_per_page = 50

    # Запрет на добавление/редактирование/удаление
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def session_id_preview(self, obj):
        """Предпросмотр session_id"""
        if obj.session_id:
            return obj.session_id[:30] + '...' if len(obj.session_id) > 30 else obj.session_id
        return '-'
    session_id_preview.short_description = 'Session ID'

    def error_message_preview(self, obj):
        """Предпросмотр сообщения об ошибке"""
        if obj.error_message:
            return obj.error_message[:50] + '...' if len(obj.error_message) > 50 else obj.error_message
        return '-'
    error_message_preview.short_description = 'Ошибка'

    fieldsets = (
        ('Основная информация', {
            'fields': ('timestamp', 'error_type', 'status_code', 'error_message')
        }),
        ('Детали ошибки', {
            'fields': ('error_details', 'request_id')
        }),
        ('Идентификаторы', {
            'fields': ('session_id', 'user_id', 'nomer')
        }),
        ('Информация о клиенте', {
            'fields': ('client_ip', 'client_system', 'token_preview')
        }),
        ('Данные запроса', {
            'fields': ('request_data', 'message_preview'),
            'classes': ('collapse',)
        }),
    )
