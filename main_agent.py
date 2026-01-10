#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Главный Агент системы определения услуг
Координирует работу микросервисов поиска услуг с воронкой точности
"""

import logging
import asyncio
import traceback
import json
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

        # ИСПРАВЛЕНО (2025-12-29): Кэш фильтров из БД
        self._categories_cache = None
        self._objects_cache = None
        self._location_types_cache = None
        self._incident_types_cache = None

        # ИСПРАВЛЕНО (2025-12-29): Настройка отладки промптов
        from django.conf import settings
        self.tst_prompt = getattr(settings, 'TST_PROMPT', 0)

        # Инициализируем микросервисы
        self._init_services()
        self._load_filters_from_db()  # Загружаем фильтры из БД

        logger.info("Главный Агент инициализирован с микросервисной архитектурой")
        logger.info(f"🐛 TST_PROMPT={self.tst_prompt} (режим отладки вопросов)")

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

    def _load_filters_from_db(self):
        """
        ИСПРАВЛЕНО (2025-12-29): Загружает уникальные значения фильтров из БД
        для использования в промтах вместо захардкоженных значений
        """
        try:
            with connection.cursor() as cursor:
                # Загружаем уникальные категории
                cursor.execute("SELECT DISTINCT category FROM services_catalog WHERE category IS NOT NULL AND category != '' ORDER BY category")
                self._categories_cache = [row[0] for row in cursor.fetchall()]

                # Загружаем уникальные объекты
                cursor.execute("SELECT DISTINCT object_type FROM services_catalog WHERE object_type IS NOT NULL AND object_type != '' ORDER BY object_type")
                self._objects_cache = [row[0] for row in cursor.fetchall()]

                # Загружаем типы локации
                cursor.execute("SELECT DISTINCT location_type FROM services_catalog WHERE location_type IS NOT NULL AND location_type != '' ORDER BY location_type")
                self._location_types_cache = [row[0] for row in cursor.fetchall()]

                # Загружаем типы инцидентов
                cursor.execute("SELECT DISTINCT incident_type FROM services_catalog WHERE incident_type IS NOT NULL AND incident_type != '' ORDER BY incident_type")
                self._incident_types_cache = [row[0] for row in cursor.fetchall()]

                logger.info(f"[OK] Загружены фильтры из БД:")
                logger.info(f"   Категории ({len(self._categories_cache)}): {', '.join(self._categories_cache[:5])}...")
                logger.info(f"   Объекты ({len(self._objects_cache)}): {', '.join(self._objects_cache[:5])}...")
                logger.info(f"   Локации ({len(self._location_types_cache)}): {', '.join(self._location_types_cache)}")
                logger.info(f"   Инциденты ({len(self._incident_types_cache)}): {', '.join(self._incident_types_cache)}")

        except Exception as e:
            logger.error(f"Ошибка загрузки фильтров из БД: {e}")
            # Fallback на захардкоженные значения
            self._categories_cache = ['Водоснабжение', 'Отопление', 'Канализация', 'Электрика']
            self._objects_cache = ['Труба', 'Кран', 'Батарея', 'Розетка']
            self._location_types_cache = ['Индивидуальное', 'Общедомовое']
            self._incident_types_cache = ['Инцидент', 'Запрос']

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
        session_id = None  # ИСПРАВЛЕНО (2026-01-06): Извлекаем session_id
        message_id = None  # ИСПРАВЛЕНО (2026-01-06): Извлекаем message_id

        if user_context:
            original_message = user_context.get('original_message', message_text)
            is_followup = user_context.get('is_followup', False)
            dialog_history = user_context.get('dialog_history', [])
            session_id = user_context.get('session_id')  # ИСПРАВЛЕНО (2026-01-06)
            message_id = user_context.get('message_id')  # ИСПРАВЛЕНО (2026-01-06)

            if is_followup and dialog_history:
                logger.info(f"Главный Агент обрабатывает уточняющее сообщение: '{original_message}' (история: {len(dialog_history)} сообщений)")
            else:
                logger.info(f"Главный Агент начал обработку: '{message_text[:50]}...'")
        else:
            logger.info(f"Главный Агент начал обработку: '{message_text[:50]}'")

        # ИСПРАВЛЕНО (2025-12-28): Добавлены мощные отладочные логи для проверки контекста
        logger.info("=" * 80)
        logger.info("[SEARCH] ДИАГНОСТИКА КОНТЕКСТА (process_service_detection)")
        logger.info("=" * 80)
        logger.info(f"📥 message_text: '{message_text}'")
        logger.info(f"📥 original_message: '{original_message}'")
        logger.info(f"📥 is_followup: {is_followup}")
        logger.info(f"📥 dialog_history длина: {len(dialog_history) if dialog_history else 0}")

        if dialog_history and len(dialog_history) > 0:
            logger.info("[LIST] DIALOG HISTORY (последние 5 сообщений):")
            for i, msg in enumerate(dialog_history[-5:], 1):
                role = msg.get('role', 'unknown')
                text = msg.get('text', '')[:60]
                logger.info(f"  {i}. [{role}] {text}...")
        else:
            logger.info("[!]  DIALOG HISTORY ПУСТОЙ ИЛИ ОТСУТСТВУЕТ")

        logger.info("=" * 80)

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

        # ИСПРАВЛЕНО (2025-12-28): Отладочные логи до накопления
        logger.info("[SEARCH] TXTPrb И ФИЛЬТРЫ ДО накопления:")
        logger.info(f"  [NOTE] txtPrb: '{txtPrb[:80] if txtPrb else '(пусто)'}'")
        logger.info(f"  [TOOL] accumulated_fields: {accumulated_fields}")
        logger.info(f"  [TOOL] established_filters: {established_filters}")

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
                # ИСПРАВЛЕНО (2026-01-06): Передаем session_id и message_id для логирования
                accumulation_result = await self.problem_accumulator.extract_and_accumulate(
                    message_text=message_text,
                    current_problem=txtPrb,
                    bot_question=last_bot_question,
                    dialog_history=dialog_history,
                    session_id=session_id,  # ИСПРАВЛЕНО (2026-01-06)
                    message_id=message_id   # ИСПРАВЛЕНО (2026-01-06)
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

            except Exception as e:
                logger.warning(f"Ошибка ProblemAccumulationService: {e}")

        # ИСПРАВЛЕНО (2026-01-03): SemanticPreCheck - извлечение абсолютных фактов ДО поиска
        # Это позволяет оптимизировать работу микросервисов и избежать избыточных вопросов
        # ИСПРАВЛЕНО (2026-01-10): Используем txtPrb вместо search_text для полного контекста!
        semantic_check_result = {}
        if self.filter_detection and self.ai_agent and txtPrb:
            try:
                logger.info("Запускаем SemanticPreCheck для извлечения абсолютных фактов...")
                # ИСПРАВЛЕНО (2026-01-06): Передаем session_id и message_id для логирования
                # ИСПРАВЛЕНО (2026-01-10): Используем txtPrb вместо search_text (полный контекст!)
                semantic_check_result = await self._semantic_pre_check(
                    message_text=txtPrb,  # ИСПРАВЛЕНО (2026-01-10): было search_text, стало txtPrb
                    dialog_history=dialog_history,
                    session_id=session_id,
                    message_id=message_id
                )

                if semantic_check_result.get('absolute_facts'):
                    logger.info(f"SemanticPreCheck найден {len(semantic_check_result['absolute_facts'])} фактов:")
                    for fact in semantic_check_result['absolute_facts']:
                        logger.info(f"  ✓ {fact}")

                    # ИСПРАВЛЕНО (2026-01-10): Защита от переопределения фильтров с высокой уверенностью
                    # Объединяем с established_filters от ProblemAccumulationService
                    if semantic_check_result.get('filters'):
                        for filter_name, filter_data in semantic_check_result['filters'].items():
                            # ИСПРАВЛЕНО (2026-01-10): НЕ переопределяем фильтры с высокой уверенностью
                            if filter_name in established_filters:
                                existing_confidence = established_filters[filter_name].get('confidence', 0.0)
                                new_confidence = filter_data.get('confidence', 0.0)
                                # Если существующий фильтр имеет уверенность >=75% → НЕ переопределяем!
                                if existing_confidence >= 0.75:
                                    logger.info(f"  ⚠️ Фильтр {filter_name} СУЩЕСТВУЕТ с уверенностью {existing_confidence:.0%} - ПРЕНОПРЕДЕЛЯЕМSemanticPreCheck!")
                                    continue  # Пропускаем этот фильтр
                                # Иначе добавляем/обновляем
                                established_filters[filter_name] = filter_data
                                logger.info(f"  Добавлен фильтр из PreCheck: {filter_name}={filter_data['value']} (confidence: {new_confidence:.0%})")
                            else:
                                # Фильтра еще нет - добавляем
                                established_filters[filter_name] = filter_data
                                logger.info(f"  Добавлен фильтр из PreCheck: {filter_name}={filter_data['value']}")

                    # ИСПРАВЛЕНО (2026-01-05): КРИТИЧЕСКИ ВАЖНО! Добавляем semantic_check в established_filters
                    # Это нужно чтобы _generate_ai_question мог использовать absolute_facts для запрета вопросов
                    established_filters['semantic_check'] = semantic_check_result
                    logger.info("✅ semantic_check добавлен в established_filters для absolute_facts")

                else:
                    logger.info("SemanticPreCheck не нашел значимых фактов")

            except Exception as e:
                logger.warning(f"Ошибка SemanticPreCheck: {e}")
                semantic_check_result = {}

        # ИСПРАВЛЕНО (2025-12-28): Мощные отладочные логи ПОСЛЕ накопления
        logger.info("[SEARCH] TXTPrb И ФИЛЬТРЫ ПОСЛЕ накопления:")
        logger.info(f"  [NOTE] txtPrb: '{txtPrb[:120] if txtPrb else '(пусто)'}'")
        logger.info(f"  [TOOL] accumulated_fields: {json.dumps(accumulated_fields, ensure_ascii=False)}")
        logger.info(f"  [TOOL] established_filters: {json.dumps(established_filters, ensure_ascii=False)}")

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
                logger.warning(f"[!] Обнаружен повторяющийся ответ: '{repeated_answer}' (2+ раза)")

                # ИСПРАВЛЕНО (2025-12-27): ВСЕГДА меняем стратегию при повторяющихся ответах
                # Не проверяем уверенность фильтров - если пользователь повторяет, значит нужно менять вопрос!

                # Проверяем: сколько раз повторяется?
                repeat_count = 1
                for i in range(1, len(user_responses)):
                    if user_responses[i] == repeated_answer:
                        repeat_count += 1
                    else:
                        break

                logger.info(f"[!] Ответ повторяется {repeat_count} раз")

                # Меняем сообщение в зависимости от количества повторений
                if repeat_count >= 3:
                    # 3+ повторения - просим описать проблему другими словами
                    message = 'Пожалуйста, опишите проблему другими словами. Что именно случилось?'
                else:
                    # 2 повтора - задаем более конкретный вопрос
                    message = 'Уточните, пожалуйста: что именно произошло?'

                logger.info("[!] Меняем стратегию: задаем другой вопрос")

                # Возвращаем специальный результат
                # ИСПРАВЛЕНО (2026-01-06): Добавляем microservices_results для трассировки
                result_metadata = {
                    'txtPrb': txtPrb,
                    'accumulated_fields': accumulated_fields,
                    'established_filters': established_filters,
                    'repeated_answer_detected': True,
                    'repeat_count': repeat_count,
                    'semantic_check': semantic_check_result,  # ИСПРАВЛЕНО (2026-01-03)
                    'microservices_results': {}  # Пусто, т.к. микросервисы не запускались
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

        # Подготавливаем metadata для результата
        result_metadata = {
            'txtPrb': txtPrb,
            'accumulated_fields': accumulated_fields,
            'established_filters': established_filters,
            'semantic_check': semantic_check_result,  # ИСПРАВЛЕНО (2026-01-03)
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
                # ИСПРАВЛЕНО (2026-01-05): НЕ возвращаем сразу! Передаем в _create_ambiguous_result_from_candidates
                # для применения фильтров (known_location, known_incident, known_object)
                logger.info(f"AI Orchestrator требует уточнения: {orch_result.get('message')}")
                logger.info(f"Передаем {len(orch_result.get('candidates', []))} кандидатов в _create_ambiguous_result_from_candidates для фильтрации")

                # Получаем кандидатов от AI Orchestrator
                orch_candidates = orch_result.get('candidates', [])

                # Если есть кандидаты - фильтруем их
                if orch_candidates:
                    result = await self._create_ambiguous_result_from_candidates(
                        orch_candidates, original_message, is_followup, dialog_history
                    )
                    # Сохраняем AI Orchestrator message
                    result['_ai_orchestrator_message'] = orch_result.get('message')
                    # Добавляем metadata если нет
                    if '_metadata' not in result:
                        result['_metadata'] = result_metadata
                    return result
                else:
                    # Нет кандидатов - возвращаем сообщение AI Orchestrator
                    return {
                        'status': 'AMBIGUOUS',
                        'candidates': [],
                        'candidate_names': [],
                        'message': orch_result.get('message'),
                        'needs_clarification': True,
                        'is_followup': is_followup,
                        '_metadata': result_metadata
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
                    # ИСПРАВЛЕНО (2026-01-06): Передаем session_id и message_id для логирования
                    filter_result = await self.filter_detection.detect_filters(original_message, dialog_history, session_id=session_id, message_id=message_id)

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
                        before_count = len(filtered)

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

                        # ИСПРАВЛЕНО (2025-12-29): Сохраняем информацию о фильтрации (второй проход)
                        result_metadata['second_pass'] = {
                            'enabled': True,
                            'before_count': before_count,
                            'after_count': len(filtered),
                            'applied_filters': {
                                k: v for k, v in filters.items() if v
                            }
                        }

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

            # ИСПРАВЛЕНО (2025-12-29): Получаем результат и добавляем metadata
            result = await self._create_ambiguous_result_from_candidates(candidates_data, original_message, is_followup, dialog_history)

            # Добавляем metadata если его нет
            if '_metadata' not in result and 'result_metadata' in locals():
                result['_metadata'] = result_metadata

            return result

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
        # ИСПРАВЛЕНО (2026-01-05): Отладочный лог
        logger.info(f"[DEBUG] _create_ambiguous_result_from_candidates ВХОД: {len(candidates_data)} кандидатов")

        # ИСПРАВЛЕНО (2026-01-05): Безопасная сортировка - candidates могут не иметь 'sources'
        try:
            candidates_data.sort(key=lambda x: len(x.get('sources', [])), reverse=True)
        except Exception as e:
            logger.warning(f"Ошибка сортировки кандидатов: {e}")
            # Если не получается сортировать по sources - сортируем по service_id
            candidates_data.sort(key=lambda x: x.get('service_id', 0))

        candidate_names = [c['service_name'] for c in candidates_data[:5]]

        logger.info(f"Формируем запрос уточнения из {len(candidates_data)} кандидатов")

        # ИСПРАВЛЕНО: Загружаем атрибуты из БД вместо пустых значений
        candidates_with_attrs = await self._load_candidates_attributes(candidates_data[:5])

        # Генерируем умный уточняющий вопрос с учетом истории
        clarification_result = await self._generate_smart_clarification(candidates_with_attrs, original_message, is_followup, dialog_history)

        # ИСПРАВЛЕНО: Если после фильтрации остался 1 кандидат - возвращаем SUCCESS
        if clarification_result.get('status') == 'SUCCESS' and clarification_result.get('single_candidate'):
            candidate = clarification_result['single_candidate']
            result = {
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
            # ИСПРАВЛЕНО (2025-12-29): Добавляем _ai_metadata если есть
            if '_ai_metadata' in clarification_result:
                result['_ai_metadata'] = clarification_result['_ai_metadata']
            return result

        # ИСПРАВЛЕНО (2025-12-25): Используем отфильтрованных кандидатов
        filtered_candidates = clarification_result.get('filtered_candidates', candidates_with_attrs)

        result = {
            'status': 'AMBIGUOUS',
            'candidates': filtered_candidates,  # ИСПРАВЛЕНО: отфильтрованные кандидаты
            'candidate_names': [c.get('service_name', c.get('scenario_name', 'Unknown')) for c in filtered_candidates],
            'message': clarification_result['message'],
            'needs_clarification': True,
            'clarification_type': 'candidates',  # ИСПРАВЛЕНО (2026-01-05): было 'no_intersection'
            'is_followup': is_followup
        }
        # ИСПРАВЛЕНО (2025-12-29): Добавляем _ai_metadata если есть
        if '_ai_metadata' in clarification_result:
            result['_ai_metadata'] = clarification_result['_ai_metadata']
        return result

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
                            # ИСПРАВЛЕНО (2026-01-06): Передаем session_id для логирования
                            future = pool.submit(asyncio.run, self.filter_detection.detect_filters(message_text, dialog_history or [], session_id=session_id))
                            return future.result()
                    else:
                        # ИСПРАВЛЕНО (2026-01-06): Передаем session_id для логирования
                        return asyncio.run(self.filter_detection.detect_filters(message_text, dialog_history or [], session_id=session_id))

                filter_result = call_filter_sync()
                if filter_result.get('status') == 'success':
                    filter_svc_filters = filter_result.get('filters', {})
                    # Если FilterDetectionService вернул значения - используем их
                    if filter_svc_filters.get('location_type'):
                        filters['location_type'] = filter_svc_filters['location_type']
                    if filter_svc_filters.get('category'):
                        filters['category'] = filter_svc_filters['category']
                    # ИСПРАВЛЕНО (2026-01-06): Используем incident_type вместо incident
                    # filters['incident'] создавало путаницу - дублирование с incident_type
                    if filter_svc_filters.get('incident_type'):
                        filters['incident_type'] = filter_svc_filters['incident_type']
                    if filter_svc_filters.get('object_description'):
                        filters['object_description'] = filter_svc_filters['object_description']
                        logger.info(f"FilterDetectionService извлек object_description: {filters['object_description']}")
            except Exception as e:
                logger.warning(f"Ошибка вызова FilterDetectionService: {e}")

        # УДАЛЕНО (2025-12-25): Весь fallback хардкод keywords удален
        # FilterDetectionService теперь является единственным источником фильтров
        # Это соответствует архитектуре без хардкода данных

        return filters

    async def _generate_smart_clarification(self, candidates_with_attrs: List[Dict], original_message: str = "", is_followup: bool = False, dialog_history: List[Dict] = None, txtPrb: str = None, established_filters: Dict = None, session_id: str = None) -> Dict:
        """
        Генерирует умный уточняющий вопрос на основе анализа атрибутов кандидатов

        Логика: находит ключевые различия в атрибутах (location_type, category, incident_type)
        и задает вопрос именно по этим параметрам, НЕ перечисляя услуги

        ИСПРАВЛЕНО: Добавлен анализ истории диалога для исключения уже отвеченных вопросов
        ИСПРАВЛЕНО: Возвращает Dict с status вместо строки
        ИСПРАВЛЕНО (2025-12-25): Возвращает filtered_candidates для итеративного уточнения
        ИСПРАВЛЕНО (2025-12-28): Добавлены параметры txtPrb и established_filters для передачи в LLM
        ИСПРАВЛЕНО (2025-12-28): Извлечение txtPrb и established_filters из dialog_history если не переданы
        """
        # ИСПРАВЛЕНО (2025-12-28): Если txtPrb и established_filters не переданы - извлекаем из истории
        if not txtPrb and dialog_history and self.problem_accumulator:
            try:
                txtPrb = self.problem_accumulator.get_txtPrb_from_metadata(dialog_history)
                logger.info(f"_generate_smart_clarification: извлечен txtPrb из истории: '{txtPrb[:60] if txtPrb else '(пусто)'}...'")
            except Exception as e:
                logger.warning(f"_generate_smart_clarification: ошибка извлечения txtPrb: {e}")

        # ИСПРАВЛЕНО (2025-12-28): Добавляем отладочные логи
        logger.info("[SEARCH] _generate_smart_clarification ДИАГНОСТИКА:")
        logger.info(f"  [NOTE] txtPrb: '{txtPrb[:80] if txtPrb else '(не передан)'}'")
        logger.info(f"  [TOOL] established_filters: {established_filters if established_filters else '(не переданы)'}")
        logger.info(f"  [LIST] dialog_history: {len(dialog_history) if dialog_history else 0} сообщений")

        if not candidates_with_attrs:
            context = {
                'original_message': original_message,
                'dialog_history': dialog_history or []
            }
            # ИСПРАВЛЕНО (2025-12-28): Заменен hardcoded на AI + ПЕРЕДАЕМ txtPrb и established_filters
            # ИСПРАВЛЕНО (2026-01-06): Передаем session_id для логирования
            message = await self._generate_ai_question(
                context=context.get('original_message', ''),
                dialog_history=context.get('dialog_history', []),
                candidates=None,
                established_filters=established_filters,  # ИСПРАВЛЕНО
                txtPrb=txtPrb,  # ИСПРАВЛЕНО
                question_type='clarification',
                session_id=session_id  # ИСПРАВЛЕНО (2026-01-06)
            )
            return {
                'status': 'AMBIGUOUS',
                'message': message,
                'single_candidate': None,
                'filtered_candidates': []
            }

        # ИЗВЛЕКАЕМ ФИЛЬТРЫ ИЗ СООБЩЕНИЯ ПОЛЬЗОВАТЕЛЯ И ИСТОРИИ ДИАЛОГА
        extracted_filters = self._extract_filters_from_message(original_message, dialog_history)
        known_location = extracted_filters.get('location')  # ИСПРАВЛЕНО (2026-01-10): использую .get()
        known_category = extracted_filters.get('category')  # ИСПРАВЛЕНО (2026-01-10): использую .get()
        known_incident = extracted_filters.get('incident_type')  # ИСПРАВЛЕНО (2026-01-10): БАГ! было 'incident'
        known_object = extracted_filters.get('object_description', '')  # ИСПРАВЛЕНО (2025-12-25)

        logger.info(f"Извлеченные фильтры: location={known_location}, category={known_category}, incident_type={known_incident}, object={known_object}")

        # Фильтруем кандидатов на основе известной информации
        filtered_candidates = candidates_with_attrs
        if known_location:
            filtered_candidates = [c for c in filtered_candidates if known_location in c.get('location_type', '')]
            logger.info(f"Отфильтровано по location_type={known_location}: {len(filtered_candidates)} из {len(candidates_with_attrs)}")

        if known_category:
            # ИСПРАВЛЕНО (2026-01-05): ОТКЛЮЧЕНО! Category фильтр слишком опасен
            # Проблема: "прорвало трубу" → category=Водоснабжение (НО труба может быть канализации/отопления!)
            # Решение: НЕ фильтруем по category, передаем в AI для уточнения
            logger.info(f"[!] Фильтр category={known_category} ПРОПУСКАЕМ (трубы бывают разными!)")
            # Если очень нужно фильтровать, ТОЛЬКО при confidence >= 0.95:
            # if known_category_confidence >= 0.95:
            #     filtered_candidates = [c for c in filtered_candidates if known_category.lower() in c.get('category', '').lower()]
            #     logger.info(f"Отфильтровано по category={known_category}: {len(filtered_candidates)} из {len(candidates_with_attrs)}")

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
                                        dialog_history=dialog_history,
                                        session_id=session_id  # ИСПРАВЛЕНО (2026-01-06)
                                    )
                                )
                                return future.result()
                        # ИСПРАВЛЕНО (2026-01-06): Передаем session_id для логирования
                        return asyncio.run(
                            self.filter_detection.rank_candidates_by_relevance(
                                message_text=original_message,
                                candidates=filtered_candidates,
                                dialog_history=dialog_history,
                                session_id=session_id  # ИСПРАВЛЕНО (2026-01-06)
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

            # ИСПРАВЛЕНИЕ (2026-01-06): Проверяем - ВСЕ ЛИ важные фильтры установлены
            # Если у кандидата ЕСТЬ category/location/incident в services_catalog,
            # но FilterDetectionService НЕ установил их (confidence < 0.6) → нужно уточнить

            # Проверяем category
            candidate_category = candidate.get('category', '')
            category_filter = established_filters.get('category', {})
            category_confidence = category_filter.get('confidence', 0.0) if isinstance(category_filter, dict) else 0.0
            category_value = category_filter.get('value', '') if isinstance(category_filter, dict) else ''

            # Если у услуги ЕСТЬ категория в БД, но НЕ установлена в фильтрах
            needs_category_clarification = (
                candidate_category and  # В БД есть категория
                category_confidence < 0.6  # Но FilterDetectionService НЕ установил (или низкая уверенность)
            )

            if needs_category_clarification:
                logger.warning(f"[КАТЕГОРИЯ] У услуги '{candidate['service_name']}' есть category='{candidate_category}' в БД, но НЕ установлена в фильтрах (confidence={category_confidence})")
                logger.warning(f"[КАТЕГОРИЯ] Нужно уточнить категорию перед SUCCESS")

                # Генерируем вопрос через AI (без хардкода!)
                return await self._ask_about_missing_attribute(
                    candidate=candidate,
                    attribute_name='category',
                    attribute_value=candidate_category,
                    dialog_history=dialog_history,
                    txtPrb=txtPrb,
                    established_filters=established_filters
                )

            # ИСПРАВЛЕНО (2025-12-25): Добавляем needs_confirmation для низкого confidence
            # Получаем confidence из LLM ранжирования если было
            llm_confidence = ranking_result.get('confidence', 0.0) if 'ranking_result' in locals() else 0.0

            # ИСПРАВЛЕНО (2026-01-05): Проверяем - был ли уже подтверждающий вопрос
            already_asked_confirmation = False
            if dialog_history:
                for msg in dialog_history:
                    is_bot = msg.get('direction') == 'outbound' or msg.get('role') == 'bot'
                    if is_bot:
                        text = msg.get('message_text', '') or msg.get('text', '')
                        if 'правильно ли я понял' in text.lower() or 'подтверд' in text.lower():
                            already_asked_confirmation = True
                            logger.info(f"[!] УЖЕ был подтверждающий вопрос: '{text[:60]}...'")
                            break

            # Если confidence < 0.9 И еще НЕ спрашивали подтверждение - спрашиваем
            # Если УЖЕ спрашивали - НЕ повторяем, сразу создаем заявку
            needs_confirmation = llm_confidence < 0.9 and not already_asked_confirmation

            # Формируем сообщение
            if needs_confirmation:
                message = f"Правильно ли я понял, что у вас: {candidate['service_name']}?"
            else:
                # Если уже спрашивали подтверждение - сообщаем что создаем заявку
                if already_asked_confirmation:
                    message = f"Создаю заявку: {candidate['service_name']}"
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
        # ИСПРАВЛЕНО (2025-12-28): ПЕРЕДАЕМ txtPrb и established_filters
        # ИСПРАВЛЕНО (2025-12-29): Получаем Dict с вопросом И метаданными
        # ИСПРАВЛЕНО (2026-01-06): Передаем session_id для логирования
        ai_result = await self._generate_ai_question(
            context=context,
            dialog_history=dialog_history,
            candidates=filtered_candidates,
            established_filters=established_filters,  # ИСПРАВЛЕНО
            txtPrb=txtPrb,  # ИСПРАВЛЕНО
            question_type='clarification',
            session_id=session_id  # ИСПРАВЛЕНО (2026-01-06)
        )

        return {
            'status': 'AMBIGUOUS',
            'message': ai_result['question'],
            'single_candidate': None,
            'filtered_candidates': filtered_candidates,
            '_ai_metadata': {  # ИСПРАВЛЕНО (2025-12-29): Сохраняем метаданные для трассировки
                'prompt': ai_result['prompt'],
                'response': ai_result['response'],
                'model': ai_result['model'],
                'usage': ai_result['usage']
            }
        }

    async def _run_ai_search(self, message_text: str) -> Dict:
        """Запуск AIAgentService"""
        try:
            return await self.ai_agent.search(message_text)
        except Exception as e:
            logger.error(f"Ошибка AIAgentService: {e}")
            return {}

    def _merge_candidates(self, candidates: List[Dict]) -> List[Dict]:
        """Дедупликация и объединение кандидатов

        ИСПРАВЛЕНО (2025-12-28): Копируем location_type, incident_type, category из all_data[0]
        """
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
                # ИСПРАВЛЕНО (2025-12-28): Копируем candidate И атрибуты из all_data[0]
                merged_candidate = candidate.copy()

                # Копируем атрибуты из all_data[0] если они есть
                if 'all_data' in candidate and len(candidate['all_data']) > 0:
                    first_data = candidate['all_data'][0]
                    if 'location_type' in first_data:
                        merged_candidate['location_type'] = first_data['location_type']
                    if 'incident_type' in first_data:
                        merged_candidate['incident_type'] = first_data['incident_type']
                    if 'category' in first_data:
                        merged_candidate['category'] = first_data['category']

                service_map[service_id] = merged_candidate

        merged = list(service_map.values())

        # Сортируем по уверенности убыванию
        merged.sort(key=lambda x: x.get('confidence', 0), reverse=True)

        logger.info(f"Дедуплицировано кандидатов: {len(merged)}")
        return merged

    async def _create_ambiguous_result(self, candidates: List[Dict], original_message: str = "", is_followup: bool = False, dialog_history: List[Dict] = None, session_id: str = None) -> Dict:
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
            # ИСПРАВЛЕНО (2025-12-28): Заменен hardcoded на AI
            # ИСПРАВЛЕНО (2026-01-06): Передаем session_id для логирования
            clarification_message = await self._generate_ai_question(
                context=context.get('original_message', ''),
                dialog_history=context.get('dialog_history', []),
                candidates=None,
                established_filters=None,
                question_type='clarification',
                session_id=session_id  # ИСПРАВЛЕНО (2026-01-06)
            )
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
                    # ИСПРАВЛЕНО (2025-12-28): Открытый вопрос без перечисления комнат
                    return "Уточните, пожалуйста: где именно течет?"
                elif any(word in all_answers for word in ['батарей', 'отопл', 'радиатор']):
                    return "Где именно течет?"
                else:
                    # ИСПРАВЛЕНО (2025-12-28): Открытый вопрос без перечисления
                    return "Уточните, откуда именно течет?"
            elif any(word in all_answers for word in ['сломал', 'не работ', 'испортил']):
                return "Опишите подробнее, что именно сломалось."

            # Если ответ очень короткий (1-2 слова) - просим больше деталей
            # ИСПРАВЛЕНО (2025-12-28): Открытый вопрос вместо двойного
            if len(last_user_answers) > 0 and len(last_user_answers[-1].split()) <= 2:
                return "Опишите подробнее, что именно произошло."

        # Проверяем количество повторов одного и того же
        if len(recent_bot_questions) >= 2:
            # Если последние 2+ вопроса от бота одинаковы
            if len(set(q.lower() for q in recent_bot_questions[:2])) <= 1:
                logger.warning("Detected repeated bot questions, changing strategy")
                # ИСПРАВЛЕНО (2025-12-28): Открытый вопрос вместо двойного
                return "Пожалуйста, опишите проблему другими словами. Что именно произошло?"

        # Default fallback
        if is_followup:
            return "Уточните детали проблемы."
        return "Опишите подробнее, что именно произошло."

    async def _ask_about_missing_attribute(
        self,
        candidate: Dict,
        attribute_name: str,
        attribute_value: str,
        dialog_history: List[Dict],
        txtPrb: str,
        established_filters: Dict
    ) -> Dict:
        """
        Генерирует уточняющий вопрос о пропущенном атрибуте через AI

        ИСПРАВЛЕНИЕ (2026-01-06): БЕЗ хардкода! Использует AI для генерации вопроса

        Args:
            candidate: Кандидат-услуга
            attribute_name: Имя атрибута ('category', 'location_type', etc.)
            attribute_value: Значение атрибута из БД
            dialog_history: История диалога
            txtPrb: Накопленное описание проблемы
            established_filters: Установленные фильтры

        Returns:
            Dict: AMBIGUOUS с сгенерированным вопросом
        """
        try:
            # Формируем промпт для AI
            prompt = f"""Ты - диспетчер управляющей компании. У пользователя проблема.

