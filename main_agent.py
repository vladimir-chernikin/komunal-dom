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
        self.problem_accumulator = None  # ИСПРАВЛЕНО (2025-12-26): Сервис накопления проблемы
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

        # ИСПРАВЛЕНО (2025-12-26): ProblemAccumulationService для накопления описания проблемы
        try:
            from problem_accumulation_service import ProblemAccumulationService
            # Передаем ai_agent чтобы не дублировать вызовы LLM
            self.problem_accumulator = ProblemAccumulationService(ai_agent_service=self.ai_agent)
            logger.info("ProblemAccumulationService инициализирован (через AIAgentService)")
        except ImportError:
            logger.warning("ProblemAccumulationService не найден, накопление проблемы недоступно")

        # ИСПРАВЛЕНО (2025-12-26): CommunicativeScriptsService для управления фразами бота
        # ИСПРАВЛЕНО (2025-12-28): ОТКЛЮЧЕН - все вопросы теперь через AI (_generate_ai_question)
        # try:
        #     from communicative_scripts_service import CommunicativeScriptsService
        #     self.communicative_scripts = CommunicativeScriptsService()
        #     logger.info("CommunicativeScriptsService инициализирован")
        # except ImportError:
        #     logger.warning("CommunicativeScriptsService не найден, fallback скрипты недоступны")
        self.communicative_scripts = None
        logger.info("CommunicativeScriptsService ОТКЛЮЧЕН (используем AI-генерацию вопросов)")

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

        # ИСПРАВЛЕНО (2025-12-26): ProblemAccumulationService - накопление описания проблемы
        txtPrb = ""
        accumulated_fields = {}
        established_filters = {}

        if self.problem_accumulator and is_followup:
            try:
                # Извлекаем txtPrb из истории диалога
                txtPrb = self.problem_accumulator.get_txtPrb_from_metadata(dialog_history)
                logger.info(f"Текущий txtPrb из истории: '{txtPrb[:80] if txtPrb else '(пусто)'}...'")

                # Определяем последний вопрос бота
                last_bot_question = None
                if dialog_history:
                    for msg in reversed(dialog_history[-3:]):
                        if msg.get('role') == 'bot' and '?' in msg.get('text', ''):
                            last_bot_question = msg.get('text', '')
                            break

                # Накапливаем информацию из текущего сообщения
                accumulation_result = await self.problem_accumulator.extract_and_accumulate(
                    message_text=message_text,
                    current_problem=txtPrb,
                    bot_question=last_bot_question,
                    dialog_history=dialog_history
                )

                # ИСПРАВЛЕНО (2025-12-27): ВСЕГДА обновляем txtPrb, даже если is_meaningful=False
                # Короткие ответы типа "в квартире" важны для контекста!
                txtPrb = accumulation_result['updated_problem']
                accumulated_fields = accumulation_result['fields']

                if accumulation_result['is_meaningful']:
                    logger.info(f"txtPrb обновлен (содержательный): '{txtPrb[:100]}...'")
                    logger.info(f"Извлеченные поля: {accumulated_fields}")
                else:
                    logger.info(f"txtPrb обновлен (короткий ответ): '{txtPrb[:100]}...'")

                # Рассчитываем фильтры с весами
                established_filters = self.problem_accumulator.calculate_filter_confidence(
                    txtPrb, accumulated_fields
                )
                logger.info(f"Установленные фильтры: {established_filters}")

                # ИСПРАВЛЕНО (2025-12-27): Детект повторяющихся ответов пользователя
                # Если пользователь 2+ раза отвечает одно и то же - меняем стратегию
                if dialog_history and len(dialog_history) >= 4:
                    # Получаем последние 2-3 ответа пользователя
                    user_responses = []
                    for msg in reversed(dialog_history[-6:]):
                        # ИСПРАВЛЕНО: Используем 'role' вместо 'direction'
                        if msg.get('role') == 'user':
                            user_responses.append(msg.get('text', '').strip().lower())
                            if len(user_responses) >= 3:
                                break

                    # Проверяем есть ли повторения
                    if len(user_responses) >= 2 and user_responses[0] == user_responses[1]:
                        repeated_answer = user_responses[0]
                        logger.warning(f"⚠️ Обнаружен повторяющийся ответ: '{repeated_answer}' (2+ раза)")

                        # ИСПРАВЛЕНО (2025-12-27): ВСЕГДА меняем стратегию при повторяющихся ответах
                        # Не проверяем уверенность фильтров - если пользователь повторяет, значит нужно менять вопрос!

                        # Проверяем: сколько раз повторяется?
                        repeat_count = 1
                        for i in range(1, len(user_responses)):
                            if user_responses[i] == repeated_answer:
                                repeat_count += 1
                            else:
                                break

                        logger.info(f"⚠️ Ответ повторяется {repeat_count} раз")

                        # Меняем сообщение в зависимости от количества повторений
                        if repeat_count >= 3:
                            # 3+ повторения - просим описать проблему другими словами
                            message = 'Пожалуйста, опишите проблему другими словами. Что именно случилось?'
                        else:
                            # 2 повтора - задаем более конкретный вопрос
                            message = 'Уточните, пожалуйста: что именно произошло?'

                        logger.info("⚠️ Меняем стратегию: задаем другой вопрос")

                        # Возвращаем специальный результат
                        result_metadata = {
                            'txtPrb': txtPrb,
                            'accumulated_fields': accumulated_fields,
                            'established_filters': established_filters,
                            'repeated_answer_detected': True,
                            'repeat_count': repeat_count
                        }

                        return {
                            'status': 'AMBIGUOUS',
                            'candidates': [],
                            'candidate_names': [],
                            'message': message,
                            'needs_clarification': True,
                            'is_followup': is_followup,
                            '_metadata': result_metadata
                        }

            except Exception as e:
                logger.warning(f"Ошибка ProblemAccumulationService: {e}")

        # Подготавливаем metadata для результата
        result_metadata = {
            'txtPrb': txtPrb,
            'accumulated_fields': accumulated_fields,
            'established_filters': established_filters,
            # ДОБАВЛЕНО: Будем добавлять результаты микросервисов позже
            'microservices_results': {}  # {tag_search: {...}, vector_search: {...}, etc}
        }

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

            # ===== ИСПРАВЛЕНО (2025-12-25): AI ORCHESTRATOR вместо INTERSECTION =====
            # ИСПОЛЬЗУЕМ AI Orchestrator для умного объединения результатов

            # Формируем search_results для AI Orchestrator
            ai_search_results = {}

            for i, result in enumerate(search_results):
                if isinstance(result, Exception):
                    continue
                if not result or not result.get('candidates'):
                    continue

                source_name = result.get('method', f'service_{i}')
                ai_search_results[source_name] = result

            # ДОБАВЛЕНО: Сохраняем результаты микросервисов в metadata для отчета
            result_metadata['microservices_results'] = ai_search_results

            # Вызываем AI Orchestrator
            logger.info(f"Запускаем AI Orchestrator (микросервисов: {len(ai_search_results)})")

            # ИСПРАВЛЕНО (2025-12-27): Передаем ОБЪЕДИНЕННЫЙ КОНТЕКСТ + txtPrb + established_filters
            # Это критично для followup сообщений чтобы AI видел полный контекст разговора
            orch_result = await self._orchestrate_microservices(
                message_text=search_text,  # Объединенный контекст (previous + current)
                search_results=ai_search_results,
                dialog_history=dialog_history,
                txtPrb=txtPrb,  # Накопленное описание проблемы
                established_filters=established_filters  # Установленные фильтры
            )

            # ДОБАВЛЕНО: Сохраняем AI Orchestrator результат в metadata для отчета
            result_metadata['ai_orchestrator'] = {
                'status': orch_result.get('status', 'unknown'),
                'service_id': orch_result.get('service_id'),
                'service_name': orch_result.get('service_name'),
                'confidence': orch_result.get('confidence'),
                'message': orch_result.get('message'),
                'reasoning': orch_result.get('reasoning', ''),
                'candidates_count': len(orch_result.get('candidates', []))
            }

            # AI Orchestrator вернул решение
            if orch_result.get('status') == 'SUCCESS':
                # Услуга определена AI Orchestrator'ом
                logger.info(f"AI Orchestrator определил услугу: {orch_result.get('service_name')}")
                result = {
                    'status': 'SUCCESS',
                    'service_id': orch_result.get('service_id'),
                    'service_name': orch_result.get('service_name'),
                    'confidence': orch_result.get('confidence', 0.8),
                    'source': 'ai_orchestrator',
                    'message': orch_result.get('message'),
                    'candidates': orch_result.get('candidates', []),
                    'needs_confirmation': orch_result.get('needs_confirmation', True),
                    'is_followup': is_followup,
                    '_metadata': result_metadata  # ИСПРАВЛЕНО (2025-12-27): Добавляем metadata
                }
                return self._add_address_to_result(result, address_components)

            elif orch_result.get('status') == 'AMBIGUOUS':
                # AI Orchestrator требует уточнения
                logger.info(f"AI Orchestrator требует уточнения: {orch_result.get('message')}")
                return {
                    'status': 'AMBIGUOUS',
                    'candidates': orch_result.get('candidates', []),
                    'candidate_names': [c.get('service_name', 'Unknown') for c in orch_result.get('candidates', [])],
                    'message': orch_result.get('message'),
                    'needs_clarification': True,
                    'is_followup': is_followup,
                    '_metadata': result_metadata  # ИСПРАВЛЕНО (2025-12-27): Добавляем metadata
                }

            # Если AI Orchestrator не смог - пробуем старую логику
            logger.warning("AI Orchestrator не смог определить, используем fallback")

            # Собираем всех кандидатов из всех сервисов (дедуплицированно)
            all_service_ids = set()
            for s in service_sets:
                all_service_ids.update(s)

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
                                'needs_confirmation': True,
                                '_metadata': result_metadata  # ИСПРАВЛЕНО (2025-12-27): Добавляем metadata
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

                        # ДОБАВЛЕНО: Сохраняем FilterDetectionService результат с промтами в metadata
                        result_metadata['filter_detection'] = {
                            'status': 'success',
                            'filters': filters,
                            'confidence': filter_result.get('confidence', 0.0),
                            'prompt': filter_result.get('prompt', ''),
                            'llm_response': filter_result.get('llm_response', ''),
                            'parsed_response': filter_result.get('parsed_response', {})
                        }

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
        clarification_result = await self._generate_smart_clarification(candidates_with_attrs, original_message, is_followup, dialog_history)

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
        clarification_result = await self._generate_smart_clarification(candidates_with_attrs, original_message, is_followup, dialog_history)

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

    async def _generate_smart_clarification(self, candidates_with_attrs: List[Dict], original_message: str = "", is_followup: bool = False, dialog_history: List[Dict] = None) -> Dict:
        """
        Генерирует умный уточняющий вопрос на основе анализа атрибутов кандидатов

        Логика: находит ключевые различия в атрибутах (location_type, category, incident_type)
        и задает вопрос именно по этим параметрам, НЕ перечисляя услуги

        ИСПРАВЛЕНО: Добавлен анализ истории диалога для исключения уже отвеченных вопросов
        ИСПРАВЛЕНО: Возвращает Dict с status вместо строки
        ИСПРАВЛЕНО (2025-12-25): Возвращает filtered_candidates для итеративного уточнения
        """
        if not candidates_with_attrs:
            context = {
                'original_message': original_message,
                'dialog_history': dialog_history or []
            }
            return {
                'status': 'AMBIGUOUS',
                'message': self._generate_clarification_questions(context),
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

            # ИСПРАВЛЕНО (2025-12-25): Добавляем needs_confirmation для низкого confidence
            # Получаем confidence из LLM ранжирования если было
            llm_confidence = ranking_result.get('confidence', 0.0) if 'ranking_result' in locals() else 0.0

            # Если confidence < 0.9 - спрашиваем подтверждение
            needs_confirmation = llm_confidence < 0.9

            # Формируем сообщение
            if needs_confirmation:
                message = f"Правильно ли я понял, что у вас: {candidate['service_name']}?"
            else:
                message = f"Понял, у вас: {candidate['service_name']}"

            return {
                'status': 'SUCCESS',
                'service_id': candidate['service_id'],
                'service_name': candidate.get('service_name', candidate.get('scenario_name', 'Unknown')),
                'confidence': llm_confidence if llm_confidence > 0 else 1.0,
                'source': 'filtered_search_with_llm',
                'message': message,
                'single_candidate': candidate,
                'filtered_candidates': filtered_candidates,
                'needs_confirmation': needs_confirmation,
                'is_followup': is_followup
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

        # ИСПРАВЛЕНО (2025-12-26): Используем CommunicativeScriptsService вместо хардкода
        # Если CommunicativeScriptsService доступен - пробуем получить скрипт
        # ИСПРАВЛЕНО (2025-12-28): Используем AI для генерации вопросов
        # ЗАМЕНА: CommunicativeScriptsService → _generate_ai_question
        context = f"Пользователь написал: {original_message}"
        ai_question = await self._generate_ai_question(
            context=context,
            dialog_history=dialog_history,
            candidates=filtered_candidates,
            question_type='clarification'
        )

        return {
            'status': 'AMBIGUOUS',
            'message': ai_question,
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
            context = {
                'original_message': original_message,
                'dialog_history': dialog_history or []
            }
            clarification_message = self._generate_clarification_questions(context)
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

        clarification_result = await self._generate_smart_clarification(candidates_with_attrs, original_message, is_followup, dialog_history)

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

    def _generate_clarification_questions(self, context: Dict = None) -> str:
        """
        Генерирует умные уточняющие вопросы на основе контекста

        ИСПРАВЛЕНО (2025-12-25): Убрана фраза "попробую определить услугу заново"
        ИСПРАВЛЕНО (2025-12-25): Конкретные вопросы вместо общих фраз
        """
        # Если есть контекст предыдущих сообщений, используем его
        if context:
            original_message = context.get('original_message', '').lower()
            dialog_history = context.get('dialog_history', [])

            # Анализируем что уже было сказано
            user_messages = [m.get('text', '') for m in dialog_history if m.get('role') == 'user']

            # Если упоминалась вода/течь - спрашиваем источник
            if any(word in original_message or any(word in msg for msg in user_messages)
                   for word in ['теч', 'льет', 'капает', 'протека', 'утечк', 'вода']):
                return "Уточните, пожалуйста: откуда именно течет? (кран, труба, батарея, крыша, соседей)"

            # Если упоминалось электричество - спрашиваем что конкретно
            if any(word in original_message or any(word in msg for msg in user_messages)
                   for word in ['свет', 'электр', 'розетк', 'выключател', 'лампочк']):
                return "Что именно случилось с электричеством? (нет света, искрит, не работает розетка/выключатель)"

            # Если упоминался мусор/уборка - спрашиваем что конкретно
            if any(word in original_message or any(word in msg for msg in user_messages)
                   for word in ['мусор', 'уборк', 'чистот', 'грязь']):
                return "Уточните, пожалуйста: какая проблема с уборкой? (не вывозят мусор, грязь в подъезде, нужно убрать территорию)"

        # Общий уточняющий вопрос - спрашиваем что сломалось
        return "Что именно случилось? Опишите, пожалуйста: что сломалось, течет или не работает."

    def _generate_context_clarification_question(self, candidates: List[Dict], original_message: str = "", is_followup: bool = False) -> str:
        """
        Генерирует уточняющий вопрос для понимания контекста

        ИСПРАВЛЕНО (2025-12-25): Убрана общая фраза, добавлен конкретный вопрос
        ИСПРАВЛЕНО (2025-12-25): Убран хардкод keywords
        """
        # Если есть оригинальное сообщение - анализируем его
        if original_message:
            original_lower = original_message.lower()

            # Умные вопросы на основе контекста
            if any(word in original_lower for word in ['теч', 'льет', 'капает', 'мокр', 'сыр']):
                return "Откуда именно течет? (кран, труба, батарея, крыша, от соседей)"

            if any(word in original_lower for word in ['сломал', 'не работ', 'испортил', 'поломк']):
                return "Что именно сломалось или не работает?"

            if any(word in original_lower for word in ['запах', 'воня', 'дух']):
                return "Опишите подробнее: откуда запах?"

        # Fallback - если не смогли определить контекст
        # ИСПРАВЛЕНО (2025-12-27): Открытый вопрос вместо двойного
        return "Опишите подробнее, что именно произошло."

    def _generate_smart_fallback(self, original_message: str, dialog_history: list = None, is_followup: bool = False) -> str:
        """
        Генерирует умный fallback вопрос, избегая повторов

        ИСПРАВЛЕНО (2025-12-28):
        - Проверяет историю диалога на повторяющиеся вопросы бота
        - Анализирует последние ответы пользователя
        - Генерирует разные вопросы в зависимости от контекста

        Args:
            original_message: Оригинальное сообщение пользователя
            dialog_history: История диалога
            is_followup: Это продолжение диалога

        Returns:
            str: Умный fallback вопрос
        """
        if not dialog_history:
            # Нет истории - базовый вопрос
            return "Опишите подробнее, что именно произошло."

        # Проверяем последние вопросы бота
        recent_bot_questions = []
        for msg in reversed(dialog_history[-6:]):  # Последние 3 цикла
            if msg.get('role') == 'bot':
                bot_text = msg.get('text', '')
                recent_bot_questions.append(bot_text)

        # Если последний вопрос был "Опишите подробнее что именно произошло"
        # и пользователь ответил коротко ("течет", "течет у меня", "течет труба")
        # то нужно задать более конкретный вопрос

        last_bot_question = recent_bot_questions[0] if recent_bot_questions else ""
        last_user_answers = [msg.get('text', '') for msg in reversed(dialog_history[-4:]) if msg.get('role') == 'user']

        # Проверяем на повторяющийся паттерн
        if "опишите подробнее" in last_bot_question.lower():
            # Бот уже задавал общий вопрос, нужно конкретизировать
            logger.info(f"Detected repeated fallback question, last answers: {last_user_answers}")

            # Анализируем ответы пользователя на ключевые слова
            all_answers = ' '.join(last_user_answers).lower()

            if any(word in all_answers for word in ['теч', 'льет', 'капает', 'мокр']):
                if 'труб' in all_answers:
                    return "Уточните, пожалуйста: где именно течет из трубы? В ванной, на кухне, в другой комнате?"
                elif any(word in all_answers for word in ['батарей', 'отопл', 'радиатор']):
                    return "Понял, проблема с отоплением. В какой именно комнате течет батарея?"
                else:
                    return "Уточните, откуда именно течет? Из трубы, батареи, крана, или от соседей?"

            elif any(word in all_answers for word in ['сломал', 'не работ', 'испортил']):
                return "Какое оборудование сломалось? Опишите подробнее."

            # Если ответ очень короткий (1-2 слова) - просим больше деталей
            if len(last_user_answers) > 0 and len(last_user_answers[-1].split()) <= 2:
                return "Пожалуйста, опишите подробнее: где именно это произошло и что именно сломалось?"

        # Проверяем количество повторов одного и того же
        if len(recent_bot_questions) >= 2:
            # Если последние 2+ вопроса от бота одинаковы
            if len(set(q.lower() for q in recent_bot_questions[:2])) <= 1:
                logger.warning("Detected repeated bot questions, changing strategy")
                return "Пожалуйста, опишите проблему другими словами. Где именно это произошло и что случилось?"

        # Default fallback
        if is_followup:
            return "Уточните детали проблемы."
        return "Опишите подробнее, что именно произошло."

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
                    # ИСПРАВЛЕНО (2025-12-27): Открытый вопрос вместо двойного
                    'message': 'Понимаю, у вас поломка оборудования. Опишите подробнее, что именно сломалось.',
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

    # ========================================================================
    # ИСПРАВЛЕНО (2025-12-25): AI ORCHESTRATOR - УМНЫЙ ОРКЕСТРАТОР
    # ========================================================================

    async def _orchestrate_microservices(
        self,
        message_text: str,
        search_results: Dict,
        dialog_history: List[Dict] = None,
        txtPrb: str = None,
        established_filters: Dict = None
    ) -> Dict:
        """
        Главный АГЕНТ-ОРКЕСТРАТОР: принимает решения на основе результатов микросервисов

        ИСПРАВЛЕНО (2025-12-25): Полноценный оркестратор с умными решениями
        Использует UNION вместо INTERSECTION для объединения результатов
        """
        # ИСПРАВЛЕНО (2025-12-27): Логирование для отладки фильтрации
        logger.info(f"⚙️ _orchestrate_microservices: established_filters={established_filters}")

        tag_results = search_results.get('tag_search', {}).get('candidates', [])
        semantic_results = search_results.get('semantic_search', {}).get('candidates', [])
        vector_results = search_results.get('vector_search', {}).get('candidates', [])

        # ИСПРАВЛЕНО (2025-12-25): UNION всех результатов с приоритетами (не пересечение!)
        all_candidates = []

        # TagSearch: приоритет 1.0 (точный матч по тегам)
        for c in tag_results:
            all_candidates.append({
                **c,
                'priority': 1.0,
                'sources': c.get('sources', ['tag_search'])
            })

        # SemanticSearch: приоритет 0.8 (семантический матч)
        for c in semantic_results:
            all_candidates.append({
                **c,
                'priority': 0.8,
                'sources': c.get('sources', ['semantic_search'])
            })

        # VectorSearch: приоритет 0.6 (нечеткий матч)
        for c in vector_results:
            all_candidates.append({
                **c,
                'priority': 0.6,
                'sources': c.get('sources', ['vector_search'])
            })

        # Дедупликация и сортировка по приоритету
        unique_candidates = self._deduplicate_and_prioritize_candidates(all_candidates)

        logger.info(f"AI Orchestrator: UNION={len(all_candidates)}, уникальных={len(unique_candidates)}")

        if not unique_candidates:
            # Никто ничего не нашел - спрашиваем что случилось
            return {
                'status': 'AMBIGUOUS',
                'message': await self._ask_ai_what_happened(
                    message_text, dialog_history,
                    established_filters=established_filters,  # ИСПРАВЛЕНО: передаем фильтры
                    txtPrb=txtPrb  # ИСПРАВЛЕНО: передаем txtPrb
                ),
                'candidates': [],
                'metadata': {}
            }

        # Если 1 кандидат - но нужно проверить confidence
        if len(unique_candidates) == 1:
            candidate = unique_candidates[0]
            confidence = candidate.get('confidence', 0.0)

            if confidence >= 0.9:
                # Высокий confidence - подтверждаем
                return {
                    'status': 'SUCCESS',
                    'service_id': candidate['service_id'],
                    'service_name': candidate['service_name'],
                    'confidence': confidence,
                    'message': f"Понял, у вас: {candidate['service_name']}. Правильно?",
                    'needs_confirmation': True,
                    'source': 'orchestrator'
                }
            else:
                # Низкий confidence - уточняем через AI
                return await self._ask_ai_clarification(message_text, unique_candidates, dialog_history)

        # Если несколько кандидатов (2-10) - используем AI для уточнения
        elif len(unique_candidates) <= 10:
            # ИСПРАВЛЕНО (2025-12-27): Используем AI для анализа кандидатов
            # вместо CommunicativeScriptsService
            # ИСПРАВЛЕНО (2025-12-27): Передаем established_filters для сужения кандидатов
            return await self._ask_ai_clarification_with_candidates(
                message_text, unique_candidates, dialog_history, established_filters
            )

        # Много кандидатов (>10) - нужно задать уточняющий вопрос
        else:
            question = await self._ask_ai_what_happened(
                message_text, dialog_history,
                established_filters=established_filters,
                txtPrb=txtPrb
            )
            return {
                'status': 'AMBIGUOUS',
                'message': question,
                'candidates': unique_candidates[:10],
                'metadata': {}
            }
    
    
    async def _ask_ai_what_happened(self, message_text: str, dialog_history: List[Dict],
                                    established_filters: Dict = None, txtPrb: str = None) -> str:
        """Спрашивает у AI что случилось и где

        ИСПРАВЛЕНО (2025-12-26): Использует CommunicativeScriptsService вместо AI генерации
        ИСПРАВЛЕНО (2025-12-25): Учитывает историю диалога чтобы не повторять вопросы

        Args:
            message_text: Текст сообщения пользователя
            dialog_history: История диалога
            established_filters: Установленные фильтры с весами
            txtPrb: Накопленное описание проблемы (из ProblemAccumulationService)
        """
        # Вычисляем dialog_turn
        dialog_turn = len(dialog_history) if dialog_history else 1

        # Определяем is_followup
        is_followup = dialog_turn > 1

        # Собираем последние вопросы бота
        recent_bot_questions = []
        if dialog_history:
            for msg in dialog_history:
                if msg.get('role') == 'bot' and '?' in msg.get('text', ''):
                    question = msg.get('text', '')
                    if '?' in question:
                        question = question.split('?')[0] + '?'
                        recent_bot_questions.append(question)

        # Логирование контекста
        if txtPrb:
            logger.info(f"txtPrb: {txtPrb}")
        if established_filters:
            logger.info(f"established_filters: {established_filters}")
        if recent_bot_questions:
            logger.info(f"recent_bot_questions: {recent_bot_questions}")

        # ИСПРАВЛЕНО (2025-12-28): Используем AI для генерации вопроса
        # ЗАМЕНА: CommunicativeScriptsService → _generate_ai_question
        context = f"Пользователь написал: {message_text}"
        question = await self._generate_ai_question(
            context=context,
            dialog_history=dialog_history,
            established_filters=established_filters,
            txtPrb=txtPrb,
            question_type='what_happened'
        )

        logger.info(f"AI сгенерировал вопрос (turn={dialog_turn}, followup={is_followup}): {question}")
        return question

    async def _generate_ai_question(
        self,
        context: str,
        dialog_history: List[Dict] = None,
        candidates: List[Dict] = None,
        established_filters: Dict = None,
        txtPrb: str = None,
        question_type: str = "clarification"
    ) -> str:
        """
        Универсальный метод для генерации вопросов через AI

        ИСПРАВЛЕНО (2025-12-28): Все вопросы генерируются через YandexGPT
        ЗАМЕНА: Все хардкод вопросы и CommunicativeScriptsService

        Args:
            context: Контекст ситуации (описание проблемы)
            dialog_history: История диалога
            candidates: Кандидаты услуг (для уточнения)
            established_filters: Установленные фильтры
            txtPrb: Накопленное описание проблемы
            question_type: Тип вопроса
                - 'clarification' - уточняющий вопрос
                - 'what_happened' - что случилось
                - 'location' - где произошло
                - 'details' - детали проблемы

        Returns:
            str: Сгенерированный AI вопрос
        """
        try:
            # Формируем промт для AI
            prompt = self._build_question_prompt(
                context=context,
                dialog_history=dialog_history,
                candidates=candidates,
                established_filters=established_filters,
                txtPrb=txtPrb,
                question_type=question_type
            )

            # Вызываем AI через AIAgentService
            if self.ai_agent:
                response, usage = await self.ai_agent._call_yandex_gpt(prompt)
                question = response.strip()

                # Удаляем лишние кавычки если есть
                if question.startswith('"') and question.endswith('"'):
                    question = question[1:-1]
                if question.startswith("'") and question.endswith("'"):
                    question = question[1:-1]

                logger.info(f"AI сгенерировал вопрос ({question_type}): {question}")
                return question
            else:
                logger.warning("AIAgentService недоступен, используем fallback")
                return self._fallback_question(question_type, context)

        except Exception as e:
            logger.error(f"Ошибка генерации AI вопроса: {e}")
            return self._fallback_question(question_type, context)

    def _build_question_prompt(
        self,
        context: str,
        dialog_history: List[Dict] = None,
        candidates: List[Dict] = None,
        established_filters: Dict = None,
        txtPrb: str = None,
        question_type: str = "clarification"
    ) -> str:
        """Строит промт для генерации вопроса

        ПЕРЕРАБОТАНО (2025-12-28):
        - Добавлено объяснение про фильтры и услуги
        - Атомарные открытые вопросы
        - Запрет на двойные вопросы
        """

        # Анализируем что уже известно из истории
        known_info = self._extract_known_info(dialog_history, txtPrb)

        # Собираем контекст из истории
        recent_dialog = ""
        if dialog_history:
            last_msgs = dialog_history[-4:]  # Последние 2 цикла
            for msg in last_msgs:
                role = "Пользователь" if msg.get('role') == 'user' else "Бот"
                recent_dialog += f"{role}: {msg.get('text', '')}\n"

        # Формируем таблицу кандидатов для промта
        candidates_table = ""
        if candidates and len(candidates) > 0:
            candidates_table = "\nТАБЛИЦА КАНДИДАТОВ (услуги которые подходят под описание):\n"
            for i, c in enumerate(candidates[:10], 1):
                name = c.get('service_name', c.get('scenario_name', 'Unknown'))
                incident_type = c.get('incident_type', '-')
                location_type = c.get('location_type', '-')
                category = c.get('category', '-')
                object_type = c.get('object_type', '-')
                candidates_table += f"{i}. {name}\n"
                candidates_table += f"   Тип: {incident_type} | Вид: {location_type} | Категория: {category} | Объект: {object_type}\n"

        # Формируем промт
        prompt = f"""Ты - диспетчер УК "Аспект". Твоя ГЛАВНАЯ задача - определить нужную услугу из каталога.

══════════════════════════════════════════════════════════════════════════════
КАК РАБОТАЕТ СИСТЕМА ФИЛЬТРОВ
══════════════════════════════════════════════════════════════════════════════

Услуги в каталоге имеют характеристики:
- Тип (incident_type): Инцидент | Запрос
  * Инцидент = что-то сломалось, не работает, есть угроза жизни/имуществу
  * Запрос = нужно выполнить работу, нет угрозы

- Вид (location_type): Индивидуальное | Общедомовое
  * Индивидуальное = проблема в квартире пользователя
  * Общедомовое = проблема в подъезде, на улице, в местах общего пользования

- Категория (category): Водоснабжение | Отопление | Канализация | Электрика | и т.д.

- Объект (object_type): Труба | Кран | Батарея | Розетка | и т.д.

- Теги: ключевые слова для поиска

Твоя стратегия: задавай вопросы чтобы установить фильтры и сократить список кандидатов.

══════════════════════════════════════════════════════════════════════════════
ТЕКУЩАЯ СИТУАЦИЯ
══════════════════════════════════════════════════════════════════════════════

{context}
"""

        if known_info:
            prompt += f"""
УЖЕ ИЗВЕСТНО (не спрашивай повторно):
{known_info}
"""

        if txtPrb:
            prompt += f"""
ОПИСАНИЕ ПРОБЛЕМЫ:
{txtPrb}
"""

        if recent_dialog:
            prompt += f"""
ПОСЛЕДНИЕ СООБЩЕНИЯ:
{recent_dialog}
"""

        if established_filters:
            prompt += f"""
УСТАНОВЛЕННЫЕ ФИЛЬТРЫ (сокращают список кандидатов):
{self._format_filters_for_prompt(established_filters)}
"""

        if candidates_table:
            prompt += f"\n{candidates_table}\n"

        # Инструкция по типу вопроса
        if question_type == 'clarification':
            prompt += """
══════════════════════════════════════════════════════════════════════════════
КАК ЗАДАВАТЬ ВОПРОСЫ
══════════════════════════════════════════════════════════════════════════════

ПРАВИЛО 1: Один атомарный вопрос за раз
- ПРАВИЛЬНО: "Где именно это произошло?"
- ПРАВИЛЬНО: "Что именно сломалось?"
- НЕПРАВИЛЬНО: "Что и где?" (двойной вопрос)

ПРАВИЛО 2: Открытые вопросы без перечислений
- ПРАВИЛЬНО: "Уточните какие последствия?"
- ПРАВИЛЬНО: "Опишите подробнее что случилось"
- НЕПРАВИЛЬНО: "Это труба или батарея?" (закрытый вопрос)
- НЕПРАВИЛЬНО: "Выберите: 1-труба 2-батарея 3-кран" (перечисление)

ПРАВИЛО 3: Не спрашивай то что уже известно
- Если известно "течет" → НЕ спрашивай "Что течет?"
- Если известно "в зале" → НЕ спрашивай "Где?"
- Вместо этого спроси что-то что УТОЧНЯЕТ ситуацию

ПРАВИЛО 4: Учитывай таблицу кандидатов
- Если все кандидаты "Индивидуальное" → НЕ спрашивай "В квартире или общем месте?"
- Если все кандидаты "Инцидент" → НЕ спрашивай "Это срочная проблема?"

ПРАВИЛО 5: Важные запреты
- НЕ используй эмодзи
- НЕ используй числа (1, 2, 3)
- НЕ перечисляй варианты
- НЕ задавай двойные вопросы с союзом "и"

══════════════════════════════════════════════════════════════════════════════
ПРИМЕРЫ ХОРОШИХ ВОПРОСОВ
══════════════════════════════════════════════════════════════════════════════

Ситуация: "течет"
Хороший вопрос: "Где именно это произошло?"
Обоснование: Устанавливает фильтр "Вид: Индивидуальное/Общедомовое"

Ситуация: "течет труба в зале"
Хороший вопрос: "Опишите подробнее что именно с трубой"
Обоснование: Уточняет характер проблемы для выбора категории услуги

Ситуация: "не работает лифт"
Хороший вопрос: "Опишите что именно не происходит"
Обоснование: Уточняет серьезность для определения типа (Инцидент/Запрос)

══════════════════════════════════════════════════════════════════════════════
ПРИМЕРЫ ПЛОХИХ ВОПРОСОВ
══════════════════════════════════════════════════════════════════════════════

Плохой: "Опишите что течет и где это произошло?"
Причина: ДВОЙНОЙ вопрос (что + где)

Плохой: "Это инцидент или запрос?"
Причина: Закрытый вопрос с перечислением
Правильно: "Опишите насколько это срочно"

Плохой: "У вас это 1-труба 2-батарея 3-кран?"
Причина: Перечисление вариантов
Правильно: "Что именно сломалось?"

══════════════════════════════════════════════════════════════════════════════
ЗАДАЧА
══════════════════════════════════════════════════════════════════════════════

Задай ОДИН вопрос который поможет сократить таблицу кандидатов.

Ограничения:
- Максимально коротко (1 предложение)
- Открытый вопрос
- Без перечислений
- Без эмодзи и чисел
- Учитывай что уже известно
- Учитывай таблицу кандидатов

Вопрос:"""

        elif question_type == 'what_happened':
            prompt += """

══════════════════════════════════════════════════════════════════════════════
ЗАДАЧА
══════════════════════════════════════════════════════════════════════════════

Задай ОДИН вопрос чтобы понять что именно случилось.

Ограничения:
- Один вопрос
- Открытый вопрос
- Без перечислений
- Коротко

Вопрос:"""

        elif question_type == 'location':
            prompt += """

══════════════════════════════════════════════════════════════════════════════
ЗАДАЧА
══════════════════════════════════════════════════════════════════════════════

Задай ОДИН вопрос о месте проблемы.

Ограничения:
- Один вопрос
- Открытый вопрос
- Не спрашивай если локация уже известна
- Коротко

Вопрос:"""

        else:  # details
            prompt += """

══════════════════════════════════════════════════════════════════════════════
КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:
══════════════════════════════════════════════════════════════════════════════

1. ❌ КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО: Двойные вопросы
2. ❌ НЕ спрашивать то, что УЖЕ известно
3. ❌ НЕ использовать союз "и"

ЗАДАЧА: Задай ОДИН уточняющий вопрос для детализации проблемы.

Ограничения:
- Только ОДИН вопрос
- Открытый вопрос
- Вежливый тон
- Учитывай что уже известно (не спрашивай повторно)
- Без союза "и"

Вопрос:"""

        return prompt

    def _format_filters_for_prompt(self, filters: Dict) -> str:
        """Форматирует установленные фильтры для промта AI."""
        if not filters:
            return "Нет установленных фильтров"

        lines = []
        for key, value in filters.items():
            if isinstance(value, dict) and 'value' in value:
                conf = value.get('confidence', 0.0)
                lines.append(f"- {key}: {value['value']} (уверенность: {conf*100:.0f}%)")
            elif value:
                lines.append(f"- {key}: {value}")

        return '\n'.join(lines)

    def _extract_known_info(self, dialog_history: List[Dict] = None, txtPrb: str = None) -> str:
        """
        Извлекает уже известную информацию из диалога

        ИСПРАВЛЕНО (2025-12-28): Использует ProblemAccumulationService вместо хардкода
        ИСПРАВЛЕНО (2025-12-28): УБРАН хардкод keywords!

        Returns:
            str: Список известной информации
        """
        if not dialog_history and not txtPrb:
            return ""

        known = []

        # Используем ProblemAccumulationService для анализа
        if self.problem_accumulator and dialog_history:
            # Собираем все сообщения пользователя
            user_texts = [m.get('text', '') for m in dialog_history if m.get('role') == 'user']

            if user_texts:
                # Вызываем ProblemAccumulationService для анализа
                try:
                    # ProblemAccumulationService уже извлекает все поля через AI
                    accumulated = self.problem_accumulator.accumulate_problem(
                        message_text=' '.join(user_texts),
                        existing_fields={},
                        dialog_history=dialog_history
                    )

                    if accumulated:
                        # Формируем описание из накопленных полей
                        parts = []
                        if accumulated.get('problem'):
                            parts.append(f"Проблема: {accumulated['problem']}")
                        if accumulated.get('location'):
                            parts.append(f"Локация: {accumulated['location']}")
                        if accumulated.get('source'):
                            parts.append(f"Объект: {accumulated['source']}")
                        if accumulated.get('category'):
                            parts.append(f"Категория: {accumulated['category']}")

                        if parts:
                            known.append(' | '.join(parts))

                except Exception as e:
                    logger.warning(f"Ошибка ProblemAccumulationService в _extract_known_info: {e}")

        # Fallback: используем txtPrb если есть
        if not known and txtPrb and txtPrb != "(нет значимой информации)":
            known.append(f"Описание: {txtPrb}")

        return '\n'.join(known) if known else ""

    def _fallback_question(self, question_type: str, context: str) -> str:
        """Fallback вопросы если AI недоступен"""
        fallbacks = {
            'clarification': "Уточните, пожалуйста, детали проблемы.",
            'what_happened': "Опишите подробнее, что именно произошло.",
            'location': "Где именно это произошло?",
            'details': "Пожалуйста, уточните детали."
        }
        return fallbacks.get(question_type, "Уточните детали проблемы.")

    async def _ask_ai_clarification_with_candidates(
        self,
        message_text: str,
        candidates: List[Dict],
        dialog_history: List[Dict],
        established_filters: Dict = None
    ) -> Dict:
        """Спрашивает у AI как уточнить - использует AI для анализа кандидатов

        ИСПРАВЛЕНО (2025-12-27): Использует AI для генерации вопроса на основе кандидатов
        ИСПРАВЛЕНО (2025-12-27): Закомментированы кэшированные запросы
        ИСПРАВЛЕНО (2025-12-27): Применяет established_filters для сужения кандидатов
        """
        # ИСПРАВЛЕНО (2025-12-27): Применяем фильтры к кандидатам
        if established_filters:
            before_count = len(candidates)
            logger.info(f"⚙️ _ask_ai_clarification: candidates до фильтров: {before_count}")
            logger.info(f"⚙️ _ask_ai_clarification: established_filters={established_filters}")

            candidates = self._apply_filters_to_candidates(candidates, established_filters)
            after_count = len(candidates)
            logger.info(f"✅ _ask_ai_clarification: после фильтров: {after_count} кандидатов")

            # Показываем оставшихся кандидатов
            for i, c in enumerate(candidates[:5], 1):
                logger.info(f"  {i}. {c.get('service_name', 'Unknown')} (loc={c.get('location_type', '?')[:10]} conf={c.get('confidence', 0):.2f})")
        else:
            logger.info(f"⚙️ _ask_ai_clarification: established_filters=None, пропускаем фильтрацию")

        # ИСПРАВЛЕНО (2025-12-27): Закомментированы кэшированные запросы - используем только AI
        # if self.cache_service:  # DISABLED
        #     cached = self.cache_service.get_cached_response(message_text)
        #     if cached:
        #         return cached

        # ИСПРАВЛЕНО (2025-12-27): Добавляем контекст txtPrb и previous questions в промпт
        # Собираем предыдущие вопросы бота
        recent_bot_questions = []
        if dialog_history:
            for msg in dialog_history:
                if msg.get('role') == 'bot' and '?' in msg.get('text', ''):
                    question = msg.get('text', '')
                    if '?' in question:
                        question = question.split('?')[0] + '?'
                        recent_bot_questions.append(question)

        # Формируем контекст
        context_info = ""
        if recent_bot_questions:
            context_info = f"\nУЖЕ ЗАДАННЫЕ ВОПРОСЫ (НЕ ПОВТОРЯЙ!):\n"
            for q in recent_bot_questions[-3:]:
                context_info += f"  - {q}\n"

        # СУПЕР-ЖЁСТКИЙ ПРОМПТ с конкретными примерами (2025-12-27)
        prompt = f"""Пользователь написал: "{message_text}"
{context_info}
Возможные услуги:
{chr(10).join(f"{i+1}. {c['service_name']}" for i, c in enumerate(candidates[:5]))}

ЗАДАЙ ОДИН ОТКРЫТЫЙ ВОПРОС без вариантов ответа.

══════════════════════════════════════════════════════════════════════════════
🚫 КАТЕГОРИЧЕСКИ ЗАПРЕЩЕННЫЕ ПРИМЕРЫ (НЕПРАВИЛЬНО):
🚫 "Где именно — в квартире или за её пределами?"
🚫 "Что конкретно течёт: труба, кран, батарея?"
🚫 "Требуется ли ремонт водопроводных или канализационных труб?"
🚫 "Это отопление или водоснабжение?"
🚫 "Где именно произошла протечка — в системе отопления общедомовой, в квартире или это общедомовой прорыв труб?"

═════════════════════════════════════════════════════════════════════════════
✅ ПРАВИЛЬНЫЕ ПРИМЕРЫ (ОТКРЫТЫЕ ВОПРОСЫ):
✅ "Где именно течет?"
✅ "Что именно сломалось?"
✅ "Опишите подробнее что случилось."
✅ "Уточните где именно это произошло."

═════════════════════════════════════════════════════════════════════════════
КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:
1. ❌ НЕ использовать слово "или" (в любом регистре)
2. ❌ НЕ перечислять варианты через запятую
3. ❌ НЕ использовать скобки с вариантами
4. ❌ НЕ использовать тире с вариантами
5. ❌ НЕ предлагать выбор из списка
6. ✅ Вопрос должен начинаться с: Где/Что/Какой/Опишите/Уточните
7. ✅ Только ОДИН вопрос
8. ❌ НЕ повторять уже заданные вопросы выше

Верни ТОЛЬКО текст вопроса БЕЗ слов "Вопрос:", "Ответ:" и других пояснений:"""

        if not self.ai_agent:
            return {
                'status': 'AMBIGUOUS',
                'message': "Опишите подробнее что именно произошло.",
                'candidates': candidates,
                'needs_clarification': True
            }

        try:
            response, _ = await self.ai_agent._call_yandex_gpt(prompt)
            ai_question = response.strip()
            logger.info(f"AI сгенерировал вопрос для {len(candidates)} кандидатов: {ai_question}")

            # ИСПРАВЛЕНО (2025-12-27): Post-processing проверка на запрещённые паттерны
            question_lower = ai_question.lower()

            # Запрещённые паттерны
            has_ili = ' или ' in question_lower or question_lower.endswith(' или')
            has_comma_enumeration = ',' in ai_question and '?' in ai_question
            has_parens = '(' in ai_question and ')' in ai_question
            has_dash_variants = ' — ' in ai_question or ' - ' in ai_question

            # Проверка на перечисление (несколько слов с большой буквы через запятую)
            has_multiple_options = False
            if has_comma_enumeration:
                parts = ai_question.split('?')[0].split(',')
                if len(parts) >= 2:
                    # Проверяем есть ли несколько слов с большой буквы (перечисление вариантов)
                    capitalized_parts = [p.strip() for p in parts if p.strip() and p.strip()[0].isupper()]
                    has_multiple_options = len(capitalized_parts) >= 2

            if has_ili or has_multiple_options or has_parens or has_dash_variants:
                logger.warning(
                    f"⚠️ AI сгенерировал запрещённый паттерн! "
                    f"или={has_ili}, перечисление={has_multiple_options}, "
                    f"скобки={has_parens}, тире={has_dash_variants}"
                )
                logger.warning(f"❌ Запрещённый вопрос: {ai_question}")

                # ИСПРАВЛЕНО (2025-12-28): Используем AI для генерации fallback вопроса
                context = f"Пользователь написал: {message_text}"
                ai_question = await self._generate_ai_question(
                    context=context,
                    dialog_history=dialog_history,
                    candidates=candidates,
                    question_type='clarification'
                )
                logger.info(f"✅ Заменяем на AI вопрос: {ai_question}")

            return {
                'status': 'AMBIGUOUS',
                'message': ai_question,
                'candidates': candidates,
                'needs_clarification': True
            }
        except Exception as e:
            logger.error(f"Ошибка AI генерации уточнения: {e}")
            return {
                'status': 'AMBIGUOUS',
                'message': "Опишите подробнее что именно произошло.",
                'candidates': candidates,
                'needs_clarification': True
            }

    async def _ask_ai_clarification(self, message_text: str, candidates: List[Dict], dialog_history: List[Dict]) -> Dict:
        """Спрашивает как уточнить - использует CommunicativeScriptsService

        ИСПРАВЛЕНО (2025-12-26): Вместо AI использует CommunicativeScriptsService
        """
        # Вычисляем dialog_turn и is_followup
        dialog_turn = len(dialog_history) if dialog_history else 1
        is_followup = dialog_turn > 1

        # ИСПРАВЛЕНО (2025-12-28): Используем AI для генерации вопроса
        # ЗАМЕНА: CommunicativeScriptsService → _generate_ai_question
        context = f"Пользователь написал: {message_text}"
        ai_question = await self._generate_ai_question(
            context=context,
            dialog_history=dialog_history,
            candidates=candidates,
            question_type='clarification'
        )

        return {
            'status': 'AMBIGUOUS',
            'message': ai_question,
            'candidates': candidates,
            'needs_clarification': True
        }

    def _deduplicate_and_prioritize_candidates(self, all_candidates: List[Dict]) -> List[Dict]:
        """
        Дедупликация кандидатов с приоритетами

        ИСПРАВЛЕНО (2025-12-26): Использован средневзвешенный коэффициент для priority
        вместо простого MAX. Если услуга найдена несколькими сервисами,
        priority вычисляется как: (p1*conf1 + p2*conf2) / (conf1 + conf2)
        + бонус за количество источников + бонус за высокую суммарную уверенность
        """
        # Группируем по service_id
        candidates_map = {}  # {service_id: aggregated_data}

        for c in all_candidates:
            sid = c.get('service_id')

            if sid not in candidates_map:
                # Первое вхождение
                candidates_map[sid] = {
                    'service_id': sid,
                    'service_name': c.get('service_name'),
                    'priorities': [c.get('priority', 0.0)],  # Список приоритетов
                    'confidences': [c.get('confidence', 0.0)],  # Список уверенности
                    'sources': set(c.get('sources', [])),
                    'all_data': [c]
                }
            else:
                # Уже есть - добавляем данные для расчета средневзвешенного
                existing = candidates_map[sid]
                existing['priorities'].append(c.get('priority', 0.0))
                existing['confidences'].append(c.get('confidence', 0.0))
                existing['sources'].update(c.get('sources', []))
                existing['all_data'].append(c)

        # Вычисляем средневзвешенный priority и применяем бонусы
        unique_candidates = []

        for sid, c in candidates_map.items():
            priorities = c['priorities']
            confidences = c['confidences']

            # Средневзвешенный приоритет: (p1*conf1 + p2*conf2) / (conf1 + conf2)
            total_conf = sum(confidences)
            if total_conf > 0:
                weighted_priority = sum(p * conf for p, conf in zip(priorities, confidences)) / total_conf
            else:
                weighted_priority = sum(priorities) / len(priorities) if priorities else 0.0

            # Бонус за количество источников (мульти-source подтверждение)
            source_count = len(c['sources'])
            source_bonus = 0.0
            if source_count > 1:
                source_bonus = min(0.05 * (source_count - 1), 0.15)  # Максимум +0.15

            # Бонус за высокую суммарную уверенность
            confidence_bonus = 0.0
            avg_confidence = total_conf / len(confidences) if confidences else 0.0
            if avg_confidence >= 0.95:
                confidence_bonus = 0.05
            elif avg_confidence >= 0.90:
                confidence_bonus = 0.03

            # Итоговый приоритет
            final_priority = min(weighted_priority + source_bonus + confidence_bonus, 1.0)

            # Формируем итогового кандидата
            unique_candidates.append({
                'service_id': sid,
                'service_name': c.get('service_name'),
                'confidence': avg_confidence,  # Средняя уверенность
                'priority': final_priority,  # Средневзвешенный + бонусы
                'sources': list(c['sources']),
                'all_data': c['all_data'],
                '_debug_info': {  # Для отладки
                    'weighted_priority': weighted_priority,
                    'source_bonus': source_bonus,
                    'confidence_bonus': confidence_bonus,
                    'source_count': source_count
                }
            })

        # Сортируем по priority (убывание)
        unique_candidates.sort(key=lambda x: x.get('priority', 0.0), reverse=True)

        logger.info(f"Дедупликация: {len(all_candidates)} -> {len(unique_candidates)} кандидатов")

        # Логируем топ-3 кандидатов с отладочной информацией
        for i, c in enumerate(unique_candidates[:3], 1):
            debug = c.get('_debug_info', {})
            logger.info(
                f"  #{i} ID:{c['service_id']} | priority={c['priority']:.3f} "
                f"(weighted={debug.get('weighted_priority', 0):.3f} "
                f"+source_bonus={debug.get('source_bonus', 0):.3f} "
                f"+conf_bonus={debug.get('confidence_bonus', 0):.3f}) "
                f"| sources={c['sources']}"
            )

        return unique_candidates

    def _apply_filters_to_candidates(self, candidates: List[Dict], established_filters: Dict) -> List[Dict]:
        """
        Применяет установленные фильтры к кандидатам для сужения списка

        ИСПРАВЛЕНО (2025-12-27): Использует established_filters с высокой уверенностью
        для фильтрации кандидатов по location_type, incident_type, category

        Args:
            candidates: Список кандидатов с атрибутами
            established_filters: Установленные фильтры {filter_name: {'value': ..., 'confidence': ...}}

        Returns:
            List[Dict]: Отфильтрованный список кандидатов
        """
        # Порог применения фильтра - только фильтры с уверенностью >= 0.8
        FILTER_CONFIDENCE_THRESHOLD = 0.8

        logger.info(f"🔍 _apply_filters_to_candidates: начало, кандидатов={len(candidates)}, фильтров={len(established_filters)}")

        # Применяем фильтры по очереди
        filtered_candidates = candidates

        for filter_name, filter_data in established_filters.items():
            confidence = filter_data.get('confidence', 0.0)
            value = filter_data.get('value')

            # Применяем только фильтры с высокой уверенностью
            if confidence < FILTER_CONFIDENCE_THRESHOLD:
                logger.info(f"⚠️ Фильтр {filter_name}: confidence={confidence:.2f} < {FILTER_CONFIDENCE_THRESHOLD}, ПРОПУСКАЕМ")
                continue

            logger.info(f"✅ ПРИМЕНЯЕМ ФИЛЬТР: {filter_name}={value} (confidence={confidence:.2f} >= {FILTER_CONFIDENCE_THRESHOLD})")

            # Фильтрация по location
            if filter_name == 'location' and value:
                # Маппинг: зал/комната -> Индивидуальное
                if value in ['Индивидуальное', 'Квартира', 'индивидуальное']:
                    # Оставляем только Individual
                    before_count = len(filtered_candidates)
                    filtered_candidates = [
                        c for c in filtered_candidates
                        if c.get('location_type', '').lower() in ['индивидуальное', 'квартира']
                    ]
                    after_count = len(filtered_candidates)
                    logger.info(f"  Фильтр location: {before_count} -> {after_count} (оставили Individual)")

            # Фильтрация по incident
            elif filter_name == 'incident' and value:
                if value in ['Инцидент', 'инцидент']:
                    before_count = len(filtered_candidates)
                    filtered_candidates = [
                        c for c in filtered_candidates
                        if c.get('incident_type', '').lower() in ['инцидент']
                    ]
                    after_count = len(filtered_candidates)
                    logger.info(f"  Фильтр incident: {before_count} -> {after_count} (оставили Инцидент)")

            # Фильтрация по category
            elif filter_name == 'category' and value:
                before_count = len(filtered_candidates)
                filtered_candidates = [
                    c for c in filtered_candidates
                    if value.lower() in c.get('category', '').lower()
                ]
                after_count = len(filtered_candidates)
                logger.info(f"  Фильтр category: {before_count} -> {after_count} (оставили {value})")

            # Фильтрация по object_description (поиск по названию услуги)
            elif filter_name == 'object_description' and value:
                before_count = len(filtered_candidates)
                # Ищем совпадение в названии услуги
                filtered_candidates = [
                    c for c in filtered_candidates
                    if value.lower() in c.get('service_name', '').lower()
                ]
                after_count = len(filtered_candidates)
                logger.info(f"  Фильтр object: {before_count} -> {after_count} (оставили содержащие '{value}')")

        return filtered_candidates

