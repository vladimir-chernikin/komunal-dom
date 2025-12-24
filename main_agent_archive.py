#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Главный Агент системы определения услуг - исправленная версия
"""

import logging
import asyncio
import traceback
from typing import Dict, List, Any, Tuple, Optional
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
    Главный Агент координирует работу микросервисов
    """

    def __init__(self):
        self.tag_search = None
        self.semantic_search = None
        self.vector_search = None
        self.ai_agent = None
        self.confidence_threshold = 0.75

        self._init_services()
        logger.info("Главный Агент инициализирован с микросервисной архитектурой")

    def _init_services(self):
        """Инициализация микросервисов"""
        try:
            from tag_search_service_v2 import TagSearchServiceV2
            self.tag_search = TagSearchServiceV2()
            logger.info("TagSearchServiceV2 инициализирован")
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
        """
        original_message = message_text
        is_followup = False

        if user_context:
            original_message = user_context.get('original_message', message_text)
            is_followup = user_context.get('is_followup', False)
            dialog_history = user_context.get('dialog_history', [])

            if is_followup and dialog_history:
                logger.info(f"Главный Агент обрабатывает уточняющее сообщение: '{original_message}'")
            else:
                logger.info(f"Главный Агент начал обработку: '{message_text[:50]}...'")
        else:
            logger.info(f"Главный Агент начал обработку: '{message_text[:50]}...'")

        search_text = message_text

        try:
            # Запускаем параллельный поиск через 3 основных микросервиса
            search_tasks = []

            if self.tag_search:
                search_tasks.append(self._run_tag_search(search_text))

            if self.semantic_search:
                search_tasks.append(self._run_semantic_search(search_text))

            if self.vector_search:
                search_tasks.append(self._run_vector_search(search_text))

            # Ждем результаты от 3 основных микросервисов
            if search_tasks:
                search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            else:
                return self._create_error_result("Нет доступных микросервисов")

            # Собираем результаты и анализируем расхождения
            non_ai_results = []
            for result in search_results:
                if isinstance(result, Exception):
                    logger.error(f"Ошибка микросервиса: {result}")
                    continue
                if result and result.get('candidates'):
                    non_ai_results.append(result)

            # Анализируем необходимость AI
            need_ai = self._should_run_ai_agent(non_ai_results, search_text)

            # Запускаем AI только при существенном расхождении
            ai_tasks = []
            if need_ai and self.ai_agent:
                logger.info(f"Запускаем AI из-за расхождения результатов: {need_ai}")
                ai_tasks.append(self._run_ai_search(search_text))

            if ai_tasks:
                ai_results = await asyncio.gather(*ai_tasks, return_exceptions=True)
                for result in ai_results:
                    if isinstance(result, Exception):
                        logger.error(f"Ошибка AI сервиса: {result}")
                    elif result and result.get('candidates'):
                        non_ai_results.append(result)

            # Собираем и анализируем результаты от всех микросервисов (включая AI)
            all_candidates = []
            for result in non_ai_results:
                if result and result.get('candidates'):
                    all_candidates.extend(result['candidates'])

            # Анализируем результаты
            if not all_candidates:
                # Запускаем запасной метод определения
                logger.info("Основные микросервисы не нашли кандидатов, используем запасной метод")
                return self._fallback_service_detection(message_text)

            # Дедупликация и объединение результатов
            final_candidates = self._merge_candidates(all_candidates)

            # Анализ пересечений с учетом контекста
            analysis_result = self._analyze_intersections(final_candidates, original_message, is_followup)
            return analysis_result

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
                'message': '😔 Произошла техническая ошибка. Пожалуйста, опишите проблему другими словами.\n\n'
                         'Если проблема повторяется, напишите: "связь с диспетчером"',
                'candidates': []
            }

    async def _run_tag_search(self, message_text: str) -> Dict:
        try:
            return await self.tag_search.search(message_text)
        except Exception as e:
            logger.error(f"Ошибка TagSearchService: {e}")
            return {}

    async def _run_semantic_search(self, message_text: str) -> Dict:
        try:
            return await self.semantic_search.search(message_text)
        except Exception as e:
            logger.error(f"Ошибка SemanticSearchService: {e}")
            return {}

    async def _run_vector_search(self, message_text: str) -> Dict:
        try:
            return await self.vector_search.search(message_text)
        except Exception as e:
            logger.error(f"Ошибка VectorSearchService: {e}")
            return {}

    async def _run_ai_search(self, message_text: str) -> Dict:
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
        merged.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        logger.info(f"Дедуплицировано кандидатов: {len(merged)}")
        return merged

    def _analyze_intersections(self, candidates: List[Dict], original_message: str = "", is_followup: bool = False) -> Dict:
        """Анализ пересечений результатов от разных микросервисов"""
        try:
            if len(candidates) == 1:
                # Однозначный результат
                candidate = candidates[0]
                confidence = candidate.get('confidence', 0)
                needs_confirmation = confidence < 0.85 and not is_followup

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
                # Нет кандидатов - используем улучшенные уточняющие вопросы
                return self._create_ambiguous_result([], original_message, is_followup)
        except Exception as e:
            logger.error(f"Ошибка в _analyze_intersections: {e}")
            return self._create_ambiguous_result(candidates)

    def _create_ambiguous_result(self, candidates: List[Dict], original_message: str = "", is_followup: bool = False) -> Dict:
        """Создание результата с неопределенностью"""
        try:
            if not candidates:
                clarification_message = self._generate_clarification_questions(original_message)
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
        except Exception as e:
            logger.error(f"Ошибка в _create_ambiguous_result: {e}")
            return {
                'status': 'AMBIGUOUS',
                'candidates': candidates[:1] if candidates else [],
                'message': '🤔 Пожалуйста, уточните детали проблемы.',
                'needs_clarification': True
            }

    def _generate_clarification_questions(self, message_text: str = "") -> str:
        """Генерирует умные уточняющие вопросы"""
        # Используем fallback detection для улучшенных уточняющих вопросов
        if message_text:
            fallback_result = self._fallback_service_detection(message_text)
            if fallback_result.get('status') == 'AMBIGUOUS' and fallback_result.get('needs_clarification'):
                return fallback_result.get('message', '')

        # Стандартные вопросы если fallback не сработал
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
        try:
            # Упрощенный анализ на основе названий услуг
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

        # Общий уточняющий вопрос
        base_question = "🤔 Чтобы я точнее понял проблему, пожалуйста, уточните:\n• Что именно произошло?\n• Где именно это произошло: в квартире у вас или на территории общедомового имущества?\n• Когда это началось?"

        # Если это уточняющее сообщение, даем более конкретный вопрос
        if is_followup and original_message:
            return f"🤔 Спасибо за уточнение! Чтобы лучше понять ситуацию с '{original_message}', пожалуйста, уточните:\n• Точные детали проблемы\n• Где именно это произошло: в квартире у вас или на территории общедомового имущества?\n• Когда и как это произошло"

        return base_question

    def _should_run_ai_agent(self, results: List[Dict], search_text: str) -> Optional[str]:
        """
        Анализ необходимости запуска AI агента

        Args:
            results: Результаты от 3 основных микросервисов
            search_text: Исходный текст поиска

        Returns:
            Optional[str]: Причина запуска AI или None
        """
        if not results:
            return "no_results_from_basic_services"

        # Анализируем пересечения результатов
        service_sets = []
        for result in results:
            service_ids = {candidate['service_id'] for candidate in result.get('candidates', [])}
            service_sets.append(service_ids)

        # Если 3 результата не имеют пересечений
        if len(service_sets) == 3:
            intersection = set.intersection(*service_sets)
            union = set.union(*service_sets)

            # Расчет разнообразия результатов
            if len(intersection) == 0:
                if len(union) >= 3:
                    return "no_intersection_too_diverse"
                elif len(union) == 2:
                    return "no_intersection_two_candidates"

        # Если у ведущего кандидата низкая уверенность
        if results:
            best_confidence = 0.0
            for result in results:
                for candidate in result.get('candidates', []):
                    best_confidence = max(best_confidence, candidate.get('confidence', 0.0))

            if best_confidence < 0.4:
                return "low_confidence"

        # Если результаты сильно противоречат друг другу
        confidences = []
        for result in results:
            if result.get('candidates'):
                best_candidate = max(result.get('candidates'), key=lambda x: x.get('confidence', 0.0))
                confidences.append(best_candidate.get('confidence', 0.0))

        if len(confidences) >= 3:
            max_conf = max(confidences)
            min_conf = min(confidences)
            if max_conf - min_conf > 0.5:
                return "high_discrepancy"

        return None

    def _create_error_result(self, error_message: str) -> Dict:
        """Создание результата с ошибкой"""
        return {
            'status': 'ERROR',
            'error': error_message,
            'message': f'😔 Произошла техническая ошибка: {error_message}',
            'candidates': []
        }

    def _fallback_service_detection(self, message_text: str) -> Dict:
        """Запасной метод определения услуг по ключевым словам"""
        try:
            # Базовые ключевые слова для самых частых проблем
            water_keywords = ['теч', 'течет', 'протека', 'капа', 'утечк', 'льет', 'протек', 'затека', 'сырость', 'влага']
            equipment_keywords = ['сломал', 'не работает', 'испортил', 'повредил', 'поломк', 'брак']
            heating_keywords = ['нет отопления', 'холодно', 'не греет', 'отопление не работает', 'батарея холодная']
            electricity_keywords = ['нет света', 'света нет', 'выключили свет', 'нет электричества', 'электричество']
            lift_keywords = ['лифт', 'лифта', 'лифтом', 'лифт не работает']

            message_lower = message_text.lower()

            if any(keyword in message_lower for keyword in water_keywords):
                return {
                    'status': 'AMBIGUOUS',
                    'candidates': [],
                    'candidate_names': [],
                    'message': """📍 Похоже, у вас проблема с водой.