НАКОПЛЕННАЯ ИНФОРМАЦИЯ:
{txtPrb}

УСТАНОВЛЕННЫЕ ФИЛЬТРЫ:
- location: {established_filters.get('location_type', {}).get('value', 'неизвестно')}
- incident: {established_filters.get('incident_type', {}).get('value', 'неизвестно')}
- category: {established_filters.get('category', {}).get('value', 'НЕ УСТАНОВЛЕНО')} ← ПРОБЛЕМА!

ПРЕДВАРИТЕЛЬНАЯ УСЛУГА:
{candidate['service_name']} (категория: {attribute_value})

ЗАДАЧА:
Пользователь НЕ указал категорию проблемы (водоснабжение/отопление/канализация/и т.д.).
Задай ЕДИНСТВЕННЫЙ вопрос чтобы уточнить категорию.

ВАЖНО:
- Вопрос должен быть КРАТКИМ (1 предложение)
- НЕ используй эмодзи
- НЕ перечисляй варианты - дай пользователю ответить свободно
- Вопрос должен помогать определить категорию из контекста

ПРИМЕРЫ ПРАВИЛЬНЫХ ВОПРОСОВ:
- "Уточните, пожалуйста: к какой системе относится проблема?"
- "Что именно является источником проблемы?"
- "Какой элемент неисправен?"

