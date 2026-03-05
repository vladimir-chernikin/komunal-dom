#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Performance Tracer - трекинг времени выполнения микросервисов

СОЗДАНО: 2026-03-04
ЦЕЛЬ: Замер времени выполнения каждого этапа обработки запроса с точностью до миллисекунды

ИСПОЛЬЗОВАНИЕ:
    from performance_tracer import PerformanceTracer

    tracer = PerformanceTracer()
    tracer.start("total_request")

    tracer.start("filter_detection")
    # ... код ...
    tracer.end("filter_detection")

    tracer.end("total_request")
    report = tracer.get_report()
"""

import time
import logging
from typing import Dict, List, Any
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class PerformanceTracer:
    """
    Трекер времени выполнения для микросервисов

    Хранит информацию о времени выполнения каждого этапа
    """

    def __init__(self, session_id: str = None):
        """
        Args:
            session_id: ID сессии для привязки к диалогу
        """
        self.session_id = session_id
        self._timings: Dict[str, Dict] = {}
        self._stack: List[str] = []
        self._llm_calls: List[Dict] = []
        self._microservices: List[Dict] = []

    def start(self, name: str, metadata: Dict = None):
        """
        Начало замера этапа

        Args:
            name: Название этапа (например, "TagSearchService")
            metadata: Дополнительные метаданные (параметры вызова и т.д.)
        """
        start_time = time.perf_counter()

        self._timings[name] = {
            'name': name,
            'start_time': start_time,
            'end_time': None,
            'duration_ms': None,
            'metadata': metadata or {},
            'children': []
        }

        self._stack.append(name)

    def end(self, name: str = None, result: Any = None, error: Exception = None):
        """
        Конец замера этапа

        Args:
            name: Название этапа (если None, берется последний из стека)
            result: Результат выполнения
            error: Ошибка если была
        """
        end_time = time.perf_counter()

        if name is None:
            if not self._stack:
                logger.warning("[PerformanceTracer] Пустой stack, нельзя вызвать end() без start()")
                return
            name = self._stack.pop()
        else:
            # Удаляем из стека если там есть
            if name in self._stack:
                self._stack.remove(name)

        if name not in self._timings:
            logger.warning(f"[PerformanceTracer] Этап '{name}' не был начат через start()")
            return

        timing = self._timings[name]
        timing['end_time'] = end_time
        timing['duration_ms'] = (end_time - timing['start_time']) * 1000

        if result is not None:
            timing['result_summary'] = self._summarize_result(result)

        if error is not None:
            timing['error'] = str(error)

    def track_llm_call(self, provider: str, model: str, prompt_tokens: int,
                       completion_tokens: int, cost_rub: float, service_name: str,
                       duration_ms: float = None, prompt_length: int = 0,
                       response_length: int = 0):
        """
        Регистрация LLM вызова

        Args:
            provider: Провайдер (yandexgpt, openai и т.д.)
            model: Модель (lite, pro, gpt-4 и т.д.)
            prompt_tokens: Токены в промпте
            completion_tokens: Токены в ответе
            cost_rub: Стоимость в рублях
            service_name: Какой микросервис вызвал LLM
            duration_ms: Время выполнения вызова в миллисекундах
            prompt_length: Длина промпта в символах
            response_length: Длина ответа в символах
        """
        self._llm_calls.append({
            'timestamp': datetime.now().isoformat(),
            'provider': provider,
            'model': model,
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': prompt_tokens + completion_tokens,
            'cost_rub': cost_rub,
            'service_name': service_name,
            'duration_ms': duration_ms,
            'prompt_length': prompt_length,
            'response_length': response_length
        })

    def track_microservice(self, name: str, duration_ms: float,
                          candidates_count: int = 0, metadata: Dict = None):
        """
        Регистрация выполнения микросервиса

        Args:
            name: Название микросервиса
            duration_ms: Время выполнения в миллисекундах
            candidates_count: Количество найденных кандидатов
            metadata: Дополнительные метаданные
        """
        self._microservices.append({
            'name': name,
            'duration_ms': duration_ms,
            'candidates_count': candidates_count,
            'metadata': metadata or {}
        })

    def _summarize_result(self, result: Any) -> str:
        """
        Краткое описание результата для отчета
        """
        if result is None:
            return "None"

        if isinstance(result, dict):
            # Извлекаем ключевую информацию
            if 'status' in result:
                return f"status={result['status']}"
            if 'candidates' in result:
                count = len(result.get('candidates', []))
                return f"{count} candidates"
            if 'question' in result:
                return f"question: {result['question'][:50]}..."
            return f"dict with {len(result)} keys"

        if isinstance(result, list):
            return f"list with {len(result)} items"

        if isinstance(result, str):
            return result[:100] if len(result) > 100 else result

        return str(type(result).__name__)

    def get_report(self) -> Dict:
        """
        Генерирует отчет производительности

        Returns:
            Dict с отчетом о времени выполнения всех этапов
        """
        # Сортируем этапы по времени начала
        sorted_timings = sorted(
            self._timings.values(),
            key=lambda x: x['start_time']
        )

        # Вычисляем общее время
        total_duration = None
        if 'total_request' in self._timings:
            total_duration = self._timings['total_request']['duration_ms']

        # Суммарное время по микросервисам
        microservices_total = sum(ms['duration_ms'] for ms in self._microservices)

        # Суммарное время LLM вызовов (приблизительно через стоимость)
        llm_total_cost = sum(llm['cost_rub'] for llm in self._llm_calls)
        llm_total_tokens = sum(llm['total_tokens'] for llm in self._llm_calls)

        return {
            'session_id': self.session_id,
            'total_duration_ms': total_duration,
            'microservices_total_ms': microservices_total,
            'llm_total_cost_rub': llm_total_cost,
            'llm_total_tokens': llm_total_tokens,
            'timings': sorted_timings,
            'microservices': self._microservices,
            'llm_calls': self._llm_calls,
            'generated_at': datetime.now().isoformat()
        }

    def get_flattened_report(self) -> List[Dict]:
        """
        Плоский список этапов для отображения в таблице

        Returns:
            List[Dict] с информацией о каждом этапе
        """
        report = []

        # Добавляем основные этапы
        for timing in self._timings.values():
            report.append({
                'name': timing['name'],
                'start_time': timing['start_time'],
                'end_time': timing['end_time'],
                'duration_ms': timing['duration_ms'],
                'metadata': timing['metadata'],
                'result_summary': timing.get('result_summary', ''),
                'error': timing.get('error'),
                'type': 'stage'
            })

        # Добавляем микросервисы
        for ms in self._microservices:
            report.append({
                'name': ms['name'],
                'duration_ms': ms['duration_ms'],
                'metadata': ms['metadata'],
                'candidates_count': ms.get('candidates_count', 0),
                'type': 'microservice'
            })

        # Добавляем LLM вызовы с duration_ms
        for llm in self._llm_calls:
            report.append({
                'name': f"{llm['service_name']} ({llm['provider']}/{llm['model']})",
                'duration_ms': llm.get('duration_ms'),
                'metadata': llm,
                'type': 'llm_call',
                'tokens': llm.get('total_tokens', 0),
                'cost': llm.get('cost_rub', 0)
            })

        # Сортируем по start_time если есть, иначе по индексу
        return sorted(report, key=lambda x: x.get('start_time', 0))

    def save_to_metadata(self) -> Dict:
        """
        Подготавливает данные для сохранения в metadata поля dialog_logs

        Returns:
            Dict для записи в JSONB metadata
        """
        report = self.get_report()

        # ИСПРАВЛЕНО (2026-03-05): Добавляем start_time для waterfall диаграммы
        # Конвертируем perf_counter значения в относительное время от первого этапа
        timings = report['timings']
        if timings:
            min_start = min(t.get('start_time', 0) for t in timings if t.get('start_time') is not None)

            stages = []
            for t in timings:
                if t['duration_ms'] is not None:
                    stage_data = {
                        'name': t['name'],
                        'duration_ms': t['duration_ms'],
                        'metadata': t.get('metadata', {}),
                        'result': t.get('result_summary', '')
                    }
                    # Добавляем start_time если есть (для waterfall)
                    if t.get('start_time') is not None:
                        stage_data['start_time'] = t['start_time']
                    stages.append(stage_data)
        else:
            stages = []

        return {
            'performance': {
                'total_duration_ms': report['total_duration_ms'],
                'microservices_total_ms': report['microservices_total_ms'],
                'llm_total_cost_rub': report['llm_total_cost_rub'],
                'llm_total_tokens': report['llm_total_tokens'],
                'stages': stages,
                'microservices': report['microservices'],
                'llm_calls': report['llm_calls']
            }
        }


# Контекстный менеджер для автоматического замера
class TimedContext:
    """Контекстный менеджер для замера времени выполнения"""

    def __init__(self, tracer: PerformanceTracer, name: str, metadata: Dict = None):
        self.tracer = tracer
        self.name = name
        self.metadata = metadata
        self.result = None
        self.error = None

    def __enter__(self):
        self.tracer.start(self.name, self.metadata)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.error = exc_val
        self.tracer.end(self.name, self.result, self.error)
        return False  # Не подавляем исключения


def timed(tracer: PerformanceTracer, name: str = None):
    """
    Декоратор для автоматического замера времени функции

    Использование:
        @timed(tracer, "MyService")
        async def my_function():
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            stage_name = name or func.__name__
            with TimedContext(tracer, stage_name):
                result = func(*args, **kwargs)
                return result
        return wrapper
    return decorator
