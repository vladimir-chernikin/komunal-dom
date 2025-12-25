#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Главный Агент системы определения услуг
Координирует работу микросервисов поиска услуг с воронкой точности
"""

import logging
import asyncio
import traceback
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass
from django.db import connection
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


@dataclass
class ServiceCandidate:
    """Кандидат услуги"""
    service_id: int
    service_name: str
    confidence: float
    source: str  # источник: tag_search, semantic_search, vector_search, ai_agent


class MainAgent:
    """
    Главный Агент координирует работу микросервисов:

    ВОРОНКА ТОЧНОСТИ:
    1. Сначала запускаем БЫСТРЫЕ микросервисы параллельно:
       - TagSearchService (поиск по тегам)
       - SemanticSearchService (логико-семантический поиск)
       - VectorSearchService (поиск по векторной базе)

    2. Анализируем результаты быстрых сервисов:
       - Есть 1 кандидат с confidence > 85% → SUCCESS
       - Есть пересечения между сервисами → повышаем confidence
       - Нет кандидатов или сильное расхождение → ШАГ 3

    3. ЗАПУСКАЕМ AI ТОЛЬКО ПРИ НУЖДЕ:
       - Нет результатов от быстрых сервисов
       - Сильное расхождение результатов
       - Низкая уверенность (< 40%)
    """

    def __init__(self):
        self.tag_search = None
        self.semantic_search = None
        self.vector_search = None
        self.ai_agent = None
        self.filter_detection = None  # ИСПРАВЛЕНО: Добавлен сервис определения фильтров
        self.address_extractor = None  # ДОБАВЛЕНО: Сервис извлечения адреса
        self.confidence_threshold = 0.75  # Порог уверенности

        # Инициализируем микросервисы
        self._init_services()

        logger.info("Главный Агент инициализирован с микросервисной архитектурой")

    def _init_services(self):
        """Инициализация микросервисов"""
        try:
            from tag_search_service import TagSearchService
            self.tag_search = TagSearchService()
            logger.info("TagSearchService инициализирован")
        except ImportError:
            logger.warning("TagSearchService не найден, будет пропущен")

        try:
            from semantic_search_service import SemanticSearchService
            self.semantic_search = SemanticSearchService()
            logger.info("SemanticSearchService инициализирован")
        except ImportError:
            logger.warning("SemanticSearchService не найден, будет пропущен")

        try:
            from vector_search_service import VectorSearchService
            self.vector_search = VectorSearchService()
            logger.info("VectorSearchService инициализирован")
        except ImportError:
            logger.warning("VectorSearchService не найден, будет пропущен")

        try:
            from ai_agent_service import AIAgentService
            self.ai_agent = AIAgentService()
            logger.info("AIAgentService инициализирован")
        except ImportError:
            logger.warning("AIAgentService не найден, будет пропущен")

        # ИСПРАВЛЕНО: Добавлен FilterDetectionService (использует AIAgentService)
        try:
            from filter_detection_service import FilterDetectionService
            # Передаем ai_agent в FilterDetectionService чтобы не дублировать вызовы LLM
            self.filter_detection = FilterDetectionService(ai_agent_service=self.ai_agent)
            logger.info("FilterDetectionService инициализирован (через AIAgentService)")
        except ImportError:
            logger.warning("FilterDetectionService не найден, будет пропущен")

        # ДОБАВЛЕНО: AddressExtractor для извлечения адреса из сообщения
        try:
            from service_detection_modules import AddressExtractor
            self.address_extractor = AddressExtractor()
            logger.info("AddressExtractor инициализирован в MainAgent")
        except ImportError:
            logger.warning("AddressExtractor не найден, извлечение адреса недоступно")

    def _add_address_to_result(self, result: Dict, address_components: Dict) -> Dict:
        """
        Добавляет адресные компоненты к результату

        Args:
            result: Исходный результат
            address_components: Компоненты адреса из AddressExtractor

        Returns:
            Dict: Результат с добавленными адресными компонентами
        """
        if address_components and any(address_components.values()):
            result['address_components'] = address_components
            # Формируем строку адреса для удобства
            parts = []
            if address_components.get('street'):
                parts.append(f"ул. {address_components['street']}")
            if address_components.get('house_number'):
                parts.append(f"д. {address_components['house_number']}")
            if address_components.get('apartment_number'):
                parts.append(f"кв. {address_components['apartment_number']}")
            if parts:
                result['address_string'] = ', '.join(parts)
        return result

    async def process_service_detection(self, message_text: str, user_context: Dict = None) -> Dict:
        """
        Основной метод определения услуги через воронку точности

        Args:
            message_text: Текст сообщения пользователя (может включать контекст)
            user_context: Контекст пользователя, включая историю диалога

        Returns:
            Dict: Результат с найденными услугами
        """
        # Извлекаем оригинальное сообщение и контекст
        original_message = message_text
        is_followup = False
        dialog_history = []

        if user_context:
            original_message = user_context.get('original_message', message_text)
            is_followup = user_context.get('is_followup', False)
            dialog_history = user_context.get('dialog_history', [])

            if is_followup and dialog_history:
                logger.info(f"Главный Агент обрабатывает уточняющее сообщение: '{original_message}' (история: {len(dialog_history)} сообщений)")
            else:
                logger.info(f"Главный Агент начал обработку: '{message_text[:50]}...'")
        else:
            logger.info(f"Главный Агент начал обработку: '{message_text[:50]}...'")

        # Формируем поисковый текст
        # ИСПРАВЛЕНО: Для followup сообщений объединяем с предыдущим пользовательским сообщением
        search_text = message_text

        if is_followup and dialog_history:
            # Ищем предыдущее сообщение пользователя для объединения контекста
            previous_user_messages = [msg for msg in dialog_history if msg.get('role') == 'user']

            # ИСПРАВЛЕНО (2025-12-25): Исключаем текущее сообщение из истории если оно там есть
            # (потому что MessageHandlerService логирует ДО вызова MainAgent)
            if previous_user_messages and previous_user_messages[-1].get('text', '') == message_text:
                previous_user_messages = previous_user_messages[:-1]
                logger.info(f"Followup: исключено текущее сообщение из истории (уже в БД)")

            # ИСПРАВЛЕНО (2025-12-25): Исключаем приветствия из контекста
            GREETING_KEYWORDS = ['привет', 'здравств', 'хай', 'hello', 'hi', 'добрый день', 'доброе утро', 'добрый вечер']
            non_greeting_messages = [
                msg for msg in previous_user_messages
                if not any(kw in msg.get('text', '').lower() for kw in GREETING_KEYWORDS)
            ]
            if len(non_greeting_messages) < len(previous_user_messages):
                logger.info(f"Followup: исключены приветствия из истории: {len(previous_user_messages) - len(non_greeting_messages)} шт")
            previous_user_messages = non_greeting_messages

            if previous_user_messages:
                # ИСПРАВЛЕНО (2025-12-25): Отладочный вывод
                logger.info(f"Followup: всего user сообщений в истории: {len(previous_user_messages)}")
                logger.info(f"Followup: последние 2 текста: {[m.get('text', '')[:30] for m in previous_user_messages[-2:]]}")

                # Берем последние 2 пользовательских сообщения для контекста
                recent_user_texts = [msg.get('text', '') for msg in previous_user_messages[-2:]]
                # Объединяем: "предыдущий текст + текущий текст"
                combined_text = ' '.join(recent_user_texts + [message_text])
                search_text = combined_text
                logger.info(f"Followup: объединен контекст: '{search_text[:150]}...'")

        logger.info(f"Поисковый текст: '{search_text[:100]}...'")

        # ДОБАВЛЕНО: Извлекаем адрес из сообщения (если доступен AddressExtractor)
        address_components = {}
        if self.address_extractor:
            try:
                # Извлекаем адресные компоненты из оригинального сообщения
                # context_memory может быть передан через user_context для DialogMemoryManager
                context_memory = user_context.get('context_memory') if user_context else None
                address_components = self.address_extractor.extract_address_components(
                    original_message,
                    context_memory=context_memory
                )
                logger.info(f"Извлечены адресные компоненты: {address_components}")
            except Exception as e:
                logger.warning(f"Ошибка извлечения адреса: {e}")

        try:
            # ===== ШАГ 1: Параллельно запускаем БЫСТРЫЕ микросервисы =====
            search_tasks = []

            if self.tag_search:
                search_tasks.append(self._run_tag_search(search_text))

            if self.semantic_search:
                search_tasks.append(self._run_semantic_search(search_text))

            if self.vector_search:
                search_tasks.append(self._run_vector_search(search_text))

            # Ждем результаты от быстрых микросервисов
            if search_tasks:
                search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            else:
                return self._create_error_result("Нет доступных микросервисов")

            # ===== ШАГ 2: Анализируем результаты быстрых сервисов по ТЗ =====
            # Работаем с множествами service_id от каждого сервиса
            service_sets = []
            service_results_map = {}  # {service_id: [sources]}

            for i, result in enumerate(search_results):
                if isinstance(result, Exception):
                    logger.error(f"Ошибка микросервиса: {result}")
                    continue

                if not result or not result.get('candidates'):
                    continue

                # Создаем множество service_id от этого сервиса
                service_ids = {c['service_id'] for c in result['candidates']}
                service_sets.append(service_ids)

                # Запоминаем источники для каждого service_id
                source_name = result.get('method', f'service_{i}')
                for candidate in result['candidates']:
                    sid = candidate['service_id']
                    if sid not in service_results_map:
                        service_results_map[sid] = {
                            'service_id': sid,
                            'service_name': candidate['service_name'],
                            'sources': [],
                            'all_data': []
                        }
                    service_results_map[sid]['sources'].append(source_name)
                    service_results_map[sid]['all_data'].append(candidate)

            logger.info(f"Получено {len(service_sets)} множеств от микросервисов")
            for i, s in enumerate(service_sets):
                logger.info(f"  Сервис {i}: {len(s)} услуг")

            # ===== ТЗ 3.2.1: Проверяем пересечение множеств =====
            if service_sets:
                intersection = set.intersection(*service_sets)
                logger.info(f"Пересечение всех множеств: {len(intersection)} услуг - {intersection}")

                # Если есть однозначное пересечение (1 услуга)
                if len(intersection) == 1:
                    service_id = list(intersection)[0]
                    service_data = service_results_map[service_id]

                    logger.info(f"ОДНОЗНАЧНОЕ ПЕРЕСЕЧЕНИЕ: service_id={service_id}, источники: {service_data['sources']}")

                    result = {
                        'status': 'SUCCESS',
                        'service_id': service_id,
                        'service_name': service_data['service_name'],
                        'confidence': 1.0,  # Пересечение = 100%
                        'source': '+'.join(service_data['sources']),
                        'message': f'Правильно ли я понял, что у вас проблема: {service_data["service_name"]}?',
                        'candidates': [service_data['all_data'][0]],
                        'needs_confirmation': True,
                        'is_followup': is_followup
                    }
                    # ДОБАВЛЕНО: Добавляем адресные компоненты
                    return self._add_address_to_result(result, address_components)

                # Если пересечение из 2+ услуг - нужно уточнить
                elif len(intersection) > 1:
                    logger.info(f"МНОЖЕСТВЕННОЕ ПЕРЕСЕЧЕНИЕ: {len(intersection)} услуг")
                    candidates_data = [service_results_map[sid] for sid in intersection]
                    return await self._create_ambiguous_result_from_intersection(candidates_data, original_message, is_followup, dialog_history)

            # ===== ТЗ 3.2.2: Нет пересечения или множества не пересекаются =====
            logger.info("НЕТ ОБЩЕГО ПЕРЕСЕЧЕНИЯ, формируем таблицу кандидатов")

            # Собираем всех кандидатов из всех сервисов (дедуплицированно)
            all_service_ids = set()
            for s in service_sets:
                all_service_ids.update(s)

            logger.info(f"Всего уникальных кандидатов: {len(all_service_ids)}")

            if not all_service_ids:
                # Нет кандидатов совсем - пробуем AI
                if self.ai_agent:
                    logger.info("Нет кандидатов от быстрых сервисов, запускаем AI")
                    ai_result = await self._run_ai_search(search_text)
                    if ai_result and ai_result.get('candidates'):
                        ai_candidates = ai_result['candidates']
                        if len(ai_candidates) == 1:
                            result = {
                                'status': 'SUCCESS',
                                'service_id': ai_candidates[0]['service_id'],
                                'service_name': ai_candidates[0]['service_name'],
                                'confidence': ai_candidates[0].get('confidence', 0.8),
                                'source': 'ai_agent',
                                'message': f'Правильно ли я понял, что у вас проблема: {ai_candidates[0]["service_name"]}?',
                                'candidates': ai_candidates,
                                'needs_confirmation': True
                            }
                            return self._add_address_to_result(result, address_components)

                # Fallback
                return await self._fallback_service_detection(message_text, address_components)

            # Есть кандидаты, но нет однозначного пересечения
            candidates_data = [service_results_map[sid] for sid in all_service_ids]

            # ИСПРАВЛЕНО: FilterDetectionService запускается даже когда 0 кандидатов!
            # Логика: если традиционный поиск не сработал - используем LLM для определения фильтров
            if self.filter_detection:
                # Запускаем FilterDetectionService если:
                # 1. Несколько кандидатов (>1) - нужно отфильтровать до одного
                # 2. НЕТ кандидатов (0) - нужно искать по фильтрам от LLM во ВСЕХ услугах
                should_run = len(candidates_data) > 1 or len(candidates_data) == 0
                logger.info(f"FilterDetectionService проверка: кандидатов={len(candidates_data)}, запуск={should_run}")

                if should_run:
                    logger.info(f"Запускаем FilterDetectionService (кандидатов: {len(candidates_data)})")

                    # Вызываем FilterDetectionService
                    filter_result = await self.filter_detection.detect_filters(original_message, dialog_history)

                    if filter_result.get('status') == 'success':
                        filters = filter_result.get('filters', {})
                        logger.info(f"FilterDetectionService вернул фильтры: {filters}")

                        # ИСПРАВЛЕНО: Если 0 кандидатов - ищем ВСЕ услуги по фильтрам от LLM
                        if len(candidates_data) == 0:
                            logger.info("Кандидатов нет, ищем ВСЕ услуги по фильтрам от LLM")
                            candidates_with_attrs = await self._load_all_services_by_filters(filters)
                            logger.info(f"Найдено услуг по фильтрам LLM: {len(candidates_with_attrs)}")
                        else:
                            # Загружаем атрибуты существующих кандидатов для фильтрации
                            candidates_with_attrs = await self._load_candidates_attributes(candidates_data)

                        # Фильтруем кандидатов по полученным фильтрам
                        filtered = candidates_with_attrs

                        if filters.get('incident_type'):
                            filtered = [c for c in filtered
                                       if filters['incident_type'] in c.get('incident_type', '')]
                            logger.info(f"Отфильтровано по incident_type={filters['incident_type']}: {len(filtered)} из {len(candidates_with_attrs)}")

                        if filters.get('location_type'):
                            filtered = [c for c in filtered
                                       if filters['location_type'] in c.get('location_type', '')]
                            logger.info(f"Отфильтровано по location_type={filters['location_type']}: {len(filtered)} из {len(candidates_with_attrs)}")

                        if filters.get('category'):
                            filtered = [c for c in filtered
                                       if filters['category'].lower() in c.get('category', '').lower()]
                            logger.info(f"Отфильтровано по category={filters['category']}: {len(filtered)} из {len(candidates_with_attrs)}")

                        # Если после фильтрации остался 1 кандидат - SUCCESS
                        if len(filtered) == 1:
                            candidate = filtered[0]
                            result = {
                                'status': 'SUCCESS',
                                'service_id': candidate['service_id'],
                                'service_name': candidate.get('service_name', candidate.get('scenario_name', 'Unknown')),
                                'confidence': filter_result.get('confidence', 0.8),
                                'source': 'filter_detection',
                                'message': f"Понял, у вас: {candidate.get('service_name', candidate.get('scenario_name'))}. Это правильно?",
                                'candidates': [candidate],
                                'needs_confirmation': True,
                                'is_followup': is_followup
                            }
                            return self._add_address_to_result(result, address_components)

                        # Если кандидаты отфильтровались до 0 - используем оригинальный список
                        if not filtered:
                            logger.info("FilterDetectionService отфильтровал всех кандидатов, используем оригинальный список")
                            filtered = candidates_with_attrs if candidates_with_attrs else candidates_data

                        # Передаем отфильтрованных кандидатов в AMBIGUOUS
                        candidates_data = filtered

            return await self._create_ambiguous_result_from_candidates(candidates_data, original_message, is_followup, dialog_history)

        except Exception as e:
            # Детальное логирование критических ошибок
            error_trace = traceback.format_exc()
            logger.error(f"КРИТИЧЕСКАЯ ОШИБКА в process_service_detection: {type(e).__name__}: {e}")
            logger.error(f"Сообщение: '{message_text}'")
            logger.error(f"Контекст: {user_context}")
            logger.error(f"Трассировка:\n{error_trace}")

            # Возвращаем безопасный результат
            return {
                'status': 'ERROR',
                'error': 'Системная ошибка обработки',
                'message': 'Произошла техническая ошибка. Пожалуйста, опишите проблему другими словами.\n\n'
                         'Если проблема повторяется, напишите: "связь с диспетчером"',
                'candidates': []
            }

    def _should_run_ai_agent(self, service_results: List[Dict], search_text: str, candidates: List[Dict]) -> Optional[str]:
        """
        Анализ необходимости запуска AI агента

        AI запускается ТОЛЬКО если:
        1. Нет результатов от быстрых сервисов
        2. Сильное расхождение между сервисами
        3. Низкая уверенность у всех кандидатов

        Args:
            service_results: Результаты от быстрых сервисов
            search_text: Исходный текст поиска
            candidates: Все найденные кандидаты

        Returns:
            Optional[str]: Причина запуска AI или None
        """
        # Причина 1: Нет результатов от быстрых сервисов
        if not service_results or not candidates:
            return "no_results_from_fast_services"

        # Причина 2: Низкая уверенность у лучшего кандидата
        if candidates:
            best_confidence = max(c.get('confidence', 0) for c in candidates)
            if best_confidence < 0.40:
                return f"low_confidence_{best_confidence:.2f}"

        # Причина 3: Сильное расхождение между сервисами
        if len(service_results) >= 2:
            # Анализируем пересечения результатов
            service_sets = []
            for result in service_results:
                service_ids = {candidate['service_id'] for candidate in result.get('candidates', [])}
                service_sets.append(service_ids)

            # Если 2+ сервиса не имеют пересечений
            if len(service_sets) >= 2:
                intersection = set.intersection(*service_sets)
                union = set.union(*service_sets)

                # Нет пересечений и много разных кандидатов
                if len(intersection) == 0 and len(union) >= 3:
                    return f"no_intersection_{len(union)}_candidates"

                # Только 2 кандидата без пересечения
                if len(intersection) == 0 and len(union) == 2:
                    return "no_intersection_two_candidates"

        # AI не нужен
        return None

    async def _run_tag_search(self, message_text: str) -> Dict:
        """Запуск TagSearchService"""
        try:
            return await self.tag_search.search(message_text)
        except Exception as e:
            logger.error(f"Ошибка TagSearchService: {e}")
            return {}

    async def _run_semantic_search(self, message_text: str) -> Dict:
        """Запуск SemanticSearchService"""
        try:
            return await self.semantic_search.search(message_text)
        except Exception as e:
            logger.error(f"Ошибка SemanticSearchService: {e}")
            return {}

    async def _run_vector_search(self, message_text: str) -> Dict:
        """Запуск VectorSearchService"""
        try:
            return await self.vector_search.search(message_text)
        except Exception as e:
            logger.error(f"Ошибка VectorSearchService: {e}")
            return {}

    async def _create_ambiguous_result_from_intersection(self, candidates_data: List[Dict], original_message: str = "", is_followup: bool = False, dialog_history: List[Dict] = None) -> Dict:
        """
        Создание результата при множественном пересечении

        ИСПРАВЛЕНО: Сделано async для загрузки атрибутов из БД
        """
        candidate_names = [c['service_name'] for c in candidates_data]
        sources_info = ", ".join([f"{c['service_name']} ({'+'.join(c['sources'])})" for c in candidates_data])

        logger.info(f"Множественное пересечение: {sources_info}")

        # ИСПРАВЛЕНО: Загружаем атрибуты из БД вместо пустых значений
        candidates_with_attrs = await self._load_candidates_attributes(candidates_data)

        # Генерируем умный уточняющий вопрос с учетом истории
        clarification_result = self._generate_smart_clarification(candidates_with_attrs, original_message, is_followup, dialog_history)

        # ИСПРАВЛЕНО: Если после фильтрации остался 1 кандидат - возвращаем SUCCESS
        if clarification_result.get('status') == 'SUCCESS' and clarification_result.get('single_candidate'):
            candidate = clarification_result['single_candidate']
            return {
                'status': 'SUCCESS',
                'service_id': candidate['service_id'],
                'service_name': candidate.get('service_name', candidate.get('scenario_name', 'Unknown')),
                'confidence': 1.0,
                'source': 'filtered_search',
                'message': clarification_result['message'],
                'candidates': candidates_data[:1],
                'needs_confirmation': False,
                'is_followup': is_followup
            }

        # ИСПРАВЛЕНО (2025-12-25): Используем отфильтрованных кандидатов вместо всех
        filtered_candidates = clarification_result.get('filtered_candidates', candidates_with_attrs)

        return {
            'status': 'AMBIGUOUS',
            'candidates': filtered_candidates,  # ИСПРАВЛЕНО: отфильтрованные кандидаты
            'candidate_names': [c.get('service_name', c.get('scenario_name', 'Unknown')) for c in filtered_candidates],
            'message': clarification_result['message'],
            'needs_clarification': True,
            'clarification_type': 'intersection_multiple',
            'is_followup': is_followup
        }

    def _should_run_ai_agent(self, service_results: List[Dict], search_text: str, candidates: List[Dict]) -> Optional[str]:
        """
        Анализ необходимости запуска AI агента

        AI запускается ТОЛЬКО если:
        1. Нет результатов от быстрых сервисов
        2. Сильное расхождение между сервисами
        3. Низкая уверенность у всех кандидатов

        Args:
            service_results: Результаты от быстрых сервисов
            search_text: Исходный текст поиска
            candidates: Все найденные кандидаты

        Returns:
            Optional[str]: Причина запуска AI или None
        """
        # Причина 1: Нет результатов от быстрых сервисов
        if not service_results or not candidates:
            return "no_results_from_fast_services"

        # Причина 2: Низкая уверенность у лучшего кандидата
        if candidates:
            best_confidence = max(c.get('confidence', 0) for c in candidates)
            if best_confidence < 0.40:
                return f"low_confidence_{best_confidence:.2f}"

        # Причина 3: Сильное расхождение между сервисами
        if len(service_results) >= 2:
            # Анализируем пересечения результатов
            service_sets = []
            for result in service_results:
                service_ids = {candidate['service_id'] for candidate in result.get('candidates', [])}
                service_sets.append(service_ids)

            # Если 2+ сервиса не имеют пересечений
            if len(service_sets) >= 2:
                intersection = set.intersection(*service_sets)
                union = set.union(*service_sets)

                # Нет пересечений и много разных кандидатов
                if len(intersection) == 0 and len(union) >= 3:
                    return f"no_intersection_{len(union)}_candidates"

                # Только 2 кандидата без пересечения
                if len(intersection) == 0 and len(union) == 2:
                    return "no_intersection_two_candidates"

        # AI не нужен
        return None

    async def _create_ambiguous_result_from_candidates(self, candidates_data: List[Dict], original_message: str = "", is_followup: bool = False, dialog_history: List[Dict] = None) -> Dict:
        """
        Создание результата из таблицы кандидатов по ТЗ 3.2.2

        ИСПРАВЛЕНО: Сделано async для загрузки атрибутов из БД
        """
        # Сортируем по количеству источников (чем больше, тем выше приоритет)
        candidates_data.sort(key=lambda x: len(x['sources']), reverse=True)

        candidate_names = [c['service_name'] for c in candidates_data[:5]]

        logger.info(f"Формируем запрос уточнения из {len(candidates_data)} кандидатов")

        # ИСПРАВЛЕНО: Загружаем атрибуты из БД вместо пустых значений
        candidates_with_attrs = await self._load_candidates_attributes(candidates_data[:5])

        # Генерируем умный уточняющий вопрос с учетом истории
        clarification_result = self._generate_smart_clarification(candidates_with_attrs, original_message, is_followup, dialog_history)

        # ИСПРАВЛЕНО: Если после фильтрации остался 1 кандидат - возвращаем SUCCESS
        if clarification_result.get('status') == 'SUCCESS' and clarification_result.get('single_candidate'):
            candidate = clarification_result['single_candidate']
            return {
                'status': 'SUCCESS',
                'service_id': candidate['service_id'],
                'service_name': candidate.get('service_name', candidate.get('scenario_name', 'Unknown')),
                'confidence': 1.0,
                'source': 'filtered_search',
                'message': clarification_result['message'],
                'candidates': candidates_data[:1],
                'needs_confirmation': False,
                'is_followup': is_followup
            }

        # ИСПРАВЛЕНО (2025-12-25): Используем отфильтрованных кандидатов
        filtered_candidates = clarification_result.get('filtered_candidates', candidates_with_attrs)

        return {
            'status': 'AMBIGUOUS',
            'candidates': filtered_candidates,  # ИСПРАВЛЕНО: отфильтрованные кандидаты
            'candidate_names': [c.get('service_name', c.get('scenario_name', 'Unknown')) for c in filtered_candidates],
            'message': clarification_result['message'],
            'needs_clarification': True,
            'clarification_type': 'no_intersection',
            'is_followup': is_followup
        }

    async def _load_candidates_attributes(self, candidates_data: List[Dict]) -> List[Dict]:
        """
        Загружает атрибуты услуг (incident_type, category, location_type) из БД
        для умного анализа различий между кандидатами

        ИСПРАВЛЕНО: Сделано async для корректной работы в async контексте
        """
        if not candidates_data:
            return []

        try:
            def load_sync():
                service_ids = [c['service_id'] for c in candidates_data]

                with connection.cursor() as cursor:
                    # Используем денормализованные колонки
                    cursor.execute("""
                        SELECT service_id, scenario_name, incident_type, category, location_type
                        FROM services_catalog
                        WHERE service_id IN %s
                    """, [tuple(service_ids)])

                    attrs_map = {}
                    for row in cursor.fetchall():
                        attrs_map[row[0]] = {
                            'service_id': row[0],
                            'scenario_name': row[1],
                            'incident_type': row[2] or '',
                            'category': row[3] or '',
                            'location_type': row[4] or ''
                        }

                return attrs_map

            attrs_map = await sync_to_async(load_sync)()

            # Обогащаем данные кандидатов атрибутами
            enriched = []
            for candidate in candidates_data:
                service_id = candidate['service_id']
                attrs = attrs_map.get(service_id, {})
                enriched.append({
                    **candidate,
                    'incident_type': attrs.get('incident_type', ''),
                    'category': attrs.get('category', ''),
                    'location_type': attrs.get('location_type', '')
                })

            logger.info(f"Загружены атрибуты для {len(enriched)} кандидатов")
            return enriched

        except Exception as e:
            logger.error(f"Ошибка загрузки атрибутов кандидатов: {e}")
            return candidates_data

    async def _load_all_services_by_filters(self, filters: Dict) -> List[Dict]:
        """
        Ищет ВСЕ услуги в БД по фильтрам от FilterDetectionService

        Используется когда традиционный поиск вернул 0 кандидатов,
        но LLM определил фильтры (incident_type, location_type, category)

        Args:
            filters: Словарь с фильтрами от LLM
                {
                    'incident_type': 'Инцидент' or 'Запрос',
                    'location_type': 'Индивидуальное' or 'Общедомовое',
                    'category': 'Водоснабжение' or ...
                }

        Returns:
            List[Dict]: Список кандидатов с атрибутами
        """
        try:
            def load_sync():
                with connection.cursor() as cursor:
                    # Строим SQL запрос с фильтрами
                    sql = "SELECT service_id, scenario_name, incident_type, category, location_type FROM services_catalog WHERE is_active = TRUE"
                    params = []

                    # Добавляем фильтры если они есть
                    if filters.get('incident_type'):
                        sql += " AND incident_type = %s"
                        params.append(filters['incident_type'])

                    if filters.get('location_type'):
                        sql += " AND location_type = %s"
                        params.append(filters['location_type'])

                    if filters.get('category'):
                        # Частичное совпадение для категории
                        sql += " AND category ILIKE %s"
                        params.append(f"%{filters['category']}%")

                    sql += " ORDER BY scenario_name"
                    logger.info(f"SQL для поиска по фильтрам: {sql} с параметрами {params}")

                    cursor.execute(sql, params)
                    results = cursor.fetchall()

                # Конвертируем в формат кандидатов
                candidates = []
                for row in results:
                    candidates.append({
                        'service_id': row[0],
                        'service_name': row[1],
                        'incident_type': row[2] or '',
                        'category': row[3] or '',
                        'location_type': row[4] or '',
                        'confidence': 0.7,  # Базовая уверенность для найденных по фильтрам
                        'sources': ['filter_detection'],
                        'source': 'filter_detection'
                    })

                return candidates

            candidates = await sync_to_async(load_sync)()
            logger.info(f"Найдено {len(candidates)} услуг по фильтрам: {filters}")
            return candidates

        except Exception as e:
            logger.error(f"Ошибка поиска услуг по фильтрам: {e}")
            return []

    def _extract_filters_from_message(self, message_text: str, dialog_history: List[Dict] = None) -> Dict:
        """
        Извлекает фильтры (location, category, incident, object_description) из текста сообщения и истории диалога

        ИСПРАВЛЕНО (2025-12-25): Добавлен вызов FilterDetectionService для object_description

        Args:
            message_text: Текст сообщения пользователя
            dialog_history: История диалога

        Returns:
            Dict: {
                'location': 'Индивидуальное' | 'Общедомовое' | None,
                'category': 'Водоснабжение' | ... | None,
                'incident': 'Инцидент' | 'Запрос' | None,
                'object_description': 'описание объекта' | None
            }
        """
        filters = {
            'location': None,
            'category': None,
            'incident': None,
            'object_description': None  # ИСПРАВЛЕНО (2025-12-25)
        }

        # ИСПРАВЛЕНО (2025-12-25): Сначала пробуем FilterDetectionService для object_description
        if self.filter_detection:
            try:
                # ИСПРАВЛЕНО: Используем await вместо asyncio.run()
                # Но это не async функция, поэтому сохраняем как есть и вызываем через sync wrapper
                def call_filter_sync():
                    import asyncio
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Если уже в event loop - создаем задачу
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            future = pool.submit(asyncio.run, self.filter_detection.detect_filters(message_text, dialog_history or []))
                            return future.result()
                    else:
                        return asyncio.run(self.filter_detection.detect_filters(message_text, dialog_history or []))

                filter_result = call_filter_sync()
                if filter_result.get('status') == 'success':
                    filter_svc_filters = filter_result.get('filters', {})
                    # Если FilterDetectionService вернул значения - используем их
                    if filter_svc_filters.get('location_type'):
                        filters['location'] = filter_svc_filters['location_type']
                    if filter_svc_filters.get('category'):
                        filters['category'] = filter_svc_filters['category']
                    if filter_svc_filters.get('incident_type'):
                        filters['incident'] = filter_svc_filters['incident_type']
                    if filter_svc_filters.get('object_description'):
                        filters['object_description'] = filter_svc_filters['object_description']
                        logger.info(f"FilterDetectionService извлек object_description: {filters['object_description']}")
            except Exception as e:
                logger.warning(f"Ошибка вызова FilterDetectionService: {e}")

        # УДАЛЕНО (2025-12-25): Весь fallback хардкод keywords удален
        # FilterDetectionService теперь является единственным источником фильтров
        # Это соответствует архитектуре без хардкода данных

        return filters

    def _generate_smart_clarification(self, candidates_with_attrs: List[Dict], original_message: str = "", is_followup: bool = False, dialog_history: List[Dict] = None) -> Dict:
        """
        Генерирует умный уточняющий вопрос на основе анализа атрибутов кандидатов

        Логика: находит ключевые различия в атрибутах (location_type, category, incident_type)
        и задает вопрос именно по этим параметрам, НЕ перечисляя услуги

        ИСПРАВЛЕНО: Добавлен анализ истории диалога для исключения уже отвеченных вопросов
        ИСПРАВЛЕНО: Возвращает Dict с status вместо строки
        ИСПРАВЛЕНО (2025-12-25): Возвращает filtered_candidates для итеративного уточнения
        """
        if not candidates_with_attrs:
            return {
                'status': 'AMBIGUOUS',
                'message': self._generate_clarification_questions(),
                'single_candidate': None,
                'filtered_candidates': []
            }

        # ИЗВЛЕКАЕМ ФИЛЬТРЫ ИЗ СООБЩЕНИЯ ПОЛЬЗОВАТЕЛЯ И ИСТОРИИ ДИАЛОГА
        extracted_filters = self._extract_filters_from_message(original_message, dialog_history)
        known_location = extracted_filters['location']
        known_category = extracted_filters['category']
        known_incident = extracted_filters['incident']
        known_object = extracted_filters.get('object_description', '')  # ИСПРАВЛЕНО (2025-12-25)

        logger.info(f"Извлеченные фильтры: location={known_location}, category={known_category}, incident={known_incident}, object={known_object}")

        # Фильтруем кандидатов на основе известной информации
        filtered_candidates = candidates_with_attrs
        if known_location:
            filtered_candidates = [c for c in filtered_candidates if known_location in c.get('location_type', '')]
            logger.info(f"Отфильтровано по location_type={known_location}: {len(filtered_candidates)} из {len(candidates_with_attrs)}")

        if known_category:
            # Прямое совпадение категории (FilterDetectionService уже возвращает корректную категорию)
            filtered_candidates = [c for c in filtered_candidates if known_category.lower() in c.get('category', '').lower()]
            logger.info(f"Отфильтровано по category={known_category}: {len(filtered_candidates)} из {len(candidates_with_attrs)}")

        if known_incident:
            # Фильтрация по типу инцидента
            filtered_candidates = [c for c in filtered_candidates if known_incident in c.get('incident_type', '')]
            logger.info(f"Отфильтровано по incident_type={known_incident}: {len(filtered_candidates)} из {len(candidates_with_attrs)}")

        # ИСПРАВЛЕНО (2025-12-25): Ранжирование через LLM вместо хардкода keywords
        if known_object and len(filtered_candidates) > 1:
            logger.info(f"Ранжирование {len(filtered_candidates)} кандидатов по object_description='{known_object}' через LLM")

            if self.filter_detection:
                try:
                    # Используем ThreadPoolExecutor для вызова async из sync контекста
                    def call_ranking_sync():
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            import concurrent.futures
                            with concurrent.futures.ThreadPoolExecutor() as pool:
                                future = pool.submit(
                                    asyncio.run,
                                    self.filter_detection.rank_candidates_by_relevance(
                                        message_text=original_message,
                                        candidates=filtered_candidates,
                                        dialog_history=dialog_history
                                    )
                                )
                                return future.result()
                        return asyncio.run(
                            self.filter_detection.rank_candidates_by_relevance(
                                message_text=original_message,
                                candidates=filtered_candidates,
                                dialog_history=dialog_history
                            )
                        )

                    ranking_result = call_ranking_sync()

                    if ranking_result.get('status') == 'success':
                        recommended_id = ranking_result.get('recommended_id')
                        confidence = ranking_result.get('confidence', 0.0)
                        reason = ranking_result.get('reason', '')

                        # Находим рекомендованного кандидата
                        recommended_candidate = None
                        for c in filtered_candidates:
                            if c.get('service_id') == recommended_id:
                                recommended_candidate = c
                                break

                        if recommended_candidate:
                            logger.info(
                                f"LLM рекомендовал: {recommended_candidate['service_name']} "
                                f"(ID: {recommended_id}, confidence: {confidence})"
                            )

                            # Если confidence > 0.7, выбираем этого кандидата
                            if confidence >= 0.7:
                                logger.info(f"По LLM ранжированию выбран кандидат: {recommended_candidate['service_name']}")
                                filtered_candidates = [recommended_candidate]
                            else:
                                logger.info(f"LLM confidence слишком низкий ({confidence}), оставляем всех кандидатов")
                        else:
                            logger.warning(f"LLM вернул невалидный recommended_id={recommended_id}")
                    else:
                        logger.warning(f"LLM ранжирование не удалось: {ranking_result.get('error')}")

                except Exception as e:
                    logger.error(f"Ошибка вызова LLM ранжирования: {e}")
            else:
                logger.warning("FilterDetectionService недоступен, пропускаем ранжирование")

        # Если после фильтрации остался 1 кандидат - возвращаем SUCCESS
        if len(filtered_candidates) == 1:
            # Услуга определена после фильтрации!
            candidate = filtered_candidates[0]
            logger.info(f"После фильтрации остался 1 кандидат: {candidate['service_name']} (ID: {candidate['service_id']})")
            return {
                'status': 'SUCCESS',
                'message': f"Понял, у вас: {candidate['service_name']}",
                'single_candidate': candidate,
                'filtered_candidates': filtered_candidates
            }

        # ИСПРАВЛЕНО: Если осталось несколько кандидатов с одинаковыми атрибутами - пробуем уточнить по keywords
        if len(filtered_candidates) > 1:
            # Проверяем все ли кандидаты имеют одинаковые location, category, incident
            locations = set(c.get('location_type') for c in filtered_candidates if c.get('location_type'))
            categories = set(c.get('category') for c in filtered_candidates if c.get('category'))
            incidents = set(c.get('incident_type') for c in filtered_candidates if c.get('incident_type'))

            if len(locations) == 1 and len(categories) == 1 and len(incidents) == 1:
                # Все кандидаты имеют одинаковые атрибуты - уточняем по описанию
                names = [c.get('service_name', c.get('scenario_name', 'Unknown')) for c in filtered_candidates]
                logger.info(f"Кандидаты имеют одинаковые атрибуты, уточняем: {names}")

                # Генерируем вопрос на основе названий
                if len(names) <= 3:
                    return {
                        'status': 'AMBIGUOUS',
                        'message': f"Уточните, пожалуйста, что именно произошло:\n• " + "\n• ".join(names),
                        'single_candidate': None,
                        'filtered_candidates': filtered_candidates
                    }

                # Если кандидатов много - возвращаем общий вопрос
                return {
                    'status': 'AMBIGUOUS',
                    'message': f"Уточните, пожалуйста, детали проблемы (выберите один из вариантов ниже)",
                    'single_candidate': None,
                    'filtered_candidates': filtered_candidates
                }

        # Если осталось 0 кандидатов после фильтрации - используем оригинальный список
        if not filtered_candidates:
            logger.warning("После фильтрации не осталось кандидатов, используем полный список")
            filtered_candidates = candidates_with_attrs

        # Анализируем уникальные значения по каждому измерению на основе отфильтрованных кандидатов
        location_types = set()
        categories = set()
        incident_types = set()

        for c in filtered_candidates:
            if c.get('location_type'):
                location_types.add(c['location_type'])
            if c.get('category'):
                categories.add(c['category'])
            if c.get('incident_type'):
                incident_types.add(c['incident_type'])

        logger.info(f"Анализ кандидатов: locations={location_types}, categories={categories}, incidents={incident_types}")

        # ===== ПРИОРИТЕТ 1: Локализация (квартира vs общедомовое) =====
        # Если локация уже известна - пропускаем этот вопрос
        if not known_location and len(location_types) >= 2:
            # Проверяем есть ли оба основных типа локации
            has_individual = any('индивид' in loc.lower() or 'квартир' in loc.lower() for loc in location_types)
            has_common = any('общедом' in loc.lower() or 'общее' in loc.lower() for loc in location_types)

            if has_individual and has_common:
                return {
                    'status': 'AMBIGUOUS',
                    'message': "Где именно это произошло: в квартире у вас или на территории общедомового имущества?",
                    'single_candidate': None,
                    'filtered_candidates': filtered_candidates
                }

            # Иначе перечисляем найденные локации
            loc_list = list(location_types)
            if len(loc_list) == 2:
                return {
                    'status': 'AMBIGUOUS',
                    'message': f"Уточните, пожалуйста: это произошло {loc_list[0].lower()} или {loc_list[1].lower()}?",
                    'single_candidate': None,
                    'filtered_candidates': filtered_candidates
                }
            else:
                return {
                    'status': 'AMBIGUOUS',
                    'message': "Где именно это произошло?\n• " + "\n• ".join(loc_list) + "\n\nПожалуйста, уточните.",
                    'single_candidate': None,
                    'filtered_candidates': filtered_candidates
                }

        # ===== ПРИОРИТЕТ 2: Тип инцидента (Инцидент vs Запрос) =====
        if len(incident_types) >= 2:
            has_incident = any('инцид' in inc.lower() for inc in incident_types)
            has_request = any('запрос' in inc.lower() or 'заявк' in inc.lower() for inc in incident_types)

            if has_incident and has_request:
                return {
                    'status': 'AMBIGUOUS',
                    'message': "Уточните, пожалуйста: у вас аварийная ситуация (поломка, течь и т.п.) или вам нужна информация/услуга?",
                    'single_candidate': None,
                    'filtered_candidates': filtered_candidates
                }

        # ===== ПРИОРИТЕТ 3: Категория проблемы =====
        # Если категория уже известна - пропускаем этот вопрос
        if not known_category and len(categories) >= 2:
            # Анализируем категории для умного вопроса
            has_water = any('вод' in cat.lower() or 'сантехник' in cat.lower() or 'канализ' in cat.lower() for cat in categories)
            has_heating = any('отопл' in cat.lower() for cat in categories)
            has_electric = any('электр' in cat.lower() for cat in categories)
            has_construct = any('конструк' in cat.lower() for cat in categories)
            has_lift = any('лифт' in cat.lower() for cat in categories)

            # Специфичные вопросы по парам категорий
            if has_water and has_heating:
                return {
                    'status': 'AMBIGUOUS',
                    'message': "Это проблема с водой (течь, засор) или с отоплением?",
                    'single_candidate': None,
                    'filtered_candidates': filtered_candidates
                }

            if has_water and has_electric:
                return {
                    'status': 'AMBIGUOUS',
                    'message': "Проблема с водоснабжением или с электричеством?",
                    'single_candidate': None,
                    'filtered_candidates': filtered_candidates
                }

            if has_lift and (has_water or has_heating or has_electric):
                return {
                    'status': 'AMBIGUOUS',
                    'message': "Проблема с лифтом или с коммуникациями (вода, свет, отопление)?",
                    'single_candidate': None,
                    'filtered_candidates': filtered_candidates
                }

            if has_construct and has_water:
                return {
                    'status': 'AMBIGUOUS',
                    'message': "Это проблема с конструкцией (крыша, стены) или с сантехникой?",
                    'single_candidate': None,
                    'filtered_candidates': filtered_candidates
                }

            # Если много категорий - спрашиваем что именно
            if len(categories) <= 4:
                return {
                    'status': 'AMBIGUOUS',
                    'message': "Уточните, пожалуйста, о какой проблеме речь:\n• " + "\n• ".join(categories) + "\n\nОпишите подробнее.",
                    'single_candidate': None,
                    'filtered_candidates': filtered_candidates
                }

        # ===== ФОЛЛБЕК: Анализ исходного сообщения =====
        if original_message:
            # Ищем контекст в исходном сообщении
            original_lower = original_message.lower()

            # ИСПРАВЛЕНО: Генерируем простые открытые вопросы, НЕ перечисляем варианты
            # Если говорится о течи - спрашиваем где (открытый вопрос)
            if any(word in original_lower for word in ['теч', 'течет', 'протека', 'капа', 'утечк', 'льет']):
                return {
                    'status': 'AMBIGUOUS',
                    'message': "Где именно это произошло? Пожалуйста, опишите подробнее.",
                    'single_candidate': None,
                    'filtered_candidates': filtered_candidates
                }

            # Если говорится о поломке - спрашиваем что
            if any(word in original_lower for word in ['сломал', 'не работ', 'поломк']):
                return {
                    'status': 'AMBIGUOUS',
                    'message': "Что именно сломалось? Опишите, пожалуйста, подробнее.",
                    'single_candidate': None,
                    'filtered_candidates': filtered_candidates
                }

        # ===== ОБЩИЙ ВОПРОС (открытый, без перечисления вариантов) =====
        return {
            'status': 'AMBIGUOUS',
            'message': "Пожалуйста, уточните где именно это произошло и опишите подробнее, что случилось.",
            'single_candidate': None,
                    'filtered_candidates': filtered_candidates
                }

    async def _run_ai_search(self, message_text: str) -> Dict:
        """Запуск AIAgentService"""
        try:
            return await self.ai_agent.search(message_text)
        except Exception as e:
            logger.error(f"Ошибка AIAgentService: {e}")
            return {}

    def _merge_candidates(self, candidates: List[Dict]) -> List[Dict]:
        """Дедупликация и объединение кандидатов"""
        service_map = {}

        for candidate in candidates:
            service_id = candidate.get('service_id')
            if service_id in service_map:
                # Если услуга уже есть, повышаем уверенность
                existing = service_map[service_id]
                existing_confidence = existing.get('confidence', 0)
                candidate_confidence = candidate.get('confidence', 0)

                if candidate_confidence > existing_confidence:
                    existing['confidence'] = candidate_confidence
                    existing['source'] = f"{existing.get('source', '')}+{candidate.get('source', '')}"
                else:
                    existing['source'] = f"{existing.get('source', '')}+{candidate.get('source', '')}"
                    existing['confidence'] = min(existing_confidence + 0.1, 1.0)
            else:
                service_map[service_id] = candidate.copy()

        merged = list(service_map.values())

        # Сортируем по уверенности убыванию
        merged.sort(key=lambda x: x.get('confidence', 0), reverse=True)

        logger.info(f"Дедуплицировано кандидатов: {len(merged)}")
        return merged

    async def _analyze_intersections(self, candidates: List[Dict], original_message: str = "", is_followup: bool = False) -> Dict:
        """
        Анализ пересечений результатов от разных микросервисов

        ИСПРАВЛЕНО: Сделано async для вызова _create_ambiguous_result
        """
        if len(candidates) == 1:
            # Однозначный результат
            candidate = candidates[0]
            confidence = candidate.get('confidence', 0)

            # Если это уточняющий вопрос и высокая уверенность - не требуем подтверждения
            needs_confirmation = confidence < 0.85 and not is_followup

            # Формируем сообщение с учетом контекста
            if is_followup:
                message = f'Отлично! Теперь понятно. У вас проблема: {candidate.get("service_name", "Unknown")}'
            else:
                message = f'Я определил, что у вас проблема: {candidate.get("service_name", "Unknown")}'

            return {
                'status': 'SUCCESS',
                'service_id': candidate.get('service_id'),
                'service_name': candidate.get('service_name', 'Unknown'),
                'confidence': confidence,
                'source': candidate.get('source', 'unknown'),
                'message': message,
                'candidates': candidates,
                'needs_confirmation': needs_confirmation,
                'is_followup': is_followup
            }
        elif len(candidates) >= 2:
            # Несколько кандидатов - уточняем
            return await self._create_ambiguous_result(candidates, original_message, is_followup)
        else:
            # Нет кандидатов
            return self._create_error_result("Не удалось определить услугу")

    async def _create_ambiguous_result(self, candidates: List[Dict], original_message: str = "", is_followup: bool = False, dialog_history: List[Dict] = None) -> Dict:
        """
        Создание результата с неопределенностью

        ИСПРАВЛЕНО: Сделано async для загрузки атрибутов из БД
        """
        if not candidates:
            # Нет кандидатов - задаем умные уточняющие вопросы
            clarification_message = self._generate_clarification_questions()
            return {
                'status': 'AMBIGUOUS',
                'candidates': [],
                'candidate_names': [],
                'message': clarification_message,
                'needs_clarification': True,
                'clarification_type': 'questions'
            }

        # ИСПРАВЛЕНО: Загружаем атрибуты из БД вместо пустых значений
        candidates_with_attrs = await self._load_candidates_attributes(candidates[:3])

        clarification_result = self._generate_smart_clarification(candidates_with_attrs, original_message, is_followup, dialog_history)

        # ИСПРАВЛЕНО: Если после фильтрации остался 1 кандидат - возвращаем SUCCESS
        if clarification_result.get('status') == 'SUCCESS' and clarification_result.get('single_candidate'):
            candidate = clarification_result['single_candidate']
            return {
                'status': 'SUCCESS',
                'service_id': candidate['service_id'],
                'service_name': candidate.get('service_name', candidate.get('scenario_name', 'Unknown')),
                'confidence': 1.0,
                'source': 'filtered_search',
                'message': clarification_result['message'],
                'candidates': candidates[:1],
                'needs_confirmation': False,
                'is_followup': is_followup
            }

        # ИСПРАВЛЕНО (2025-12-25): Используем отфильтрованных кандидатов
        filtered_candidates = clarification_result.get('filtered_candidates', candidates_with_attrs)

        return {
            'status': 'AMBIGUOUS',
            'candidates': filtered_candidates,  # ИСПРАВЛЕНО: отфильтрованные кандидаты
            'candidate_names': [c.get('service_name', c.get('scenario_name', 'Unknown')) for c in filtered_candidates],
            'message': clarification_result['message'],
            'needs_clarification': True,
            'clarification_type': 'context',
            'is_followup': is_followup
        }

    def _generate_clarification_questions(self) -> str:
        """
        Генерирует умные уточняющие вопросы

        ИСПРАВЛЕНО: Использует открытые вопросы без цифр и нумерации
        """
        return """Я не совсем понял проблему. Опишите пожалуйста, что именно случилось и где это произошло."""

    def _generate_context_clarification_question(self, candidates: List[Dict], original_message: str = "", is_followup: bool = False) -> str:
        """
        Генерирует уточняющий вопрос для понимания контекста

        ИСПРАВЛЕНО (2025-12-25): Удален хардкод keywords
        Теперь используется общий вопрос без классификации
        """
        # УДАЛЕНО: Весь хардкод keywords для локаций и инцидентов
        # FilterDetectionService и LLM должны определять фильтры

        # Общий уточняющий вопрос без хардкода
        return "Пожалуйста, уточните детали проблемы. Опишите что именно случилось и где это произошло."

    def _create_error_result(self, error_message: str) -> Dict:
        return {
            'status': 'ERROR',
            'error': error_message,
            'message': f'Произошла техническая ошибка: {error_message}',
            'candidates': []
        }

    async def _fallback_service_detection(self, message_text: str, address_components: Dict = None) -> Dict:
        """
        Запасной метод определения услуг по ключевым словам

        ИСПРАВЛЕНО: Сделано async для вызова _create_ambiguous_result
        ДОБАВЛЕНО: Принимает address_components для добавления к результату
        """
        try:
            # Улучшенные ключевые слова для проблем с водой
            water_keywords = ['теч', 'течет', 'протека', 'капа', 'утечк', 'льет', 'протек', 'затека', 'сырость', 'влага', 'капает', 'жидкость', 'сыро', 'мокро', 'протекает', 'течь']
            equipment_keywords = ['сломал', 'не работает', 'испортил', 'повредил', 'поломк', 'брак']
            heating_keywords = ['нет отопления', 'холодно', 'не греет', 'отопление не работает', 'батарея холодная']
            electricity_keywords = ['нет света', 'света нет', 'выключили свет', 'нет электричества', 'электричество']
            lift_keywords = ['лифт', 'лифта', 'лифтом', 'лифт не работает']

            message_lower = message_text.lower()

            if any(keyword in message_lower for keyword in water_keywords):
                # ИСПРАВЛЕНО: Возвращаем AMBIGUOUS вместо SUCCESS чтобы задать уточняющий вопрос
                return {
                    'status': 'AMBIGUOUS',
                    'candidates': [],
                    'candidate_names': [],
                    'message': 'Понял, у вас течь. Где именно это произошло? Пожалуйста, опишите подробнее.',
                    'needs_clarification': True,
                    'clarification_type': 'water'
                }
            elif any(keyword in message_lower for keyword in equipment_keywords):
                return {
                    'status': 'AMBIGUOUS',
                    'candidates': [],
                    'candidate_names': [],
                    'message': 'Понимаю, у вас поломка оборудования. Что именно сломалось и где это произошло? Опишите подробнее.',
                    'needs_clarification': True,
                    'clarification_type': 'equipment'
                }
            elif any(keyword in message_lower for keyword in heating_keywords):
                return {
                    'status': 'AMBIGUOUS',
                    'candidates': [],
                    'candidate_names': [],
                    'message': 'Похоже, проблема с отоплением. Где именно это произошло? Пожалуйста, уточните детали.',
                    'needs_clarification': True,
                    'clarification_type': 'heating'
                }
            elif any(keyword in message_lower for keyword in electricity_keywords):
                return {
                    'status': 'AMBIGUOUS',
                    'candidates': [],
                    'candidate_names': [],
                    'message': 'Похоже, проблема с электричеством. Где именно это произошло? Опишите подробнее ситуацию.',
                    'needs_clarification': True,
                    'clarification_type': 'electricity'
                }
            elif any(keyword in message_lower for keyword in lift_keywords):
                result = {
                    'status': 'SUCCESS',
                    'service_id': 42,
                    'service_name': 'Лифт не работает, двери застряли, люди внутри',
                    'confidence': 0.9,
                    'source': 'fallback_detection',
                    'message': 'Я определил, что у вас проблема: Лифт не работает',
                    'candidates': []
                }
                # ДОБАВЛЕНО: Добавляем адресные компоненты
                if address_components:
                    result = self._add_address_to_result(result, address_components)
                return result

            # Если не смогли определить проблему
            return await self._create_ambiguous_result([])

        except Exception as e:
            logger.error(f"Ошибка в fallback_service_detection: {e}")
            return await self._create_ambiguous_result([])

    def _get_service_name(self, service_id: int) -> str:
        """Получить название услуги по ID из services_catalog"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT scenario_name FROM services_catalog WHERE service_id = %s
                """, [service_id])
                result = cursor.fetchone()
                return result[0] if result else f"Услуга #{service_id}"
        except Exception as e:
            logger.error(f"Ошибка получения названия услуги {service_id}: {e}")
            return f"Услуга #{service_id}"

    def get_service_details(self, service_id: int) -> Optional[Dict]:
        """Получить детальную информацию об услуге из services_catalog"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT service_id, scenario_name, description_for_search, type_id, kind_id, category_id
                    FROM services_catalog WHERE service_id = %s
                """, [service_id])
                result = cursor.fetchone()

                if result:
                    return {
                        'service_id': result[0],
                        'scenario_name': result[1],
                        'description': result[2] or result[1],
                        'type_id': result[3],
                        'kind_id': result[4],
                        'category_id': result[5]
                    }
                return None
        except Exception as e:
            logger.error(f"Ошибка получения деталей услуги {service_id}: {e}")
            return None