Верни ТОЛЬКО текст вопроса (без кавычек и пояснений)."""

            # Вызываем LLM
            response, usage = await self.ai_agent.call_llm(
                prompt=prompt,
                provider='yandexgpt',
                model='lite'
            )

            question = response.strip().strip('\'"').strip()

            logger.info(f"[AI QUESTION] Сгенерирован вопрос о category: '{question}'")

            return {
                'status': 'AMBIGUOUS',
                'message': question,
                'single_candidate': None,
                'filtered_candidates': [candidate],
                'needs_clarification': True,
                'is_followup': True,
                '_metadata': {
                    'clarification_reason': f'missing_attribute_{attribute_name}',
                    'attribute_name': attribute_name,
                    'attribute_value': attribute_value,
                    'service_name': candidate['service_name'],
                    'ai_generated_question': True
                }
            }

        except Exception as e:
            logger.error(f"Ошибка генерации вопроса о {attribute_name}: {e}")
            # Fallback вопрос
            return {
                'status': 'AMBIGUOUS',
                'message': f'Уточните, пожалуйста: к какой категории относится проблема?',
                'single_candidate': None,
                'filtered_candidates': [candidate],
                'needs_clarification': True,
                'is_followup': True
            }

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
        logger.info(f"[GEAR] _orchestrate_microservices: established_filters={established_filters}")

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
                # ИСПРАВЛЕНО (2026-01-05): Передаем established_filters
                return await self._ask_ai_clarification(
                    message_text, unique_candidates, dialog_history, established_filters
                )

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
                                    established_filters: Dict = None, txtPrb: str = None, session_id: str = None) -> str:
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
        # ИСПРАВЛЕНО (2025-12-29): Получаем Dict с вопросом И метаданными
        # ИСПРАВЛЕНО (2026-01-06): Передаем session_id для логирования
        context = f"Пользователь написал: {message_text}"
        ai_result = await self._generate_ai_question(
            context=context,
            dialog_history=dialog_history,
            established_filters=established_filters,
            txtPrb=txtPrb,
            question_type='what_happened',
            session_id=session_id  # ИСПРАВЛЕНО (2026-01-06)
        )

        question = ai_result['question']
        logger.info(f"AI сгенерировал вопрос (turn={dialog_turn}, followup={is_followup}): {question}")

        # ИСПРАВЛЕНО (2025-12-29): Сохраняем метаданные AI для трассировки в result_metadata
        # result_metadata должен быть доступен в области видимости этого метода
        # Проверяем есть ли result_metadata в замыкании или передаем как параметр

        return question

    async def _llm_validate_question(
        self,
        question: str,
        txtPrb: str = None,
        established_filters: Dict = None
    ) -> str:
        """
        ИСПРАВЛЕНО (2026-01-03): LLM-валидация вопроса вместо Regex

        Проверяет через YandexGPT Lite:
        1. Не спрашивает ли бот о том, что уже известно
        2. Не является ли вопрос двойным

        Args:
            question: Сгенерированный вопрос
            txtPrb: Накопленное описание проблемы
            established_filters: Установленные фильтры

        Returns:
            str: Валидированный вопрос
        """
        if not question or not self.ai_agent:
            return question

        # Формируем абсолютные факты для промпта
        absolute_facts = []
        if txtPrb:
            absolute_facts.append(f"Описание проблемы: {txtPrb}")

        if established_filters:
            for filter_name, filter_data in established_filters.items():
                if isinstance(filter_data, dict) and filter_data.get('value'):
                    confidence = filter_data.get('confidence', 0)
                    if confidence > 0.8:
                        absolute_facts.append(f"{filter_name}={filter_data['value']} (уверенность: {confidence:.0%})")

        # Если нет известных фактов - пропускаем валидацию
        if not absolute_facts:
            return question

        # Формируем промпт для валидации
        facts_text = "\n".join([f"  - {fact}" for fact in absolute_facts])

        # ИСПРАВЛЕНО (2026-01-03): Улучшенный промпт с примерами и строгими правилами
        # ИСПРАВЛЕНО (2026-01-03): Проверка что текст является вопросом
        prompt = f"""Ты - строгий логический валидатор вопросов AI-диспетчера.

