#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Главный Агент системы определения услуг
Координирует работу микросервисов поиска услуг
"""

import logging
import asyncio
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
from django.db import connection

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
    1. TagSearchService - нечеткий поиск по тегам
    2. SemanticSearchService - логико-семантический поиск
    3. VectorSearchService - поиск по векторной базе тегов
    4. AIAgentService - поиск с помощью ИИ (YandexGPT)
    """

    def __init__(self):
        self.tag_search = None
        self.semantic_search = None
        self.vector_search = None
        self.ai_agent = None
        self.confidence_threshold = 0.75  # Порог уверенности

        # Инициализируем микросервисы
        self._init_services()

        logger.info("Главный Агент инициализирован с микросервисной архитектурой")

    def _init_services(self):
        """Инициализация микросервисов"""
        try:
            from tag_search_service_v2 import TagSearchServiceV2
            self.tag_search = TagSearchServiceV2()
            logger.info("TagSearchServiceV2 инициализирован (с поддержкой ref_tags)")
        except ImportError:
            logger.warning("TagSearchServiceV2 не найден, будет пропущен")

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

    async def process_service_detection(self, message_text: str, user_context: Dict = None) -> Dict:
        """
        Основной метод определения услуги через микросервисы

        Args:
            message_text: Текст сообщения пользователя (может включать контекст)
            user_context: Контекст пользователя, включая историю диалога

        Returns:
            Dict: Результат с найденными услугами
        """
        # Извлекаем оригинальное сообщение и контекст
        original_message = message_text
        is_followup = False

        if user_context:
            original_message = user_context.get('original_message', message_text)
            is_followup = user_context.get('is_followup', False)
            dialog_history = user_context.get('dialog_history', [])

            if is_followup and dialog_history:
                logger.info(f"Главный Агент обрабатывает уточняющее сообщение: '{original_message}' (полный контекст: '{message_text[:50]}...')")
            else:
                logger.info(f"Главный Агент начал обработку: '{message_text[:50]}...'")
        else:
            logger.info(f"Главный Агент начал обработку: '{message_text[:50]}...'")

        # Для поиска используем полный контекст, но для генерации ответов - оригинальное сообщение
        search_text = message_text

        try:
            # Запускаем параллельный поиск через все доступные микросервисы
            search_tasks = []

            if self.tag_search:
                search_tasks.append(self._run_tag_search(search_text))

            if self.semantic_search:
                search_tasks.append(self._run_semantic_search(search_text))

            if self.vector_search:
                search_tasks.append(self._run_vector_search(search_text))

            if self.ai_agent:
                search_tasks.append(self._run_ai_search(search_text))

            # Ждем результаты от всех микросервисов
            if search_tasks:
                search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            else:
                return self._create_error_result("Нет доступных микросервисов")

            # Собираем и анализируем результаты
            all_candidates = []
            for result in search_results:
                if isinstance(result, Exception):
                    logger.error(f"Ошибка микросервиса: {result}")
                    continue
                if result and result.get('candidates'):
                    all_candidates.extend(result['candidates'])

            # Анализируем результаты
            if not all_candidates:
                return self._create_ambiguous_result(all_candidates)

            # Дедупликация и объединение результатов
            final_candidates = self._merge_candidates(all_candidates)

            # Анализ пересечений с учетом контекста
            try:
                analysis_result = self._analyze_intersections(final_candidates, original_message, is_followup)
                return analysis_result
        except Exception as e:
                # Детальное логирование ошибки анализа
                import traceback
                logger.error(f"Ошибка в _analyze_intersections: {type(e).__name__}: {e}")
                logger.error(f"Кандидаты: {final_candidates}")
                logger.error(f"Трассировка:\n{traceback.format_exc()}")

                # Возвращаем базовый результат при ошибке анализа
                if final_candidates:
                    return {
                        'status': 'AMBIGUOUS',
                        'candidates': final_candidates[:3],
                        'message': '🤔 Пожалуйста, уточните детали проблемы.',
                        'needs_clarification': True
                    }
                else:
                    return self._create_error_result("Не удалось определить услугу. Пожалуйста, опишите проблему подробнее.")

            except Exception as e:
            # Общая обработка критических ошибок в process_service_detection
            import traceback
            logger.error(f"КРИТИЧЕСКАЯ ОШИБКА в process_service_detection: {type(e).__name__}: {e}")
            logger.error(f"Сообщение: '{message_text}'")
            logger.error(f"Контекст: {user_context}")
            logger.error(f"Трассировка:\n{traceback.format_exc()}")

            # Возвращаем безопасный результат
            return {
                'status': 'ERROR',
                'error': 'Системная ошибка обработки',
                'message': '😔 Произошла техническая ошибка. Пожалуйста, опишите проблему другими словами.\n\n'
                         'Если проблема повторяется, напишите: "связь с диспетчером"',
                'candidates': []
            }

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

    async def _run_ai_search(self, message_text: str) -> Dict:
        """Запуск AIAgentService"""
        try:
            return await self.ai_agent.search(message_text)
        except Exception as e:
            logger.error(f"Ошибка AIAgentService: {e}")
            return {}

    def _filter_by_confidence(self, candidates: List[Dict]) -> List[Dict]:
        """Фильтрация кандидатов по порогу уверенности"""
        filtered = []
        for candidate in candidates:
            confidence = candidate.get('confidence', 0)
            if confidence >= self.confidence_threshold:
                filtered.append(candidate)
            else:
                service_id = candidate.get('service_id', 'unknown')
                logger.debug(f"Кандидат отфильтрован: {service_id} ({confidence:.2f} < {self.confidence_threshold})")

        logger.info(f"Отфильтровано кандидатов: {len(filtered)} из {len(candidates)}")
        return filtered

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

    def _analyze_intersections(self, candidates: List[Dict], original_message: str = "", is_followup: bool = False) -> Dict:
        """Анализ пересечений результатов от разных микросервисов"""
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
            return self._create_ambiguous_result(candidates, original_message, is_followup)
        else:
            # Нет кандидатов
            return self._create_error_result("Не удалось определить услугу")

    def _create_ambiguous_result(self, candidates: List[Dict], original_message: str = "", is_followup: bool = False) -> Dict:
        """Создание результата с неопределенностью"""
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

        # Есть кандидаты - задаем уточняющий вопрос для понимания контекста
        return {
            'status': 'AMBIGUOUS',
            'candidates': candidates[:3],
            'candidate_names': [c.get('service_name', 'Unknown') for c in candidates[:3]],
            'message': self._generate_context_clarification_question(candidates[:3], original_message, is_followup),
            'needs_clarification': True,
            'clarification_type': 'context',
            'is_followup': is_followup
        }

    def _generate_clarification_questions(self) -> str:
        """Генерирует умные уточняющие вопросы"""
        return """🤔 Я не совсем понял проблему. Давайте уточним:

💧 Что именно случилось:
• Течь/протечка воды
• Сломалось оборудование
• Нет отопления/света
• Что-то другое

📍 Где именно это произошло: в квартире у вас или на территории общедомового имущества?

Пожалуйста, опишите подробнее, что и где произошло."""

    def _generate_context_clarification_question(self, candidates: List[Dict], original_message: str = "", is_followup: bool = False) -> str:
        """Генерирует уточняющий вопрос для понимания контекста"""

        # Проверяем наличие услуг с разными типами локации
        # Упрощенный анализ на основе названий услуг
        try:
            # Анализируем названия услуг на предмет локации
            inside_keywords = ['квартир', 'в квартире', 'моя']
            common_keywords = ['лифт', 'подъезд', 'лестниц', 'крыш', 'подвал', 'общ']

            has_inside = any(any(keyword in candidate.get('service_name', '').lower() for keyword in inside_keywords) for candidate in candidates)
            has_common = any(any(keyword in candidate.get('service_name', '').lower() for keyword in common_keywords) for candidate in candidates)

            # Если есть оба типа локаций - задаем ключевой вопрос
            if has_inside and has_common:
                return """📍 Где именно это произошло: в квартире у вас или на территории общедомового имущества?

Это поможет мне точно определить нужную услугу."""
        except Exception as e:
            logger.error(f"Ошибка анализа локаций: {e}")

        # Анализируем типы кандидатов для генерации релевантного вопроса
        location_keywords = {
            'квартира': ['квартир', 'в квартире'],
            'подвал': ['подвал', 'в подвале'],
            'крыша': ['крыш', 'крыши', 'с крыши'],
            'лифт': ['лифт', 'лифта'],
            'общие зоны': ['подъезд', 'лестниц', 'коридор', 'обществ'],
            'коммуникации': ['вод', 'отопление', 'канализац', 'электрич', 'газ']
        }

        incident_keywords = {
            'течь': ['теч', 'протека', 'капа', 'утечка'],
            'поломка': ['сломал', 'не работает', 'поломк', 'испортил'],
            'отсутствие': ['нет', 'отсутству', 'пропал'],
            'засор': ['засор', 'забил', 'пробка'],
            'ремонт': ['ремонт', 'починить', 'восстановить']
        }

        # Находим ключевые слова в названиях услуг
        found_locations = []
        found_incidents = []

        for candidate in candidates:
            name = candidate.get('service_name', '').lower()
            for location, keywords in location_keywords.items():
                if any(keyword in name for keyword in keywords):
                    found_locations.append(location)

            for incident, keywords in incident_keywords.items():
                if any(keyword in name for keyword in keywords):
                    found_incidents.append(incident)

        # Убираем дубликаты
        found_locations = list(set(found_locations))
        found_incidents = list(set(found_incidents))

        # Генерируем вопрос на основе анализа
        if found_locations and found_incidents:
            if len(found_locations) > 1:
                location_question = "📍 Где именно это произошло?\n• " + '\n• '.join(found_locations)
            else:
                location_question = f"📍 Где именно это произошло: {found_locations[0]}?"

            return f"{location_question}\n\nОпишите подробнее, пожалуйста."

        elif found_locations:
            if len(found_locations) > 1:
                return f"📍 Где именно проблема?\n• " + '\n• '.join(found_locations) + "\n\nПожалуйста, уточните."
            else:
                return f"📍 {found_locations[0].capitalize()}. Опишите, пожалуйста, что именно случилось."

        elif found_incidents:
            return f"🔧 {found_incidents[0].capitalize()}. Уточните, пожалуйста, где именно это произошло."

        # Общий уточняющий вопрос
        base_question = "🤔 Чтобы я точнее понял проблему, пожалуйста, уточните:\n• Что именно произошло?\n• Где именно это произошло: в квартире у вас или на территории общедомового имущества?\n• Когда это началось?"

        # Если это уточняющее сообщение, даем более конкретный вопрос
        if is_followup and original_message:
            return f"🤔 Спасибо за уточнение! Чтобы лучше понять ситуацию с '{original_message}', пожалуйста, уточните:\n• Точные детали проблемы\n• Где именно это произошло: в квартире у вас или на территории общедомового имущества?\n• Когда и как это произошло"

        return base_question

    def _create_error_result(self, error_message: str) -> Dict:
        return {
            'status': 'ERROR',
            'error': error_message,
            'message': f'Произошла техническая ошибка: {error_message}',
            'candidates': []
        }

    def _get_service_name(self, service_id: int) -> str:
        """Получить название услуги по ID"""
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

    def get_service_details(self, service_id: int) -> Dict:
        """Получить детальную информацию об услуге"""
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