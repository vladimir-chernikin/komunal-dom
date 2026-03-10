#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AICostTrackingService - микросервис отслеживания расходов на AI
Отслеживает стоимость запросов к разным AI моделям и сохраняет в БД
"""

import logging
import uuid
import time
import json
from datetime import datetime, timezone
from typing import Dict, Optional, Any, List
from decimal import Decimal
from django.db import connection

logger = logging.getLogger(__name__)


class AICostTrackingService:
    """
    Микросервис отслеживания расходов на AI.

    Предназначен для:
    - Отслеживания стоимости каждого AI запроса
    - Сохранения истории запросов в БД
    - Аналитики расходов (дневной, месячной)
    - Мониторинга производительности моделей
    """

    # Тарифы за 1000 токенов в USD
    RATES = {
        'yandexgpt-lite': Decimal('0.00024'),   # ~0.24 копейки за 1000 токенов
        'yandexgpt-pro': Decimal('0.0005'),     # ~0.5 копейки за 1000 токенов
        'yandexgpt-plus': Decimal('0.0007'),    # ~0.7 копейки за 1000 токенов
        'gpt-3.5-turbo': Decimal('0.0005'),     # ~0.5 копейки за 1000 токенов
        'gpt-4': Decimal('0.003'),              # ~3 копейки за 1000 токенов
        'gpt-4-turbo': Decimal('0.001'),        # ~1 копейка за 1000 токенов
        'gemini-pro': Decimal('0.00005'),       # ~0.05 копейки за 1000 токенов
        'claude-3-sonnet': Decimal('0.00075'),  # ~0.75 копейки за 1000 токенов
        'claude-3-opus': Decimal('0.0025'),     # ~2.5 копейки за 1000 токенов
    }

    def __init__(self):
        """Инициализация сервиса отслеживания расходов"""
        logger.info("AICostTrackingService initialized")

    def track_llm_request(self,
                         trace_id: str,
                         dialog_id: str,
                         user_id: int,
                         model_name: str,
                         prompt_tokens: int = 0,
                         completion_tokens: int = 0,
                         response_time_ms: int = 0,
                         success: bool = True,
                         error_message: str = None,
                         ai_provider: str = None,
                         service_type: str = None,
                         additional_data: Dict = None) -> Dict[str, Any]:
        """
        Отследить LLM запрос и сохранить в БД.

        Args:
            trace_id: Уникальный ID трассировки запроса
            dialog_id: ID диалога
            user_id: ID пользователя
            model_name: Название модели (yandexgpt-lite, gpt-4, etc.)
            prompt_tokens: Количество токенов в промпте
            completion_tokens: Количество токенов в ответе
            response_time_ms: Время ответа в миллисекундах
            success: Успешность запроса
            error_message: Сообщение об ошибке (если есть)
            ai_provider: Провайдер AI (yandex, openai, google, etc.)
            service_type: Тип услуги (service_detection, address_extraction, etc.)
            additional_data: Дополнительные данные в JSON

        Returns:
            Dict с информацией о созданном запросе:
            {
                'request_id': str,
                'cost_usd': Decimal,
                'cost_rub': Decimal,
                'total_tokens': int,
                'model': str,
                'trace_id': str,
                'success': bool
            }
        """
        try:
            # Генерируем UUID для запроса
            request_id = str(uuid.uuid4())

            # Рассчитываем общие токены
            total_tokens = prompt_tokens + completion_tokens

            # Рассчитываем стоимость
            cost_usd = self._calculate_cost(model_name, total_tokens)
            cost_rub = cost_usd * Decimal('100')  # Конвертируем в рубли

            # Сохраняем в БД
            self._save_to_database(
                request_id=request_id,
                trace_id=trace_id,
                dialog_id=dialog_id,
                user_id=user_id,
                ai_provider=ai_provider or self._get_provider_by_model(model_name),
                model_name=model_name,
                service_type=service_type,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                response_time_ms=response_time_ms,
                cost_usd=cost_usd,
                success=success,
                error_message=error_message,
                additional_data=additional_data
            )

            # Логируем результат
            status = "✅ OK" if success else "❌ ERROR"
            logger.info(
                f"{status} | Model: {model_name} | Tokens: {total_tokens} | "
                f"Cost: ${cost_usd:.6f} ({cost_rub:.4f}₽) | Time: {response_time_ms}ms | "
                f"Trace: {trace_id[:8]}..."
            )

            return {
                'request_id': request_id,
                'cost_usd': float(cost_usd),
                'cost_rub': float(cost_rub),
                'total_tokens': total_tokens,
                'model': model_name,
                'trace_id': trace_id,
                'success': success
            }

        except Exception as e:
            logger.error(f"Error tracking LLM request: {e}")
            return {
                'request_id': None,
                'cost_usd': 0.0,
                'cost_rub': 0.0,
                'total_tokens': 0,
                'model': model_name,
                'trace_id': trace_id,
                'success': False,
                'error': str(e)
            }

    def _calculate_cost(self, model_name: str, tokens: int) -> Decimal:
        """
        Рассчитать стоимость запроса.

        Args:
            model_name: Название модели
            tokens: Количество токенов

        Returns:
            Decimal: Стоимость в USD
        """
        try:
            rate = self.RATES.get(model_name, Decimal('0'))
            if rate == 0:
                logger.warning(f"Unknown model: {model_name}, cost set to 0")
                return Decimal('0')

            # Формула: (tokens / 1000) * rate
            cost = (Decimal(tokens) / Decimal('1000')) * rate
            return cost.quantize(Decimal('0.000001'))

        except Exception as e:
            logger.error(f"Error calculating cost: {e}")
            return Decimal('0')

    def _get_provider_by_model(self, model_name: str) -> str:
        """
        Определить провайдера по названию модели.

        Args:
            model_name: Название модели

        Returns:
            str: Название провайдера
        """
        if model_name.startswith('yandexgpt'):
            return 'yandex'
        elif model_name.startswith('gpt-'):
            return 'openai'
        elif model_name.startswith('gemini'):
            return 'google'
        elif model_name.startswith('claude'):
            return 'anthropic'
        else:
            return 'unknown'

    def _save_to_database(self,
                         request_id: str,
                         trace_id: str,
                         dialog_id: str,
                         user_id: int,
                         ai_provider: str,
                         model_name: str,
                         service_type: str,
                         prompt_tokens: int,
                         completion_tokens: int,
                         total_tokens: int,
                         response_time_ms: int,
                         cost_usd: Decimal,
                         success: bool,
                         error_message: str = None,
                         additional_data: Dict = None) -> None:
        """
        Сохранить информацию о запросе в БД.

        Args:
            Все параметры для сохранения в таблицу ai_cost_tracking
        """
        try:
            with connection.cursor() as cursor:
                # Используем существующую структуру таблицы
                # Добавляем trace_id в additional_data для отладки
                additional_data = additional_data or {}
                additional_data['trace_id'] = trace_id
                additional_data['request_id'] = request_id

                cursor.execute("""
                    INSERT INTO ai_cost_tracking (
                        dialog_id, user_id, ai_provider, model_name,
                        service_type, input_tokens, output_tokens, total_tokens,
                        response_time_ms, cost_rub, success, error_message,
                        additional_data, request_timestamp
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s
                    )
                """, [
                    dialog_id,
                    user_id,
                    ai_provider,
                    model_name,
                    service_type,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    response_time_ms,
                    float(cost_usd * Decimal('100')),  # Конвертируем в рубли
                    success,
                    error_message,
                    json.dumps(additional_data, ensure_ascii=False),
                    datetime.now(timezone.utc)
                ])

            logger.info(f"Saved AI request to database: {request_id}")

        except Exception as e:
            logger.error(f"Error saving AI request to database: {e}")

    def get_daily_costs(self, date: str = None) -> Dict[str, Any]:
        """
        Получить статистику расходов за день.

        Args:
            date: Дата в формате YYYY-MM-DD (если None - сегодня)

        Returns:
            Dict с дневной статистикой:
            {
                'date': str,
                'total_cost_rub': float,
                'requests_count': int,
                'tokens_used': int,
                'avg_response_time_ms': float,
                'success_rate': float,
                'by_model': {
                    'model_name': {
                        'requests': int,
                        'tokens': int,
                        'cost_rub': float,
                        'avg_response_time_ms': float,
                        'success_rate': float
                    }
                }
            }
        """
        try:
            if date is None:
                date = datetime.now().strftime('%Y-%m-%d')

            with connection.cursor() as cursor:
                # Общая статистика за день
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_requests,
                        SUM(total_tokens) as total_tokens,
                        SUM(cost_rub) as total_cost_rub,
                        AVG(response_time_ms) as avg_response_time_ms,
                        SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as successful_requests
                    FROM ai_cost_tracking
                    WHERE DATE(request_timestamp) = %s
                """, [date])

                total_stats = cursor.fetchone()

                if not total_stats or total_stats[0] == 0:
                    return {
                        'date': date,
                        'total_cost_rub': 0.0,
                        'requests_count': 0,
                        'tokens_used': 0,
                        'avg_response_time_ms': 0.0,
                        'success_rate': 0.0,
                        'by_model': {}
                    }

                # Статистика по моделям
                cursor.execute("""
                    SELECT
                        model_name,
                        COUNT(*) as requests,
                        SUM(total_tokens) as tokens,
                        SUM(cost_rub) as cost_rub,
                        AVG(response_time_ms) as avg_response_time_ms,
                        SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as successful_requests
                    FROM ai_cost_tracking
                    WHERE DATE(request_timestamp) = %s
                    GROUP BY model_name
                    ORDER BY cost_rub DESC
                """, [date])

                model_stats = cursor.fetchall()

                total_requests, total_tokens, total_cost, avg_response_time, successful_requests = total_stats
                success_rate = (successful_requests / total_requests) * 100 if total_requests > 0 else 0

                by_model = {}
                for model_name, requests, tokens, cost, avg_time, successful in model_stats:
                    model_success_rate = (successful / requests) * 100 if requests > 0 else 0
                    by_model[model_name] = {
                        'requests': requests,
                        'tokens': tokens,
                        'cost_rub': float(cost),
                        'avg_response_time_ms': float(avg_time),
                        'success_rate': model_success_rate
                    }

                return {
                    'date': date,
                    'total_cost_rub': float(total_cost),
                    'requests_count': total_requests,
                    'tokens_used': total_tokens,
                    'avg_response_time_ms': float(avg_response_time),
                    'success_rate': success_rate,
                    'by_model': by_model
                }

        except Exception as e:
            logger.error(f"Error getting daily costs: {e}")
            return {'error': str(e)}

    def get_monthly_costs(self, year: int = None, month: int = None) -> Dict[str, Any]:
        """
        Получить статистику расходов за месяц.

        Args:
            year: Год (если None - текущий)
            month: Месяц (если None - текущий)

        Returns:
            Dict с месячной статистикой и daily_breakdown
        """
        try:
            if year is None or month is None:
                now = datetime.now()
                year = year or now.year
                month = month or now.month

            with connection.cursor() as cursor:
                # Общая статистика за месяц
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_requests,
                        SUM(total_tokens) as total_tokens,
                        SUM(cost_rub) as total_cost_rub,
                        AVG(response_time_ms) as avg_response_time_ms,
                        SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as successful_requests
                    FROM ai_cost_tracking
                    WHERE EXTRACT(YEAR FROM request_timestamp) = %s
                      AND EXTRACT(MONTH FROM request_timestamp) = %s
                """, [year, month])

                total_stats = cursor.fetchone()

                if not total_stats or total_stats[0] == 0:
                    return {
                        'year': year,
                        'month': month,
                        'total_cost_rub': 0.0,
                        'requests_count': 0,
                        'tokens_used': 0,
                        'avg_response_time_ms': 0.0,
                        'success_rate': 0.0,
                        'daily_breakdown': []
                    }

                # Статистика по дням
                cursor.execute("""
                    SELECT
                        DATE(request_timestamp) as date,
                        COUNT(*) as requests,
                        SUM(total_tokens) as tokens,
                        SUM(cost_rub) as cost_rub,
                        AVG(response_time_ms) as avg_response_time_ms,
                        SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as successful_requests
                    FROM ai_cost_tracking
                    WHERE EXTRACT(YEAR FROM request_timestamp) = %s
                      AND EXTRACT(MONTH FROM request_timestamp) = %s
                    GROUP BY DATE(request_timestamp)
                    ORDER BY date DESC
                """, [year, month])

                daily_data = cursor.fetchall()

                total_requests, total_tokens, total_cost, avg_response_time, successful_requests = total_stats
                success_rate = (successful_requests / total_requests) * 100 if total_requests > 0 else 0

                daily_breakdown = []
                for date, requests, tokens, cost, avg_time, successful in daily_data:
                    day_success_rate = (successful / requests) * 100 if requests > 0 else 0
                    daily_breakdown.append({
                        'date': date.strftime('%Y-%m-%d'),
                        'requests': requests,
                        'tokens': tokens,
                        'cost_rub': float(cost),
                        'avg_response_time_ms': float(avg_time),
                        'success_rate': day_success_rate
                    })

                return {
                    'year': year,
                    'month': month,
                    'total_cost_rub': float(total_cost),
                    'requests_count': total_requests,
                    'tokens_used': total_tokens,
                    'avg_response_time_ms': float(avg_response_time),
                    'success_rate': success_rate,
                    'daily_breakdown': daily_breakdown
                }

        except Exception as e:
            logger.error(f"Error getting monthly costs: {e}")
            return {'error': str(e)}

    def get_user_costs(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """
        Получить расходы конкретного пользователя за период.

        Args:
            user_id: ID пользователя
            days: Количество дней для анализа

        Returns:
            Dict со статистикой пользователя
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_requests,
                        SUM(total_tokens) as total_tokens,
                        SUM(cost_rub) as total_cost_rub,
                        AVG(response_time_ms) as avg_response_time_ms,
                        COUNT(DISTINCT DATE(request_timestamp)) as active_days,
                        MIN(request_timestamp) as first_request,
                        MAX(request_timestamp) as last_request
                    FROM ai_cost_tracking
                    WHERE user_id = %s
                      AND request_timestamp >= NOW() - INTERVAL '%s days'
                """, [user_id, days])

                stats = cursor.fetchone()

                if not stats or stats[0] == 0:
                    return {
                        'user_id': user_id,
                        'days_period': days,
                        'total_cost_rub': 0.0,
                        'requests_count': 0,
                        'tokens_used': 0,
                        'avg_response_time_ms': 0.0,
                        'active_days': 0
                    }

                requests, tokens, cost, avg_time, active_days, first_request, last_request = stats

                return {
                    'user_id': user_id,
                    'days_period': days,
                    'total_cost_rub': float(cost),
                    'requests_count': requests,
                    'tokens_used': tokens,
                    'avg_response_time_ms': float(avg_time),
                    'active_days': active_days,
                    'first_request': first_request.isoformat() if first_request else None,
                    'last_request': last_request.isoformat() if last_request else None
                }

        except Exception as e:
            logger.error(f"Error getting user costs: {e}")
            return {'error': str(e)}

    def get_model_performance(self, model_name: str = None, days: int = 7) -> Dict[str, Any]:
        """
        Получить статистику производительности моделей.

        Args:
            model_name: Название модели (если None - все модели)
            days: Период в днях

        Returns:
            Dict со статистикой производительности
        """
        try:
            with connection.cursor() as cursor:
                if model_name:
                    cursor.execute("""
                        SELECT
                            model_name,
                            COUNT(*) as total_requests,
                            SUM(total_tokens) as total_tokens,
                            SUM(cost_rub) as total_cost_rub,
                            AVG(response_time_ms) as avg_response_time_ms,
                            MIN(response_time_ms) as min_response_time_ms,
                            MAX(response_time_ms) as max_response_time_ms,
                            SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as successful_requests
                        FROM ai_cost_tracking
                        WHERE model_name = %s
                          AND request_timestamp >= NOW() - INTERVAL '%s days'
                        GROUP BY model_name
                    """, [model_name, days])
                else:
                    cursor.execute("""
                        SELECT
                            model_name,
                            COUNT(*) as total_requests,
                            SUM(total_tokens) as total_tokens,
                            SUM(cost_rub) as total_cost_rub,
                            AVG(response_time_ms) as avg_response_time_ms,
                            MIN(response_time_ms) as min_response_time_ms,
                            MAX(response_time_ms) as max_response_time_ms,
                            SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as successful_requests
                        FROM ai_cost_tracking
                        WHERE request_timestamp >= NOW() - INTERVAL '%s days'
                        GROUP BY model_name
                        ORDER BY total_requests DESC
                    """, [days])

                results = cursor.fetchall()

                model_stats = []
                for row in results:
                    (model, requests, tokens, cost, avg_time, min_time, max_time, successful) = row
                    success_rate = (successful / requests) * 100 if requests > 0 else 0

                    model_stats.append({
                        'model_name': model,
                        'total_requests': requests,
                        'total_tokens': tokens,
                        'total_cost_rub': float(cost),
                        'avg_response_time_ms': float(avg_time),
                        'min_response_time_ms': float(min_time),
                        'max_response_time_ms': float(max_time),
                        'success_rate': success_rate
                    })

                return {
                    'period_days': days,
                    'models_count': len(model_stats),
                    'models': model_stats
                }

        except Exception as e:
            logger.error(f"Error getting model performance: {e}")
            return {'error': str(e)}