💧 Что именно произошло:
• Протекает/течет вода
• Течь из крана, батареи, труб
• Затопило квартиру/подвал
• Сырость на стенах/потолке

📍 Где именно это произошло: в квартире у вас или на территории общедомового имущества?

Пожалуйста, уточните детали.""",
                    'needs_clarification': True,
                    'clarification_type': 'water'
                }
            elif any(keyword in message_lower for keyword in equipment_keywords):
                return {
                    'status': 'AMBIGUOUS',
                    'candidates': [],
                    'candidate_names': [],
                    'message': """📍 Понимаю, у вас поломка оборудования.

🔧 Что именно сломалось:
• Бытовая техника
• Сантехника
• Электроприборы
• Другое оборудование

📍 Где это произошло: в квартире у вас или на территории общедомового имущества?

Опишите подробнее, что случилось.""",
                    'needs_clarification': True,
                    'clarification_type': 'equipment'
                }
            elif any(keyword in message_lower for keyword in heating_keywords):
                return {
                    'status': 'AMBIGUOUS',
                    'candidates': [],
                    'candidate_names': [],
                    'message': """📍 Похоже, проблема с отоплением.

🌡 Что именно не так:
• Батареи холодные
• Отопление не работает
• Нет горячей воды
• Тепло не включается