ВОПРОС БОТА: "{question}"

ИЗВЕСТНЫЕ ФАКТЫ (ЗАПРЕЩЕНО СПРАШИВАТЬ ОБ ЭТОМ):
{facts_text}

КРИТИЧЕСКИЕ ПРАВИЛА ВАЛИДАЦИИ:

0. ПРОВЕРКА ЧТО ЭТО ВОПРОС:
   Текст ДОЛЖЕН быть вопросом (заканчиваться на "?").

   ПРИМЕРЫ НЕВОПРОСОВ (ОТКЛОНИТЬ):
   - "Нет необходимости уточнять локацию." → НЕ ВОПРОС (утверждение)
   - "Я понял проблему." → НЕ ВОПРОС
   - "Все понятно." → НЕ ВОПРОС

   ПРИМЕРЫ ВОПРОСОВ (ПРИНЯТЬ):
   - "Где именно это произошло?" → ВОПРОС
   - "Опишите что именно сломалось?" → ВОПРОС

1. ПРОВЕРКА НА ИЗБЫТОЧНОСТЬ:
   Вопрос ИЗБЫТОЧЕН, если он спрашивает о том, что УЖЕ есть в "Известных фактах".

   ПРИМЕРЫ ИЗБЫТОЧНЫХ ВОПРОСОВ:
   - Если факт: "location=зал", вопрос "Где именно?" → ИЗБЫТОЧЕН
   - Если факт: "category=Отопление", вопрос "Это отопление?" → ИЗБЫТОЧЕН
   - Если факт: "Проблема: течет", вопрос "Что случилось?" → ИЗБЫТОЧЕН
   - Если факт: "object=батарея", вопрос "Что именно течет?" → ИЗБЫТОЧЕН

   ПРАВИЛО: Любой вопрос о локации/объекте/категории, которая УЖЕ УКАЗАНА в фактах → ИЗБЫТОЧЕН.

2. ПРОВЕРКА НА ДВОЙНОЙ ВОПРОС:
   Вопрос ДВОЙНОЙ, если содержит два разных вопроса через "и", "или", запятую.

   ПРИМЕРЫ ДВОЙНЫХ ВОПРОСОВ:
   - "Что и где именно?" → ДВОЙНОЙ (Что? + Где?)
   - "Опишите что и где это произошло" → ДВОЙНОЙ
   - "Какой объект и в каком месте?" → ДВОЙНОЙ

3. ПРОВЕРКА НА УТОЧНЕНИЕ УЖЕ ИЗВЕСТНОГО:
   Если в фактах указана конкретика, а вопрос просит "уточнить" это → ИЗБЫТОЧЕН.

   ПРИМЕРЫ:
   - Факт: "Проблема: течет из трубы", вопрос: "Уточните что течет?" → ИЗБЫТОЧЕН
   - Факт: "location=Индивидуальное", вопрос: "В квартире или общедомовое?" → ИЗБЫТОЧЕН

РЕШЕНИЕ:
- Если текст НЕ ВОПРОС → {{"valid": false, "reason": "не является вопросом", "fixed_question": "Хороший уточняющий вопрос"}}
- Если вопрос ИЗБЫТОЧНЫЙ или ДВОЙНОЙ → {{"valid": false, "reason": "описание ошибки", "fixed_question": "лучший вопрос"}}
- Если вопрос НОРМАЛЬНЫЙ → {{"valid": true}}

При генерации fixed_question:
- Если исходный текст НЕ ВОПРОС - сгенерируй хороший уточняющий вопрос по контексту
- Убирай избыточную часть
- Разбивай двойной вопрос на один основной
- Сохраняй смысл, но задавай только ОДИН вопрос

Верни только JSON, без другого текста.

JSON:"""

        try:
            # Вызываем YandexGPT Lite для валидации
            response, usage = await self.ai_agent.call_llm(
                prompt=prompt,
                provider='yandexgpt',
                model='lite'
            )

            import json
            if '{' in response:
                # Извлекаем JSON
                start = response.find('{')
                end = response.rfind('}') + 1
                json_str = response[start:end]
                result = json.loads(json_str)

                if result.get('valid'):
                    logger.info(f"LLM-валидация: вопрос корректен")
                    return question
                else:
                    reason = result.get('reason', 'неизвестно')
                    fixed = result.get('fixed_question', question)
                    logger.warning(f"LLM-валидация: обнаружена ошибка - {reason}")
                    logger.info(f"LLM-валидация: исправленный вопрос - {fixed}")
                    return fixed

        except Exception as e:
            logger.error(f"Ошибка LLM-валидации вопроса: {e}")

        # При ошибке возвращаем оригинал
        return question

    async def _semantic_pre_check(
        self,
        message_text: str,
        dialog_history: List[Dict] = None,
        session_id: str = None,
        message_id: int = None
    ) -> Dict:
        """
        ИСПРАВЛЕНО (2026-01-03): Семантический Pre-Check через FilterDetectionService

        Извлекает "абсолютные факты" из текста через YandexGPT Lite:
        - Проблема (течет, сломалось, засор и т.д.)
        - Локация (зал -> Индивидуальное, подъезд -> Общедомовое)
        - Категория (батарея -> Отопление)
        - Объект (труба, кран, батарея)

        ИСПРАВЛЕНО (2026-01-03): Добавлено кеширование результатов
        ИСПРАВЛЕНО (2026-01-06): Добавлен message_id для логирования

        Args:
            message_text: Текст сообщения
            dialog_history: История диалога
            session_id: ID сессии
            message_id: ID сообщения для логирования LLM

        Returns:
            Dict: {
                'absolute_facts': List[str],  # Список фактов
                'filters': Dict,               # Фильтры с confidence
                'normalized_fields': Dict      # Нормализованные поля
            }
        """
        if not self.filter_detection or not self.ai_agent:
            return {
                'absolute_facts': [],
                'filters': {},
                'normalized_fields': {}
            }

        # ИСПРАВЛЕНО (2026-01-03): Кеширование результатов
        # Используем хеш текста сообщения как ключ кеша
        import hashlib
        cache_key = hashlib.md5(message_text.encode()).hexdigest()

        # Проверяем кеш
        if not hasattr(self, '_semantic_pre_check_cache'):
            self._semantic_pre_check_cache = {}

        if cache_key in self._semantic_pre_check_cache:
            logger.info(f"SemanticPreCheck: результат из кеша (key: {cache_key[:8]}...)")
            return self._semantic_pre_check_cache[cache_key]

        try:
            # Вызываем FilterDetectionService (уже использует YandexGPT Lite)
            # ИСПРАВЛЕНО (2026-01-06): Передаем session_id и message_id для логирования
            filter_result = await self.filter_detection.detect_filters(
                message_text=message_text,
                dialog_history=dialog_history,
                session_id=session_id,
                message_id=message_id
            )

            if filter_result.get('status') != 'success':
                return {
                    'absolute_facts': [],
                    'filters': {},
                    'normalized_fields': {}
                }

            filters = filter_result.get('filters', {})
            confidence = filter_result.get('confidence', 0.0)

            # Формируем абсолютные факты
            absolute_facts = []
            normalized_fields = {}

            # Проблема (из object_description)
            if filters.get('object_description'):
                problem_desc = filters['object_description']
                absolute_facts.append(f"Проблема: {problem_desc}")
                normalized_fields['problem'] = problem_desc

            # Локация (нормализация: зал/кухня/ванная -> Индивидуальное)
            if filters.get('location_type'):
                location = filters['location_type']
                absolute_facts.append(f"Локация: {location}")
                normalized_fields['location'] = location

            # Категория
            if filters.get('category'):
                category = filters['category']
                absolute_facts.append(f"Категория: {category}")
                normalized_fields['category'] = category

            # Тип инцидента
            if filters.get('incident_type'):
                incident = filters['incident_type']
                absolute_facts.append(f"Тип: {incident}")
                normalized_fields['incident'] = incident

            # Логируем результаты
            logger.info(f"SemanticPreCheck: извлечено {len(absolute_facts)} фактов")
            for fact in absolute_facts:
                logger.info(f"  - {fact}")

            result = {
                'absolute_facts': absolute_facts,
                'filters': {
                    k: {'value': v, 'confidence': confidence}
                    for k, v in filters.items() if v
                },
                'normalized_fields': normalized_fields,
                'confidence': confidence,
                'raw_response': filter_result
            }

            # ИСПРАВЛЕНО (2026-01-03): Сохраняем в кеш
            self._semantic_pre_check_cache[cache_key] = result
            # Ограничиваем размер кеша (максимум 50 записей)
            if len(self._semantic_pre_check_cache) > 50:
                # Удаляем самую старую запись (первую)
                oldest_key = next(iter(self._semantic_pre_check_cache))
                del self._semantic_pre_check_cache[oldest_key]
                logger.info(f"SemanticPreCheck: кеш очищен (удалена старая запись)")

            return result

        except Exception as e:
            logger.error(f"Ошибка в _semantic_pre_check: {e}")
            return {
                'absolute_facts': [],
                'filters': {},
                'normalized_fields': {}
            }

    def _determine_strategy(
        self,
        candidates: List[Dict] = None,
        established_filters: Dict = None
    ) -> str:
        """
        ИСПРАВЛЕНО (2026-01-03): Определение стратегии по количеству кандидатов

        Стратегии:
        - A: 1 кандидат с уверенностью >90% → Подтверждение
        - B: 2-10 кандидатов → Уточнение по списку
        - C: >10 кандидатов → Фильтрация без списка

        Args:
            candidates: Список кандидатов услуг
            established_filters: Установленные фильтры

        Returns:
            str: Стратегия ('A', 'B', или 'C')
        """
        # ИСПРАВЛЕНО (2026-01-06): Если нет кандидатов - НЕ используем стратегию C
        # Стратегия C требует_candidates_для анализа различий
        if not candidates or len(candidates) == 0:
            # Возвращаем специальный код для режима "без кандидатов"
            return 'NONE'  # Нет кандидатов - используем альтернативную логику

        count = len(candidates)

        # ИСПРАВЛЕНИЕ (2026-01-05): 1 кандидат = стратегия A (подтверждение)
        # Не важно какой confidence - если остался 1 кандидат после фильтрации,
        # значит нужно подтвердить, а не уточнять
        if count == 1:
            return 'A'  # Подтверждение (всегда для 1 кандидата)

        # Стратегия B: 2-10 кандидатов
        if count <= 10:
            return 'B'

        # Стратегия C: >10 кандидатов
        return 'C'

    def _determine_missing_filter(
        self,
        candidates: List[Dict],
        established_filters: Dict
    ) -> str:
        """
        ИСПРАВЛЕНО (2026-01-03): Определение недостающего фильтра

        Анализирует какие фильтры установлены, а какие нет,
        и возвращает название недостающего фильтра для стратегии C.

        Args:
            candidates: Список кандидатов
            established_filters: Установленные фильтры

        Returns:
            str: Недостающий фильтр ('ЛОКАЦИЯ', 'КАТЕГОРИЯ', 'ОБЪЕКТ', или 'ТИП')
        """
        # Проверяем какие фильтры не установлены
        # ИСПРАВЛЕНО (2026-01-05): Используем правильные ключи из established_filters
        has_location = established_filters.get('location_type')
        has_category = established_filters.get('category')
        has_object = established_filters.get('object_description')
        has_incident = established_filters.get('incident_type')

        # Анализируем кандидатов чтобы понять что varies больше всего
        if candidates and len(candidates) > 0:
            # Собираем уникальные значения
            locations = set(c.get('location_type') for c in candidates if c.get('location_type'))
            categories = set(c.get('category') for c in candidates if c.get('category'))
            objects = set(c.get('object_type') for c in candidates if c.get('object_type'))
            incidents = set(c.get('incident_type') for c in candidates if c.get('incident_type'))

            # Находим параметр с наибольшим разнообразием
            max_var = 0
            missing = 'ЛОКАЦИЯ'

            if not has_location and len(locations) > max_var:
                max_var = len(locations)
                missing = 'ЛОКАЦИЯ'
            if not has_category and len(categories) > max_var:
                max_var = len(categories)
                missing = 'КАТЕГОРИЯ'
            if not has_object and len(objects) > max_var:
                max_var = len(objects)
                missing = 'ОБЪЕКТ'
            if not has_incident and len(incidents) > max_var:
                max_var = len(incidents)
                missing = 'ТИП'

            return missing

        # Если нет кандидатов, проверяем по очереди
        if not has_location:
            return 'ЛОКАЦИЯ'
        if not has_category:
            return 'КАТЕГОРИЯ'
        if not has_object:
            return 'ОБЪЕКТ'
        return 'ТИП'

    def _extract_asked_questions(self, dialog_history: List[Dict]) -> List[str]:
        """
        ИСПРАВЛЕНО (2026-01-05): Извлекает вопросы которые бот уже задал
        ИСПРАВЛЕНО (2026-01-05): Поддержка обеих структур истории (direction и role)

        Args:
            dialog_history: История диалога

        Returns:
            List[str]: Список уже заданных вопросов
        """
        if not dialog_history:
            return []

        asked = []
        for msg in dialog_history:
            # ИСПРАВЛЕНО (2026-01-05): Поддержка обеих структур
            # Структура 1: {'direction': 'outbound', ...} (реальный бот)
            # Структура 2: {'role': 'bot', ...} (тестовый симулятор)
            is_bot_message = (
                msg.get('direction') == 'outbound' or  # реальный бот
                msg.get('role') == 'bot'  # тестовый симулятор
            )

            if is_bot_message:
                text = msg.get('message_text', '') or msg.get('text', '')
                if text and text.strip():
                    # Убираем технические фразы, оставляем только вопросы
                    text = text.strip()
                    # ИСПРАВЛЕНО (2026-01-05): Пропускаем только приветствия и системные сообщения
                    # НЕ пропускаем вопросы с "понял" - это уточняющие вопросы!
                    skip_phrases = ['добрый день', 'здравствуйте', 'опишите вашу проблему', 'создана заявка']
                    if not any(skip in text.lower() for skip in skip_phrases):
                        # Дополнительная проверка: пропускаем сообщения без вопросительного знака и короткие
                        # которые не являются вопросами (чистые факты)
                        is_short_fact = (
                            len(text.split()) < 5 and  # короткое
                            '?' not in text and  # без вопросительного знака
                            not any(word in text.lower() for word in ['что', 'где', 'когда', 'как', 'почему', 'уточните', 'опишите'])  # без вопросительных слов
                        )
                        if not is_short_fact:
                            asked.append(text)

        logger.info(f"_extract_asked_questions: извлечено {len(asked)} заданных вопросов")
        for i, q in enumerate(asked, 1):
            logger.info(f"  Вопрос #{i}: {q}")

        return asked

    def _build_dynamic_prompt(
        self,
        strategy: str,
        context: str,
        absolute_facts: List[str] = None,
        candidates: List[Dict] = None,
        missing_filter: str = None,
        txtPrb: str = None,
        asked_questions: List[str] = None
    ) -> str:
        """
        ИСПРАВЛЕНО (2026-01-03): Динамическая сборка промпта по стратегии
        ИСПРАВЛЕНО (2026-01-05): Добавлен параметр asked_questions для исключения повторов
        ИСПРАВЛЕНО (2026-01-06): Добавлена стратегия NONE для случая без кандидатов

        Стратегии:
        - A (1 кандидат, >90%): Подтверждение
        - B (2-10 кандидатов): Уточнение по списку
        - C (>10 кандидатов): Фильтрация С анализом кандидатов (ИСПРАВЛЕНО 2026-01-06)
        - NONE (0 кандидатов): Уточнение без анализа услуг

        Args:
            strategy: Тип стратегии (A, B, C, NONE)
            context: Контекст ситуации
            absolute_facts: Абсолютные факты (из SemanticPreCheck)
            candidates: Список кандидатов (для стратегий B и C)
            missing_filter: Недостающий фильтр (для стратегии C)
            txtPrb: Описание проблемы
            asked_questions: Список уже заданных вопросов (ИСПРАВЛЕНО 2026-01-05)

        Returns:
            str: Промпт для YandexGPT Pro
        """
        # Базовый блок системы
        system_block = """Ты - AI-диспетчер управляющей компании. Твоя цель - выбрать услугу из каталога.
