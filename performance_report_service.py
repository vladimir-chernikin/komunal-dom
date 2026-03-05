#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Performance Report Service - генератор отчетов производительности

СОЗДАНО: 2026-03-04
ЦЕЛЬ: Генерация HTML отчетов с картой отработки запроса

ИСПОЛЬЗОВАНИЕ:
    from performance_report_service import PerformanceReportService

    report = PerformanceReportService.generate_html_report(session_id)
"""

import os
import logging
from typing import Dict, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class PerformanceReportService:
    """
    Сервис генерации отчетов производительности
    """

    # HTML шаблон отчета
    HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Карта отработки запроса: {session_id}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            font-size: 14px;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }}

        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
        }}

        .header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
        }}

        .header .meta {{
            font-size: 14px;
            opacity: 0.9;
        }}

        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f8f9fa;
            border-bottom: 1px solid #e0e0e0;
        }}

        .summary-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }}

        .summary-card .label {{
            font-size: 12px;
            color: #666;
            margin-bottom: 5px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .summary-card .value {{
            font-size: 32px;
            font-weight: bold;
            color: #667eea;
        }}

        .summary-card .unit {{
            font-size: 14px;
            color: #999;
            margin-left: 5px;
        }}

        .section {{
            padding: 30px;
            border-bottom: 1px solid #e0e0e0;
        }}

        .section:last-child {{
            border-bottom: none;
        }}

        .section h2 {{
            font-size: 20px;
            margin-bottom: 20px;
            color: #333;
            display: flex;
            align-items: center;
        }}

        .section h2::before {{
            content: '';
            width: 4px;
            height: 24px;
            background: #667eea;
            margin-right: 12px;
            border-radius: 2px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}

        th {{
            background: #f8f9fa;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            color: #555;
            border-bottom: 2px solid #e0e0e0;
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        td {{
            padding: 12px;
            border-bottom: 1px solid #f0f0f0;
        }}

        tr:hover {{
            background: #f8f9fa;
        }}

        .duration-cell {{
            text-align: right;
            font-family: 'Consolas', 'Monaco', monospace;
            font-weight: 600;
        }}

        .fast {{ color: #28a745; }}
        .medium {{ color: #ffc107; }}
        .slow {{ color: #dc3545; }}

        .timeline {{
            position: relative;
            margin: 20px 0;
        }}

        .timeline-item {{
            display: flex;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #f0f0f0;
        }}

        .timeline-item:last-child {{
            border-bottom: none;
        }}

        .timeline-time {{
            width: 100px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 13px;
            color: #666;
            flex-shrink: 0;
        }}

        .timeline-bar {{
            flex-grow: 1;
            margin: 0 20px;
            height: 30px;
            background: #f0f0f0;
            border-radius: 4px;
            position: relative;
            overflow: hidden;
        }}

        .timeline-bar-fill {{
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            border-radius: 4px;
            transition: width 0.3s ease;
        }}

        .timeline-label {{
            width: 200px;
            font-size: 13px;
            color: #333;
            flex-shrink: 0;
        }}

        .badge {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .badge-llm {{
            background: #e3f2fd;
            color: #1976d2;
        }}

        .badge-microservice {{
            background: #f3e5f5;
            color: #7b1fa2;
        }}

        .badge-error {{
            background: #ffebee;
            color: #c62828;
        }}

        .llm-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }}

        .llm-card {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #1976d2;
        }}

        .llm-card .service {{
            font-weight: 600;
            color: #333;
            margin-bottom: 8px;
        }}

        .llm-card .details {{
            font-size: 12px;
            color: #666;
        }}

        .llm-card .cost {{
            margin-top: 10px;
            font-size: 16px;
            font-weight: bold;
            color: #1976d2;
        }}

        .waterfall {{
            position: relative;
            height: 400px;
            background: white;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            overflow: hidden;
        }}

        .waterfall-stage {{
            position: absolute;
            height: 30px;
            background: linear-gradient(90deg, rgba(102, 126, 234, 0.8) 0%, rgba(118, 75, 162, 0.8) 100%);
            border-radius: 4px;
            display: flex;
            align-items: center;
            padding: 0 10px;
            color: white;
            font-size: 11px;
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .waterfall-stage:hover {{
            opacity: 0.8;
            cursor: pointer;
        }}

        .waterfall-label {{
            position: absolute;
            left: 10px;
            font-size: 12px;
            color: #666;
            width: 150px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        /* ИСПРАВЛЕНО (2026-03-05): Дерево выполнения */
        .tree-container {{
            margin: 20px 0;
            background: white;
            border-radius: 8px;
            border: 1px solid #e0e0e0;
            padding: 20px;
        }}

        .tree-node {{
            position: relative;
            padding: 10px 0 10px 20px;
            border-left: 2px solid #e0e0e0;
        }}

        .tree-node::before {{
            content: '';
            position: absolute;
            left: -2px;
            top: 20px;
            width: 20px;
            height: 2px;
            background: #e0e0e0;
        }}

        .tree-root {{
            border-left: none;
            padding-left: 0;
        }}

        .tree-root::before {{
            display: none;
        }}

        .tree-content {{
            background: #f8f9fa;
            padding: 12px 16px;
            border-radius: 6px;
            border: 1px solid #dee2e6;
            transition: all 0.2s;
        }}

        .tree-content:hover {{
            background: #e3f2fd;
            border-color: #2196f3;
        }}

        .tree-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }}

        .tree-title {{
            font-weight: 600;
            color: #333;
            font-size: 14px;
        }}

        .tree-duration {{
            font-family: 'Consolas', 'Monaco', monospace;
            font-weight: bold;
            font-size: 16px;
        }}

        .tree-duration.fast {{ color: #10b981; }}
        .tree-duration.medium {{ color: #f59e0b; }}
        .tree-duration.slow {{ color: #ef4444; }}

        .tree-details {{
            font-size: 12px;
            color: #666;
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px solid #dee2e6;
        }}

        .tree-badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 600;
            margin-left: 8px;
        }}

        .tree-badge-stage {{ background: #e3f2fd; color: #1976d2; }}
        .tree-badge-llm {{ background: #fff3e0; color: #f57c00; }}
        .tree-badge-microservice {{ background: #f3e5f5; color: #7b1fa2; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Карта отработки запроса</h1>
            <div class="meta">
                Session ID: {session_id}<br>
                Дата: {generated_date}
            </div>
        </div>

        <div class="summary">
            <div class="summary-card">
                <div class="label">Общее время</div>
                <div class="value">{total_duration_ms:.0f}<span class="unit">мс</span></div>
            </div>
            <div class="summary-card">
                <div class="label">Микросервисы</div>
                <div class="value">{microservices_total_ms:.0f}<span class="unit">мс</span></div>
            </div>
            <div class="summary-card">
                <div class="label">LLM стоимость</div>
                <div class="value">{llm_total_cost_rub:.4f}<span class="unit">руб</span></div>
            </div>
            <div class="summary-card">
                <div class="label">LLM токены</div>
                <div class="value">{llm_total_tokens}<span class="unit">шт</span></div>
            </div>
        </div>

        {stages_html}

        {tree_html}

        {microservices_html}

        {llm_calls_html}

        {waterfall_html}
    </div>

    <script>
        // Интерактивность waterfall диаграммы
        document.querySelectorAll('.waterfall-stage').forEach(stage => {{
            stage.addEventListener('click', function() {{
                const details = this.getAttribute('data-details');
                if (details) {{
                    alert(details);
                }}
            }});
        }});
    </script>
</body>
</html>
    """

    @staticmethod
    def _generate_stages_html(stages: List[Dict]) -> str:
        """Генерирует HTML для таблицы этапов"""
        if not stages:
            return ""

        rows = ""
        for stage in stages:
            duration = stage.get('duration_ms', 0)
            if duration is None:
                duration_str = "N/A"
                duration_class = ""
            else:
                duration_str = f"{duration:.2f}"
                if duration < 100:
                    duration_class = "fast"
                elif duration < 1000:
                    duration_class = "medium"
                else:
                    duration_class = "slow"

            rows += f"""
            <tr>
                <td>{stage.get('name', 'N/A')}</td>
                <td class="duration-cell {duration_class}">{duration_str}</td>
                <td>{stage.get('result', '')}</td>
                <td>{stage.get('error', '')}</td>
            </tr>
            """

        return f"""
        <div class="section">
            <h2>Этапы выполнения</h2>
            <table>
                <thead>
                    <tr>
                        <th>Этап</th>
                        <th>Время (мс)</th>
                        <th>Результат</th>
                        <th>Ошибка</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
        """

    @staticmethod
    def _generate_microservices_html(microservices: List[Dict]) -> str:
        """Генерирует HTML для микросервисов"""
        if not microservices:
            return ""

        rows = ""
        for ms in microservices:
            duration = ms.get('duration_ms', 0)
            candidates = ms.get('candidates_count', 0)
            name = ms.get('name', 'N/A')

            if duration < 100:
                duration_class = "fast"
            elif duration < 1000:
                duration_class = "medium"
            else:
                duration_class = "slow"

            rows += f"""
            <tr>
                <td><span class="badge badge-microservice">{name}</span></td>
                <td class="duration-cell {duration_class}">{duration:.2f}</td>
                <td>{candidates} кандидатов</td>
            </tr>
            """

        return f"""
        <div class="section">
            <h2>Микросервисы</h2>
            <table>
                <thead>
                    <tr>
                        <th>Сервис</th>
                        <th>Время (мс)</th>
                        <th>Кандидатов</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
        """

    @staticmethod
    def _generate_llm_calls_html(llm_calls: List[Dict]) -> str:
        """Генерирует HTML для LLM вызовов"""
        if not llm_calls:
            return ""

        cards = ""
        for llm in llm_calls:
            service = llm.get('service_name', 'N/A')
            provider = llm.get('provider', 'N/A')
            model = llm.get('model', 'N/A')
            tokens = llm.get('total_tokens', 0)
            cost = llm.get('cost_rub', 0)

            cards += f"""
            <div class="llm-card">
                <div class="service">{service}</div>
                <div class="details">
                    {provider} / {model}<br>
                    {tokens} токенов
                </div>
                <div class="cost">{cost:.4f} руб</div>
            </div>
            """

        return f"""
        <div class="section">
            <h2>LLM вызовы ({len(llm_calls)})</h2>
            <div class="llm-cards">
                {cards}
            </div>
        </div>
        """

    @staticmethod
    def _generate_waterfall_html(stages: List[Dict], total_duration: float) -> str:
        """Генерирует waterfall диаграмму с относительным позиционированием"""
        if not stages or total_duration is None or total_duration == 0:
            return ""

        # Находим минимальное время старта
        min_start_time = min(
            (s.get('start_time', 0) for s in stages if s.get('start_time') is not None),
            default=0
        )

        bars = ""
        for i, stage in enumerate(stages):
            start_time = stage.get('start_time')
            duration = stage.get('duration_ms')
            name = stage.get('name', 'N/A')

            if start_time is None or duration is None:
                continue

            # Вычисляем относительное время в миллисекундах (perf_counter)
            start_offset_ms = (start_time - min_start_time) * 1000  # Конвертируем в мс

            # Вычисляем позицию в процентах от общего времени
            left_percent = (start_offset_ms / total_duration) * 100 if total_duration > 0 else 0
            width_percent = (duration / total_duration) * 100 if total_duration > 0 else 0

            # Ограничиваем чтобы не выходило за границы
            left_percent = min(left_percent, 95)
            width_percent = min(width_percent, 100 - left_percent - 5)

            # Цвет в зависимости от типа этапа (из metadata)
            color = "#667eea"  # Default purple
            if 'filter' in name.lower():
                color = "#f59e0b"  # Orange
            elif 'search' in name.lower():
                color = "#10b981"  # Green
            elif 'problem' in name.lower():
                color = "#8b5cf6"  # Violet

            bars += f"""
            <div class="waterfall-stage"
                 style="left: {left_percent}%; width: {width_percent}%; top: {i * 35 + 40}px; background: {color};"
                 data-details="{name}: {duration:.2f}мс (начало: {start_offset_ms:.0f}мс)">
                {name}
            </div>
            <div class="waterfall-label" style="top: {i * 35 + 45}px;">{name}</div>
            """

        # Добавляем временную шкалу
        total_height = len(stages) * 35 + 80

        return f"""
        <div class="section">
            <h2>Waterfall диаграмма (временная шкала)</h2>
            <div class="waterfall" style="height: {total_height}px;">
                <div style="position: absolute; bottom: 10px; left: 0; right: 0; text-align: center; font-size: 12px; color: #999;">
                    0мс ←———— {total_duration/1000:.1f}с ————→
                </div>
                {bars}
            </div>
        </div>
        """

    @staticmethod
    def _generate_tree_html(stages: List[Dict], microservices: List[Dict], llm_calls: List[Dict]) -> str:
        """Генерирует дерево выполнения с вложенностью

        ИСПРАВЛЕНО (2026-03-05): Добавлено визуальное дерево выполнения запроса
        """
        if not stages and not microservices and not llm_calls:
            return ""

        # Группируем по типу
        tree_items = []

        # 1. Главный этап total_request (корень)
        total_stage = next((s for s in stages if s.get('name') == 'total_request'), None)
        if total_stage:
            duration = total_stage.get('duration_ms', 0)
            tree_items.append({
                'name': 'Обработка запроса',
                'duration': duration,
                'badge': 'Весь запрос',
                'badge_class': 'tree-badge-stage',
                'details': f'Полное время обработки запроса от начала до конца',
                'level': 0
            })

        # 2. Этапы обработки
        for stage in stages:
            name = stage.get('name', 'N/A')
            if name == 'total_request':
                continue

            duration = stage.get('duration_ms', 0)

            # Определяем badge
            if 'filter' in name.lower():
                badge = 'Фильтр'
                badge_class = 'tree-badge-stage'
            elif 'problem' in name.lower():
                badge = 'Накопление'
                badge_class = 'tree-badge-stage'
            elif 'search' in name.lower():
                badge = 'Поиск'
                badge_class = 'tree-badge-stage'
            else:
                badge = 'Этап'
                badge_class = 'tree-badge-stage'

            result = stage.get('result_summary', '')
            details = f"Результат: {result[:80]}..." if len(result) > 80 else f"Результат: {result}"

            tree_items.append({
                'name': name,
                'duration': duration,
                'badge': badge,
                'badge_class': badge_class,
                'details': details,
                'level': 1
            })

        # 3. LLM вызовы
        for llm in llm_calls:
            service = llm.get('service_name', 'Unknown')
            provider = llm.get('provider', 'unknown')
            model = llm.get('model', 'unknown')
            duration = llm.get('duration_ms', 0)
            tokens = llm.get('total_tokens', 0)
            cost = llm.get('cost_rub', 0)

            tree_items.append({
                'name': f'{service} ({provider}/{model})',
                'duration': duration,
                'badge': 'LLM',
                'badge_class': 'tree-badge-llm',
                'details': f'{tokens} токенов, стоимость: {cost:.4f} руб',
                'level': 2
            })

        # 4. Микросервисы
        for ms in microservices:
            name = ms.get('name', 'Unknown')
            duration = ms.get('duration_ms', 0)
            candidates = ms.get('candidates_count', 0)

            tree_items.append({
                'name': name,
                'duration': duration,
                'badge': 'Сервис',
                'badge_class': 'tree-badge-microservice',
                'details': f'Найдено кандидатов: {candidates}',
                'level': 2
            })

        # Генерируем HTML дерева
        tree_html = ""
        for i, item in enumerate(tree_items):
            duration = item.get('duration', 0)
            if duration is None:
                duration_str = "N/A"
                duration_class = ""
            else:
                duration_str = f"{duration:.2f}"
                if duration < 100:
                    duration_class = "fast"
                elif duration < 1000:
                    duration_class = "medium"
                else:
                    duration_class = "slow"

            level_class = "tree-root" if item['level'] == 0 else "tree-node"

            tree_html += f"""
            <div class="{level_class}">
                <div class="tree-content">
                    <div class="tree-header">
                        <div>
                            <span class="tree-title">{item['name']}</span>
                            <span class="tree-badge {item['badge_class']}">{item['badge']}</span>
                        </div>
                        <div class="tree-duration {duration_class}">{duration_str} мс</div>
                    </div>
                    <div class="tree-details">{item['details']}</div>
                </div>
            </div>
            """

        return f"""
        <div class="section">
            <h2>Дерево выполнения запроса</h2>
            <div class="tree-container">
                {tree_html}
            </div>
        </div>
        """

    @classmethod
    def generate_html_report(cls, performance_data: Dict) -> str:
        """
        Генерирует HTML отчет производительности

        Args:
            performance_data: Данные из PerformanceTracer.get_report()

        Returns:
            HTML строка с отчетом
        """
        session_id = performance_data.get('session_id', 'N/A')
        total_duration = performance_data.get('total_duration_ms', 0)
        microservices_total = performance_data.get('microservices_total_ms', 0)
        llm_cost = performance_data.get('llm_total_cost_rub', 0)
        llm_tokens = performance_data.get('llm_total_tokens', 0)

        # ИСПРАВЛЕНО (2026-03-05): Исправляем несоответствие ключей
        # В metadata используется 'stages', а не 'timings'
        stages = performance_data.get('stages', performance_data.get('timings', []))
        microservices = performance_data.get('microservices', [])
        llm_calls = performance_data.get('llm_calls', [])

        stages_html = cls._generate_stages_html(stages)
        microservices_html = cls._generate_microservices_html(microservices)
        llm_calls_html = cls._generate_llm_calls_html(llm_calls)
        waterfall_html = cls._generate_waterfall_html(stages, total_duration)
        tree_html = cls._generate_tree_html(stages, microservices, llm_calls)  # ИСПРАВЛЕНО (2026-03-05)

        return cls.HTML_TEMPLATE.format(
            session_id=session_id,
            generated_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            total_duration_ms=total_duration or 0,
            microservices_total_ms=microservices_total or 0,
            llm_total_cost_rub=llm_cost or 0,
            llm_total_tokens=llm_tokens or 0,
            stages_html=stages_html,
            tree_html=tree_html,  # ИСПРАВЛЕНО (2026-03-05)
            microservices_html=microservices_html,
            llm_calls_html=llm_calls_html,
            waterfall_html=waterfall_html
        )

    @classmethod
    def generate_from_session_id(cls, session_id: str) -> str:
        """
        Генерирует отчет из данных сессии в БД

        Args:
            session_id: ID сессии

        Returns:
            HTML строка с отчетом
        """
        # TODO: Загрузить performance данные из dialog_logs.metadata
        # Пока возвращаем заглушку
        return cls.HTML_TEMPLATE.format(
            session_id=session_id,
            generated_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            total_duration_ms=0,
            microservices_total_ms=0,
            llm_total_cost_rub=0,
            llm_total_tokens=0,
            stages_html="<div class='section'><p>Данные производительности будут доступны после следующего запроса</p></div>",
            microservices_html="",
            llm_calls_html="",
            waterfall_html=""
        )