📍 Где именно это произошло: в квартире у вас или на территории общедомового имущества?

Пожалуйста, уточните детали.""",
                    'needs_clarification': True,
                    'clarification_type': 'heating'
                }
            elif any(keyword in message_lower for keyword in electricity_keywords):
                return {
                    'status': 'AMBIGUOUS',
                    'candidates': [],
                    'candidate_names': [],
                    'message': """📍 Похоже, проблема с электричеством.

⚡ Что именно не работает:
• Нет света в квартире
• Выключили электричество
• Сработал автомат
• Перебои с подачей

📍 Где именно это произошло: в квартире у вас или на территории общедомового имущества?

Опишите подробнее ситуацию.""",
                    'needs_clarification': True,
                    'clarification_type': 'electricity'
                }
            elif any(keyword in message_lower for keyword in lift_keywords):
                return {
                    'status': 'SUCCESS',
                    'service_id': 5,
                    'service_name': 'Сломался лифт',
                    'confidence': 0.9,
                    'source': 'fallback_detection',
                    'message': 'Я определил, что у вас проблема: Сломался лифт',
                    'candidates': []
                }

            # Если не смогли определить проблему
            return self._create_ambiguous_result([])

        except Exception as e:
            logger.error(f"Ошибка в fallback_service_detection: {e}")
            return self._create_ambiguous_result([])

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