Стиль: Краткий, деловой, без приветствий. Максимум 15 слов.
"""

        # Блок абсолютных фактов
        facts_block = ""
        if absolute_facts:
            facts_list = "\n".join([f"- {fact}" for fact in absolute_facts])
            facts_block = f"""
БЛОК: АБСОЛЮТНЫЕ ФАКТЫ (ЗАПРЕТ НА ВОПРОСЫ)
Ниже перечислены факты, которые УЖЕ установлены. ТЕБЕ ЗАПРЕЩЕНО ЗАДАВАТЬ ВОПРОСЫ ОБ ЭТОМ.
{facts_list}
"""

        # ИСПРАВЛЕНО (2026-01-05): Блок уже заданных вопросов
        asked_questions_block = ""
        if asked_questions:
            questions_list = "\n".join([f"{i+1}. {q}" for i, q in enumerate(asked_questions)])
            asked_questions_block = f"""
================================================================================
⛔ КРИТИЧЕСКОЕ ПРЕДОСТЕРЕЖЕНИЕ: УЖЕ ЗАДАННЫЕ ВОПРОСЫ ⛔
================================================================================

НИЖЕ ПЕРЕЧИСЛЕНЫ ВОПРОСЫ КОТОРЫЕ БОТ УЖЕ ЗАДАВАЛ В ЭТОМ ДИАЛОГЕ:

{questions_list}

🚨 КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО:
1. ЗАДАВАТЬ ТОЧНО ТАКИЕ ЖЕ ВОПРОСЫ
2. ЗАДАВАТЬ ПОХОЖИЕ ВОПРОСЫ (перефразирования)
3. СПРАШИВАТЬ ТО ЧТО УЖЕ СПРАШИВАЛИ

ПРИМЕРЫ НАРУШЕНИЙ (ЗАПРЕЩЕНО!):
- Уже спросили "Где именно?" → НЕЛЬЗЯ спросить "В каком месте?"
- Уже спросили "Что именно?" → НЕЛЬЗЯ спросить "Что сломалось?"
- Уже спросили "Правильно ли я понял, что прорыв труб?" → НЕЛЬЗЯ спросить "Это прорыв труб?"

ВАЖНО: Если пользователь НЕ ОТВЕТИЛ на вопрос, задай ДРУГОЙ вопрос по другой теме!
================================================================================

"""

        # Блок контекста
        context_block = f"""
БЛОК: КОНТЕКСТ
Текущее описание проблемы: {context}
"""
        if txtPrb:
            context_block += f"\nНакопленное описание: {txtPrb}"

        # Блок ограничений
        constraints_block = """
БЛОК: ОГРАНИЧЕНИЯ (КРИТИЧЕСКИ ВАЖНО - НАРУШЕНИЕ ЗАПРЕЩЕНО!)
0. 🚨 САМОЕ ВАЖНОЕ: НЕ ПОВТОРЯЙ УЖЕ ЗАДАННЫЕ ВОПРОСЫ!
   Если выше в блоке "УЖЕ ЗАДАННЫЕ ВОПРОСЫ" есть вопрос "Где именно?",
   ТЫ КАТЕГОРИЧЕСКИ НЕ МОЖЕШЬ спросить "В каком месте?" или "Где это?"
   ЗАДАЙ ДРУГОЙ ВОПРОС ПО ДРУГОЙ ТЕМЕ!

1. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО двойные вопросы через "или", "или", "и":
   ПЛОХО: "Что именно или где именно?", "Это труба или батарея?"
   ХОРОШО: "Опишите что именно сломалось", "Где именно это произошло?"

2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО перечислять варианты в скобках или запятыми:
   ПЛОХО: "Какой характер? (капает, струей, trickle)", "Что: труба, кран, батарея?"
   ХОРОШО: "Опишите характер проблемы подробнее"

3. ЗАПРЕЩЕНО спрашивать о том, что УЖЕ есть в "Абсолютных фактах":
   Если факт: "location=ванная", вопрос "Где именно?" → ИЗБЫТОЧЕН!

4. Максимум ОДИН вопрос, не более 10 слов, без вводных фраз

5. Используй только открытые вопросы (Что? Как? Где? Когда? Почему?)
   ЗАПРЕЩЕНО закрытые вопросы типа "Это X или Y?"
"""

        # Блок задачи в зависимости от стратегии
        if strategy == 'A':
            # 1 кандидат, уверенность >90%
            candidate_name = candidates[0]['service_name'] if candidates else 'Неизвестно'

            # ИСПРАВЛЕНО (2026-01-05): Проверяем есть ли уже похожий подтверждающий вопрос
            has_confirm_question = False
            logger.info(f"[DEBUG] Стратегия A: asked_questions={len(asked_questions) if asked_questions else 0}")
            if asked_questions:
                for i, q in enumerate(asked_questions):
                    logger.info(f"[DEBUG] Проверка вопроса #{i+1}: '{q[:60]}...'")
                    if 'правильно ли я понял' in q.lower() or 'подтверд' in q.lower():
                        has_confirm_question = True
                        logger.info(f"[DEBUG] НАЙДЕН подтверждающий вопрос!")
                        break

            if has_confirm_question:
                logger.info(f"[DEBUG] Используем альтернативный вопрос (уже спрашивали подтверждение)")
                # Уже спрашивали подтверждение - задаем короткий вопрос
                task_block = f"""
БЛОК: ЗАДАЧА
Услуга определена с вероятностью >90%: {candidate_name}.
Вы УЖЕ задавали подтверждающий вопрос выше.
НЕ ПОВТОРЯЙ "Правильно ли я понял?"!
Задай вопрос для подтверждения: "Подтверждаете?" или "Верно?"
"""
            else:
                # Первый раз - задаем полный подтверждающий вопрос
                logger.info(f"[DEBUG] Первый подтверждающий вопрос")
                task_block = f"""
БЛОК: ЗАДАЧА
Услуга определена с вероятностью >90%. Задай подтверждающий вопрос.
Формула: "Правильно ли я понял, что [описание проблемы]?"

Кандидат: {candidate_name}
"""
        elif strategy == 'B':
            import json
            candidates_json = json.dumps([{
                'id': c.get('service_id'),
                'name': c.get('service_name', c.get('scenario_name', 'Unknown')),
                'category': c.get('category', '-'),
                'location': c.get('location_type', '-')
            } for c in (candidates or [])], ensure_ascii=False)

            task_block = f"""
БЛОК: ЗАДАЧА
Список кандидатов (мало вариантов):
{candidates_json}

Найди критическое отличие между ними (объект или место) и задай вопрос.
Не спрашивай о фактах из блока "Абсолютные факты".
"""
        elif strategy == 'C':
            # ИСПРАВЛЕНО (2026-01-06): Стратегия C ВСЕГДА получает candidates
            # Добавляем анализ различий между кандидатами БЕЗ хардкода
            import json

            # Собираем уникальные значения параметров из кандидатов
            locations = set()
            categories = set()
            incidents = set()

            for c in (candidates or []):
                if c.get('location_type'):
                    locations.add(c['location_type'])
                if c.get('category'):
                    categories.add(c['category'])
                if c.get('incident_type'):
                    incidents.add(c['incident_type'])

            # Формируем блок анализа различий
            analysis_block = """
БЛОК: АНАЛИЗ РАЗЛИЧИЙ МЕЖДУ КАНДИДАТАМИ

Проанализируй кандидатов и определи какие параметры РАЗНЫЕ:
"""
            if locations:
                analysis_block += f"- Разные локации: {', '.join(locations)}\n"
            if categories:
                analysis_block += f"- Разные категории: {', '.join(categories)}\n"
            if incidents:
                analysis_block += f"- Разные типы: {', '.join(incidents)}\n"

            if not (locations or categories or incidents):
                analysis_block += "- Кандидаты не имеют различий в параметрах\n"

            # Сжимаем список кандидатов для промпта (только id, name, key параметры)
            candidates_summary = []
            for c in (candidates or [])[:20]:  # Максимум 20 для экономии токенов
                candidates_summary.append({
                    'id': c.get('service_id'),
                    'name': c.get('service_name', c.get('scenario_name', 'Unknown'))[:50],  # Обрезаем длинные названия
                    'loc': c.get('location_type', '?'),
                    'cat': c.get('category', '?'),
                    'inc': c.get('incident_type', '?')
                })

            candidates_json = json.dumps(candidates_summary, ensure_ascii=False)

            task_block = f"""
{analysis_block}
СПИСОК КАНДИДАТОВ (первые 20 из {len(candidates or [])}):
{candidates_json}

БЛОК: ЗАДАЧА
Кандидатов слишком много ({len(candidates or [])} штук).

АЛГОРИТМ ГЕНЕРАЦИИ ВОПРОСА:
1. Проанализируй блок "РАЗЛИЧИЯ МЕЖДУ КАНДИДАТАМИ"
2. Найди параметр с МАКСИМАЛЬНЫМ разнообразием
3. Сформулируй вопрос который УТОЧНИТ этот параметр
4. НЕ перечисляй варианты из списка
5. НЕ упоминай конкретные услуги

ЦЕЛЬ: Вопрос должен помочь ОТФИЛЬТРОВАТЬ кандидатов, оставив 2-5 самых подходящих.
"""
        else:  # strategy == 'NONE' - нет кандидатов совсем
            task_block = f"""
БЛОК: ЗАДАЧА
Ни одна услуга не подходит под описание проблемы.

Задай вопрос который поможет лучше понять:
- Что именно произошло?
- Где именно это произошло?
- Какой объект поврежден?

Выбери ОДИН самый важный аспект для уточнения.
"""

        # ИСПРАВЛЕНО (2026-01-05): Собираем промпт с блоком уже заданных вопросов
        prompt = f"{system_block}{facts_block}{asked_questions_block}{context_block}{task_block}{constraints_block}"

        # Добавляем инструкцию по формату ответа
        prompt += "\nВерни только вопрос, без объяснений.\n\nВопрос:"

        return prompt

    async def _generate_ai_question(
        self,
        context: str,
        dialog_history: List[Dict] = None,
        candidates: List[Dict] = None,
        established_filters: Dict = None,
        txtPrb: str = None,
        question_type: str = "clarification",
        session_id: str = None
    ) -> Dict[str, str]:
        """
        Универсальный метод для генерации вопросов через AI

        ИСПРАВЛЕНО (2025-12-28): Все вопросы генерируются через YandexGPT
        ИСПРАВЛЕНО (2025-12-29): Возвращает Dict с вопросом И метаданными для трассировки
        ИСПРАВЛЕНО (2026-01-06): Добавлен параметр session_id для связи с llm_request_log
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
            session_id: ID сессии для сохранения в llm_request_log

        Returns:
            Dict: {
                'question': str,  # Сгенерированный вопрос
                'prompt': str,    # Промт отправленный в LLM
                'response': str,  # Ответ от LLM
                'model': str,     # Модель использованная
                'usage': Dict     # Информация об использовании токенов
            }
        """
        # ИСПРАВЛЕНО (2025-12-28): Мощные отладочные логи ВХОДЯЩИХ параметров
        logger.info("[SEARCH] _generate_ai_question ВХОДЯЩИЕ ПАРАМЕТРЫ:")
        logger.info(f"  [NOTE] context: '{context[:100]}'")
        logger.info(f"  [TOOL] question_type: {question_type}")
        logger.info(f"  [LIST] dialog_history: {len(dialog_history) if dialog_history else 0} сообщений")
        logger.info(f"  [NOTE] txtPrb: '{txtPrb[:100] if txtPrb else '(не передан)'}'")
        logger.info(f"  [TOOL] established_filters: {established_filters if established_filters else '(не переданы)'}")
        logger.info(f"  👥 candidates: {len(candidates) if candidates else 0} кандидатов")

        try:
            # ИСПРАВЛЕНО (2026-01-03): Используем _build_dynamic_prompt вместо _build_question_prompt
            # Определяем стратегию на основе количества кандидатов
            strategy = self._determine_strategy(candidates, established_filters)

            # Определяем недостающий фильтр для стратегии C
            missing_filter = None
            if strategy == 'C':
                missing_filter = self._determine_missing_filter(candidates or [], established_filters or {})

            # Формируем абсолютные факты из semantic_check если есть
            absolute_facts = []
            if established_filters:
                semantic_check = established_filters.get('semantic_check', {})
                if semantic_check.get('absolute_facts'):
                    absolute_facts = semantic_check['absolute_facts']

            # ИСПРАВЛЕНО (2026-01-05): Извлекаем уже заданные вопросы из истории
            asked_questions = []
            if dialog_history:
                asked_questions = self._extract_asked_questions(dialog_history)
                logger.info(f"[!] Уже задано вопросов: {len(asked_questions)}")

            # ИСПРАВЛЕНО (2026-01-03): Для типа clarification используем _build_dynamic_prompt
            if question_type == 'clarification' and candidates is not None:
                # Используем новый метод с динамическими промптами по стратегиям
                prompt = self._build_dynamic_prompt(
                    strategy=strategy,
                    context=context,
                    absolute_facts=absolute_facts if absolute_facts else None,
                    candidates=candidates,
                    missing_filter=missing_filter,
                    txtPrb=txtPrb,
                    asked_questions=asked_questions if asked_questions else None  # ИСПРАВЛЕНО 2026-01-05
                )
                logger.info(f"Используется стратегия {strategy} (кандидатов: {len(candidates) if candidates else 0})")
            else:
                # Для остальных типов используем старый метод
                prompt = self._build_question_prompt(
                    context=context,
                    dialog_history=dialog_history,
                    candidates=candidates,
                    established_filters=established_filters,
                    txtPrb=txtPrb,
                    question_type=question_type
                )

            # ИСПРАВЛЕНО (2025-12-28): Логируем промт (первые 500 символов)
            logger.info(f"[BOT] PROMPT ДЛЯ LLM ({question_type}):")
            logger.info(f"{'=' * 80}")
            logger.info(f"{prompt[:500]}...")
            logger.info(f"{'=' * 80} (полная длина: {len(prompt)} символов)")

            # Вызываем AI через AIAgentService
            if self.ai_agent:
                # ИСПРАВЛЕНО (2025-12-28): ГИБРИДНАЯ МОДЕЛЬ
                # - Для вопросов к пользователю: Pro (качество критично!)
                # - Для остальных задач: используется default (обычно Lite)
                question_types_requiring_pro = ['clarification', 'what_happened', 'location', 'details']
                model = 'pro' if question_type in question_types_requiring_pro else 'lite'

                # ИСПРАВЛЕНО (2025-12-28): Используем универсальный метод call_llm
                # ИСПРАВЛЕНО (2026-01-06): Передаем session_id для логирования
                response, usage = await self.ai_agent.call_llm(
                    prompt=prompt,
                    provider='yandexgpt',  # Можно менять на 'gigachat'
                    model=model,
                    session_id=session_id  # ИСПРАВЛЕНО (2026-01-06)
                )
                question = response.strip()

                # ИСПРАВЛЕНО (2025-12-28): Логируем ответ LLM
                logger.info(f"[BOT] ОТВЕТ LLM ({question_type}, model={usage.get('model', 'unknown')}):")
                logger.info(f"  [NOTE] Текст: '{question}'")
                logger.info(f"  [$] Usage: {usage}")

                # Удаляем лишние кавычки если есть
                if question.startswith('"') and question.endswith('"'):
                    question = question[1:-1]
                if question.startswith("'") and question.endswith("'"):
                    question = question[1:-1]

                # ИСПРАВЛЕНО (2026-01-03): Regex-валидаторы удалены, используем LLM-валидацию
                question = await self._llm_validate_question(
                    question=question,
                    txtPrb=txtPrb,
                    established_filters=established_filters
                )

                # ИСПРАВЛЕНО (2025-12-29): Отладочный режим - добавляем объяснение к вопросу
                if self.tst_prompt:
                    question = self._add_debug_explanation(question, question_type, candidates)

                logger.info(f"[OK] AI сгенерировал вопрос ({question_type}): {question}")

                # ИСПРАВЛЕНО (2025-12-29): Возвращаем Dict с вопросом И метаданными для трассировки
                return {
                    'question': question,
                    'prompt': prompt,
                    'response': response,
                    'model': usage.get('model', 'unknown'),
                    'usage': usage
                }
            else:
                logger.warning("AIAgentService недоступен, используем fallback")
                question = self._fallback_question(question_type, context)
                return {
                    'question': question,
                    'prompt': '(fallback - нет LLM вызова)',
                    'response': '(fallback - нет LLM ответа)',
                    'model': 'fallback',
                    'usage': {}
                }

        except Exception as e:
            logger.error(f"Ошибка генерации AI вопроса: {e}")
            question = self._fallback_question(question_type, context)
            return {
                'question': question,
                'prompt': f'(error: {str(e)})',
                'response': f'(error: {str(e)})',
                'model': 'error',
                'usage': {}
            }

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

        # Формируем JSON кандидатов для промта
        candidates_json = ""
        import json
        candidates_list = []
        for c in candidates[:15]:  # До 15 кандидатов
            candidate_data = {
                "КодУслуги": c.get('service_id', 'Unknown'),
                "Наименование": c.get('service_name', c.get('scenario_name', 'Unknown')),
                "Фильтры": {
                    "Тип": c.get('incident_type', '-'),
                    "Вид": c.get('location_type', '-'),
                    "Категория": c.get('category', '-'),
                    "Объект": c.get('object_type', '-')
                }
            }
            candidates_list.append(candidate_data)

        candidates_json = f"\nСПИСОК КАНДИДАТОВ (услуги которые подходят под описание):\n"
        candidates_json += "```json\n"
        candidates_json += json.dumps(candidates_list, ensure_ascii=False, indent=2)
        candidates_json += "\n```\n"

        # Формируем промт
        # ПЕРЕРАБОТАНО (2025-12-29): Позитивная инструкция + алгоритм + JSON заявки
        # ИСПРАВЛЕНО (2026-01-03): Убраны все эмодзи из промта
        prompt = f"""Ты - AI-диспетчер УК "Аспект".

══════════════════════════════════════════════════════════════════════════════
ГЛАВНАЯ ЗАДАЧА
══════════════════════════════════════════════════════════════════════════════

Сформировать заявку от абонента в формате JSON:

Этап 1: Определить услугу (поиск в каталоге, получение подтверждения от пользователя)
Этап 2: Определить адрес (через AddressExtractor)
Этап 3: Вернуть JSON заявки с полями:
  - timestamp: время обращения
  - telegram_user: ник пользователя в ТГ или логин в чате
  - dialog_id: ID диалога
  - service_id: ID услуги
  - address_id: ID объекта обслуживания

══════════════════════════════════════════════════════════════════════════════
ИНСТРУКЦИЯ ПО ГЕНЕРАЦИИ ВОПРОСА
══════════════════════════════════════════════════════════════════════════════

Верни уточняющий открытый вопрос, который:

1. СОКРАТИТ список кандидатов до ОДНОЙ услуги
   ИЛИ
2. НАЛОЖИТ один из фильтров (Тип/Вид/Категория/Объект) на множество кандидатов

Ограничения:
- Максимальная длина: 10 слов
- Только ОДИН вопрос
- Открытый вопрос (без вариантов ответа)
- Ответ должен приблизить к однозначному определению услуги

НЕ ПРИМЕНЯЙ:
- Двойные вопросы ("что и где?")
- Перечисления вариантов ("например, труба или батарея?")
- Закрытые вопросы (да/нет) - КРОМЕ исключения ниже
- Слово "например" и любые перечисления через него
- Внутренние термины "Инцидент/Запрос" - говори по-человечески
- Вопросы которые НЕ приближают к решению (не позволяют установить фильтр)

ИСКЛЮЧЕНИЕ (закрытый вопрос РАЗРЕШЕН):
Если один кандидат имеет вероятность 90%+ → спроси: "Правильно ли я понял, что у вас [описание проблемы]?"

ПРИМЕНЯЙ:
- Открытый вопрос, уточнение одного параметра
- Учет уже известной информации
- Анализ истории диалога ниже

══════════════════════════════════════════════════════════════════════════════
АЛГОРИТМ ПОИСКА УСЛУГИ
══════════════════════════════════════════════════════════════════════════════

1. Анализируй историю диалога в блоке [ИСТОРИЯ ДИАЛОГА]
2. Если можешь однозначно определить услугу (вероятность 90%+):
   → Задай вопрос: "Правильно ли я понял, что у вас [описание]?"
3. Если невозможно однозначно определить:
   → Задай уточняющий вопрос который отфильтрует большинство кандидатов
   → Ответ пользователя позволит установить фильтр для следующего этапа
4. Повторяй пока не будет подтверждение услуги (90%+)

══════════════════════════════════════════════════════════════════════════════
КАК РАБОТАЮТ ФИЛЬТРЫ
══════════════════════════════════════════════════════════════════════════════

Фильтры сокращают список кандидатов:

- Тип (Инцидент/Запрос):
  * Инцидент = сломалось, не работает, угроза жизни/здоровью/имуществу
  * Запрос = нужно выполнить работу, НЕТ угрозы жизни/здоровью/имуществу
    (улучшение: установка нового унитаза, консультация, замена счетчика и т.д.)

- Вид (Индивидуальное/Общедомовое):
  * Индивидуальное = проблема в квартире пользователя
    (квартира состоит из комнат: ванная, зал, кухня, спальня и т.д.)
    (если пользователь назвал локацию "ванная"/"зал" → проверь может ли она быть в квартире)
  * Общедомовое = проблема в подъезде, на улице, местах общего пользования
  Варианты: {', '.join(self._location_types_cache)}

- Категория: {', '.join(self._categories_cache)}

- Объект: {', '.join(self._objects_cache)}

Стратегия: задавай вопросы чтобы установить фильтры и сократить список кандидатов.

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
ИСТОРИЯ ДИАЛОГА:
{recent_dialog}
"""

        if established_filters:
            prompt += f"""
УСТАНОВЛЕННЫЕ ФИЛЬТРЫ (с вероятностью):
{self._format_filters_for_prompt(established_filters)}

ВАЖНО: Учитывай эти фильтры при генерации вопроса!
"""

        if candidates_json:
            prompt += f"{candidates_json}\n"

        # Инструкция по типу вопроса
        if question_type == 'clarification':
            prompt += """
══════════════════════════════════════════════════════════════════════════════
КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА
══════════════════════════════════════════════════════════════════════════════

1. ОБЯЗАТЕЛЬНО: Верни ВОПРОС (заканчивается на "?")
   - НЕЛЬЗЯ возвращать утверждения
   - НЕЛЬЗЯ возвращать "Нет необходимости уточнять"
   - НЕЛЬЗЯ возвращать "Все понятно"

2. ИСПРАВЛЕНИЕ (2026-01-05): КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНЫ ДВОЙНЫЕ ВОПРОСЫ:
   - ЗАПРЕЩЕНО вопросы через "или", "или", "и"
   - ЗАПРЕЩЕНО перечислять варианты в скобках или запятыми
   - Максимум ОДИН вопрос, не более 10 слов

   ПРИМЕРЫ ДВОЙНЫХ ВОПРОСОВ (НЕ ДЕЛАЙ ТАК):
   - "Что именно или где именно?" → ДВОЙНОЙ (Что? + Где?)
   - "Это труба или батарея?" → ДВОЙНОЙ + закрытый
   - "Какой объект и в каком месте?" → ДВОЙНОЙ
   - "Опишите что и где это произошло" → ДВОЙНОЙ

   ПРАВИЛЬНЫЕ ВОПРОСЫ:
   - "Опишите что именно сломалось" → ОДИН вопрос
   - "Где именно это произошло?" → ОДИН вопрос

3. Проверка что текст является вопросом:
   ПРИМЕРЫ НЕВОПРОСОВ (ОТКЛОНИТЬ):
   - "Нет необходимости уточнять локацию." → НЕ ВОПРОС (утверждение)
   - "Я понял проблему." → НЕ ВОПРОС
   - "Все понятно." → НЕ ВОПРОС

   ПРИМЕРЫ ВОПРОСОВ (ПРИНЯТЬ):
   - "Где именно это произошло?" → ВОПРОС
   - "Опишите что именно сломалось?" → ВОПРОС

4. ИСПРАВЛЕНИЕ (2026-01-05): КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО спрашивать то, что УЖЕ ИЗВЕСТНО:
   - Проверь блок "УСТАНОВЛЕННЫЕ ФИЛЬТРЫ" выше
   - Если фильтр установлен с уверенностью 80%+ → НЕ спрашивай про него!
   - Если location=Индивидуальное (90%) → НЕ спрашивай "Где?"
   - Если category=Водоснабжение (95%) → НЕ спрашивай "Это водоснабжение?"
   - Если object=труба (90%) → НЕ спрашивай "Что именно?"

   ПРИМЕРЫ НАРУШЕНИЙ (НЕ ДЕЛАЙ ТАК):
   - Фильтр: location=Индивидуальное (90%), вопрос: "Где это произошло?" → ЗАПРЕЩЕНО!
   - Фильтр: category=Водоснабжение (95%), вопрос: "Это водоснабжение?" → ЗАПРЕЩЕНО!
   - Фильтр: object=труба (90%), вопрос: "Из чего течет?" → ЗАПРЕЩЕНО!

5. ИСПРАВЛЕНО (2026-01-10): Если source/object_description НЕ установлен или null:
   - Проверь блок "ОПИСАНИЕ ПРОБЛЕМЫ" выше - если там нет источника проблемы
   - ОБЯЗАТЕЛЬНО спроси: "Что именно течет/сломалось?" или "Откуда именно?"
   - НЕ спрашивай про конкретную категорию (водоснабжение/отопление) если она НЕ установлена!
   - Пользователь НЕ ЗНАЕТ категорию - он знает только симптомы!

   ПРИМЕРЫ ПРАВИЛЬНЫХ ВОПРОСОВ (source=null):
   - "Что именно течет?" (пользователь сказал "течет" но не указал источник)
   - "Откуда именно течет?" (пользователь сказал "течет в зале" но не сказал источник)
   - "Какой объект неисправен?" (общий вопрос про объект)

   ПРИМЕРЫ НЕПРАВИЛЬНЫХ ВОПРОСОВ (category=null, source=null):
   - "Что происходит с водоснабжением?" → ЗАПРЕЩЕНО! (категория не установлена)
   - "Это проблема с отоплением?" → ЗАПРЕЩЕНО! (категория не установлена)
   - "Какой характер протечки?" → ЗАПРЕЩЕНО! (не помогает определить источник)

   ПРАВИЛО: СНАЧАЛА выясни источник (что именно), ПОТОМ категорию определишь!

══════════════════════════════════════════════════════════════════════════════
ЗАДАЧА
══════════════════════════════════════════════════════════════════════════════

Проанализируй список кандидатов, установленные фильтры и историю диалога.

Верни ОДИН вопрос который:
- Позволит однозначно определить кандидата ИЛИ наложить фильтр
- Максимально короткий (до 10 слов)
- Открытый вопрос (без перечислений вариантов)
- Учитывает уже известную информацию (НЕ спрашивай то, что УЖЕ есть в фильтрах!)
- ПРИБЛИЖАЕТ К РЕШЕНИЮ (позволяет установить фильтр или определить услугу)

ПРИМЕРЫ:

ХОРОШО: "Где именно это произошло?"
   Цель: Установить фильтр Вид (Индивидуальное/Общедомовое)

ХОРОШО: "Опишите что именно сломалось"
   Цель: Установить фильтр Объект (Труба/Кран/Батарея)

ХОРОШО (90%+ кандидат): "Правильно ли я понял, что у вас течет из трубы в ванной?"
   Цель: Подтвердить кандидата с высокой вероятностью (ИСКЛЮЧЕНИЕ: закрытый вопрос разрешен)

ПЛОХО: "Что и где?" (двойной вопрос)
ПЛОХО: "Это труба или батарея?" (закрытый вопрос без 90%+ кандидата)
ПЛОХО: "Это труба отопления или водоснабжения?" (закрытый вопрос с "или")
ПЛОХО: "Какой характер? Например, капает или струей?" (НЕ приближает к решению + перечисление)
ПЛОХО: "Это инцидент или запрос?" (внутренние термины, не для пользователя)

Вопрос:"""

        elif question_type == 'what_happened':
            prompt += """

══════════════════════════════════════════════════════════════════════════════
КРИТИЧЕСКИ ВАЖНОЕ ПРАВИЛО (2026-01-05):
══════════════════════════════════════════════════════════════════════════════

КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО спрашивать то, что УЖЕ ИЗВЕСТНО из установленных фильтров!
- Проверь блок "УСТАНОВЛЕННЫЕ ФИЛЬТРЫ" выше
- Если фильтр установлен с уверенностью 80%+ → НЕ спрашивай про него!

══════════════════════════════════════════════════════════════════════════════
ЗАДАЧА
══════════════════════════════════════════════════════════════════════════════

Задай ОДИН вопрос чтобы понять что именно случилось.

Ограничения:
- Один вопрос
- Открытый вопрос
- Без перечислений
- Коротко
- НЕ спрашивай то, что УЖЕ известно из фильтров

Вопрос:"""

        elif question_type == 'location':
            prompt += """

══════════════════════════════════════════════════════════════════════════════
КРИТИЧЕСКИ ВАЖНОЕ ПРАВИЛО (2026-01-05):
══════════════════════════════════════════════════════════════════════════════

КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО спрашивать про локацию если она УЖЕ ИЗВЕСТНА!
- Проверь блок "УСТАНОВЛЕННЫЕ ФИЛЬТРЫ" выше
- Если location_type установлен с уверенностью 80%+ → НЕ спрашивай "Где?"
- Вместо этого спроси про другой параметр (объект, деталь проблемы)

══════════════════════════════════════════════════════════════════════════════
ЗАДАЧА
══════════════════════════════════════════════════════════════════════════════

Задай ОДИН вопрос о месте проблемы (ТОЛЬКО если локация НЕ известна).

Ограничения:
- Один вопрос
- Открытый вопрос
- НЕ спрашивай если локация уже известна (см. правило выше)
- Коротко

Вопрос:"""

        else:  # details
            prompt += """

══════════════════════════════════════════════════════════════════════════════
КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА (2026-01-05):
══════════════════════════════════════════════════════════════════════════════

1. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО: Двойные вопросы
2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО: Спрашивать то, что УЖЕ ИЗВЕСТНО из фильтров!
3. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО: Использовать союз "и"

Проверь блок "УСТАНОВЛЕННЫЕ ФИЛЬТРЫ" выше:
- Если location известен (80%+) → НЕ спрашивай "Где?"
- Если object известен (80%+) → НЕ спрашивай "Что именно?"
- Если category известен (80%+) → НЕ спрашивай "Это [категория]?"

══════════════════════════════════════════════════════════════════════════════
ЗАДАЧА
══════════════════════════════════════════════════════════════════════════════

Задай ОДИН уточняющий вопрос для детализации проблемы (ТОЛЬКО того, что НЕ известно).

Ограничения:
- Только ОДИН вопрос
- Открытый вопрос
- Вежливый тон
- Учитывай что уже известно из фильтров (НЕ спрашивай повторно!)
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

    def _add_debug_explanation(self, question: str, question_type: str, candidates: List[Dict] = None) -> str:
        """
        ИСПРАВЛЕНО (2025-12-29): Добавляет отладочное объяснение к вопросу

        Если TST_PROMPT=1, добавляет в скобках пояснение зачем задается вопрос.
        Формат: "(определяю локацию): Где произошла протечка?"

        Args:
            question: Сгенерированный вопрос
            question_type: Тип вопроса
            candidates: Кандидаты услуг

        Returns:
            str: Вопрос с объяснением в скобках
        """
        if not self.tst_prompt:
            return question

        # Определяем цель вопроса по ключевым словам
        explanation = ""
        question_lower = question.lower()

        # Анализируем цель вопроса
        if any(word in question_lower for word in ['где', 'место', 'локаци', 'в какой комнат']):
            explanation = "определяю локацию"
        elif any(word in question_lower for word in ['что', 'чем', 'предмет', 'объект', 'какой']):
            if any(word in question_lower for word in ['сломал', 'не работ', 'произошло']):
                explanation = "определяю проблему"
            else:
                explanation = "определяю объект"
        elif any(word in question_lower for word in ['как', 'опиш', 'расскаж', 'подробн']):
            explanation = "уточняю детали"
        elif any(word in question_lower for word in ['категория', 'вид', 'тип']):
            explanation = "классифицирую услугу"
        elif candidates and len(candidates) > 5:
            explanation = f"фильтрую {len(candidates)} кандидатов"
        elif candidates and len(candidates) <= 3:
            explanation = f"уточняю из {len(candidates)} вариантов"
        else:
            explanation = "уточняю ситуацию"

        # Формируем итоговый вопрос с объяснением
        return f"({explanation}): {question}"

    async def _ask_ai_clarification_with_candidates(
        self,
        message_text: str,
        candidates: List[Dict],
        dialog_history: List[Dict],
        established_filters: Dict = None,
        session_id: str = None
    ) -> Dict:
        """Спрашивает у AI как уточнить - использует AI для анализа кандидатов

        ИСПРАВЛЕНО (2025-12-27): Использует AI для генерации вопроса на основе кандидатов
        ИСПРАВЛЕНО (2025-12-27): Закомментированы кэшированные запросы
        ИСПРАВЛЕНО (2025-12-27): Применяет established_filters для сужения кандидатов
        """
        # ИСПРАВЛЕНО (2025-12-27): Применяем фильтры к кандидатам
        if established_filters:
            before_count = len(candidates)
            logger.info(f"[GEAR] _ask_ai_clarification: candidates до фильтров: {before_count}")
            logger.info(f"[GEAR] _ask_ai_clarification: established_filters={established_filters}")

            candidates = self._apply_filters_to_candidates(candidates, established_filters)
            after_count = len(candidates)
            logger.info(f"[OK] _ask_ai_clarification: после фильтров: {after_count} кандидатов")

            # Показываем оставшихся кандидатов
            for i, c in enumerate(candidates[:5], 1):
                logger.info(f"  {i}. {c.get('service_name', 'Unknown')} (loc={c.get('location_type', '?')[:10]} conf={c.get('confidence', 0):.2f})")
        else:
            logger.info(f"[GEAR] _ask_ai_clarification: established_filters=None, пропускаем фильтрацию")

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

        # ИСПРАВЛЕНО (2025-12-28): Используем универсальный метод _generate_ai_question
        # вместо старого хардкод промпта
        context = f"Пользователь написал: {message_text}"

        # Добавляем информацию об уже заданных вопросах в context
        if recent_bot_questions:
            context += f"\n\nУЖЕ ЗАДАННЫЕ ВОПРОСЫ (НЕ ПОВТОРЯТЬ!):\n"
            for q in recent_bot_questions[-3:]:
                context += f"  - {q}\n"

        # ИСПРАВЛЕНО (2025-12-28): Извлекаем txtPrb из dialog_history
        extracted_txtPrb = ""
        if self.problem_accumulator and dialog_history:
            extracted_txtPrb = self.problem_accumulator.get_txtPrb_from_metadata(dialog_history)

        # Генерируем вопрос через универсальный метод
        # ИСПРАВЛЕНО (2025-12-29): Получаем Dict с вопросом И метаданными
        # ИСПРАВЛЕНО (2026-01-06): Передаем session_id для логирования
        ai_result = await self._generate_ai_question(
            context=context,
            dialog_history=dialog_history,
            candidates=candidates,
            established_filters=established_filters,
            txtPrb=extracted_txtPrb,  # ИСПРАВЛЕНО: передаем txtPrb
            question_type='clarification',
            session_id=session_id  # ИСПРАВЛЕНО (2026-01-06)
        )

        ai_question = ai_result['question']
        logger.info(f"AI сгенерировал вопрос для {len(candidates)} кандидатов: {ai_question}")

        # ИСПРАВЛЕНО (2025-12-29): Сохраняем метаданные AI в результат
        # Это будет добавлено в _metadata вызываемого метода

        return {
            'status': 'AMBIGUOUS',
            'message': ai_question,
            'candidates': candidates,
            'needs_clarification': True,
            '_ai_metadata': {  # ИСПРАВЛЕНО (2025-12-29): Сохраняем метаданные для трассировки
                'prompt': ai_result['prompt'],
                'response': ai_result['response'],
                'model': ai_result['model'],
                'usage': ai_result['usage']
            }
        }

    async def _ask_ai_clarification(
        self,
        message_text: str,
        candidates: List[Dict],
        dialog_history: List[Dict],
        established_filters: Dict = None,
        session_id: str = None
    ) -> Dict:
        """Спрашивает как уточнить - использует CommunicativeScriptsService

        ИСПРАВЛЕНО (2025-12-26): Вместо AI использует CommunicativeScriptsService
        ИСПРАВЛЕНО (2026-01-05): Добавлен параметр established_filters
        """
        # Вычисляем dialog_turn и is_followup
        dialog_turn = len(dialog_history) if dialog_history else 1
        is_followup = dialog_turn > 1

        # ИСПРАВЛЕНО (2025-12-28): Используем AI для генерации вопроса
        # ЗАМЕНА: CommunicativeScriptsService → _generate_ai_question
        context = f"Пользователь написал: {message_text}"

        # ИСПРАВЛЕНО (2025-12-28): Извлекаем txtPrb из dialog_history
        extracted_txtPrb = ""
        if self.problem_accumulator and dialog_history:
            extracted_txtPrb = self.problem_accumulator.get_txtPrb_from_metadata(dialog_history)

        # ИСПРАВЛЕНО (2026-01-05): Получаем Dict с вопросом И метаданными, ПЕРЕДАЕМ established_filters
        # ИСПРАВЛЕНО (2026-01-06): Передаем session_id для логирования
        ai_result = await self._generate_ai_question(
            context=context,
            dialog_history=dialog_history,
            candidates=candidates,
            established_filters=established_filters,  # ИСПРАВЛЕНО (2026-01-05): передаем фильтры
            txtPrb=extracted_txtPrb,
            question_type='clarification',
            session_id=session_id  # ИСПРАВЛЕНО (2026-01-06)
        )

        ai_question = ai_result['question']

        return {
            'status': 'AMBIGUOUS',
            'message': ai_question,
            'candidates': candidates,
            'needs_clarification': True,
            '_ai_metadata': {  # ИСПРАВЛЕНО (2025-12-29): Сохраняем метаданные для трассировки
                'prompt': ai_result['prompt'],
                'response': ai_result['response'],
                'model': ai_result['model'],
                'usage': ai_result['usage']
            }
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
            # ИСПРАВЛЕНО (2025-12-28): Копируем location_type, incident_type, category из all_data[0]
            final_candidate = {
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
            }

            # Копируем атрибуты из all_data[0] если они есть
            if c['all_data'] and len(c['all_data']) > 0:
                first_data = c['all_data'][0]
                if 'location_type' in first_data:
                    final_candidate['location_type'] = first_data['location_type']
                if 'incident_type' in first_data:
                    final_candidate['incident_type'] = first_data['incident_type']
                if 'category' in first_data:
                    final_candidate['category'] = first_data['category']

            unique_candidates.append(final_candidate)

        # ИСПРАВЛЕНО (2026-01-06): Сортируем по комбинированному показателю (priority + confidence)
        # Проблема: сортировка только по priority выбирала не лучшего кандидата
        # Решение: учитываем и priority (60%) и confidence (40%)
        unique_candidates.sort(
            key=lambda x: (
                x.get('priority', 0.0) * 0.6 + x.get('confidence', 0.0) * 0.4,
                len(x.get('sources', []))
            ),
            reverse=True
        )

        logger.info(f"Дедупликация: {len(all_candidates)} -> {len(unique_candidates)} кандидатов")

        # Логируем топ-3 кандидатов с отладочной информацией
        for i, c in enumerate(unique_candidates[:3], 1):
            debug = c.get('_debug_info', {})
            score = c.get('priority', 0.0) * 0.6 + c.get('confidence', 0.0) * 0.4
            logger.info(
                f"  #{i} ID:{c['service_id']} | {c.get('service_name', 'Unknown')[:30]} "
                f"| score={score:.3f} (priority={c['priority']:.3f} + conf={c.get('confidence', 0):.2f}) "
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

        logger.info(f"[SEARCH] _apply_filters_to_candidates: начало, кандидатов={len(candidates)}, фильтров={len(established_filters)}")

        # Применяем фильтры по очереди
        filtered_candidates = candidates

        for filter_name, filter_data in established_filters.items():
            confidence = filter_data.get('confidence', 0.0)
            value = filter_data.get('value')

            # Применяем только фильтры с высокой уверенностью
            if confidence < FILTER_CONFIDENCE_THRESHOLD:
                logger.info(f"[!] Фильтр {filter_name}: confidence={confidence:.2f} < {FILTER_CONFIDENCE_THRESHOLD}, ПРОПУСКАЕМ")
                continue

            logger.info(f"[OK] ПРИМЕНЯЕМ ФИЛЬТР: {filter_name}={value} (confidence={confidence:.2f} >= {FILTER_CONFIDENCE_THRESHOLD})")

            # ИСПРАВЛЕНИЕ (2026-01-05): Используем правильные ключи established_filters
            # Фильтрация по location_type (было 'location')
            if filter_name == 'location_type' and value:
                # Маппинг: зал/комната -> Индивидуальное
                if value in ['Индивидуальное', 'Квартира', 'индивидуальное']:
                    # ИСПРАВЛЕНО (2025-12-28): Добавлено детальное логирование
                    before_count = len(filtered_candidates)

                    # Логируем каждого кандидата ДО фильтрации
                    logger.info(f"  [LIST] ДО ФИЛЬТРАЦИИ location_type='{value}':")
                    for i, c in enumerate(filtered_candidates, 1):
                        loc = c.get('location_type', 'NULL')
                        loc_lower = loc.lower() if loc else 'null'
                        match = loc_lower in ['индивидуальное', 'квартира']
                        logger.info(f"    {i}. ID={c.get('service_id')} | '{loc}' -> '{loc_lower}' | match={match}")

                    filtered_candidates = [
                        c for c in filtered_candidates
                        if c.get('location_type', '').lower() in ['индивидуальное', 'квартира']
                    ]
                    after_count = len(filtered_candidates)
                    logger.info(f"  [OK] Фильтр location_type: {before_count} -> {after_count} (оставили Individual)")

            # ИСПРАВЛЕНИЕ (2026-01-05): Используем правильные ключи established_filters
            # Фильтрация по incident_type (было 'incident')
            elif filter_name == 'incident_type' and value:
                if value in ['Инцидент', 'инцидент']:
                    before_count = len(filtered_candidates)
                    filtered_candidates = [
                        c for c in filtered_candidates
                        if c.get('incident_type', '').lower() in ['инцидент']
                    ]
                    after_count = len(filtered_candidates)
                    logger.info(f"  [OK] Фильтр incident_type: {before_count} -> {after_count} (оставили Инцидент)")

            # ИСПРАВЛЕНИЕ (2026-01-05): ОТКЛЮЧАЕМ фильтрацию по category
            # ПРИЧИНА: FilterDetectionService часто ошибается (определил 'Канализация' для 'прорвало трубу')
            # Фильтр убивал всех кандидатов (5 → 0) из-за неправильной категории
            elif filter_name == 'category' and value:
                logger.info(f"[!] Фильтр category={value}: ПРОПУСКАЕМ (FilterDetectionService часто ошибается)")
                continue

            # ИСПРАВЛЕНИЕ (2026-01-05): ОТКЛЮЧАЕМ фильтрацию по object_description
            # ПРИЧИНА: object_description='труба прорвало' - это описание проблемы,
            # а НЕ подстрока для поиска в названии услуги. Неправильная логика убивала всех кандидатов.
            elif filter_name == 'object_description' and value:
                logger.info(f"[!] Фильтр object_description={value}: ПРОПУСКАЕМ (неправильная логика)")
                continue

        return filtered_candidates

