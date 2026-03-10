#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Главный оркестратор системы обнаружения услуг Telegram бота УК "Аспект"
Объединяет все модули в единую систему обработки сообщений
"""

import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Any, List
from django.db import connection

from service_detection_modules import (
    AntiSpamFilter,
    PrecisionFunnelLevel1,
    PrecisionFunnelLevel2,
    PrecisionFunnelLevel3,
    AddressExtractor
)
from ai_cost_tracking_service import AICostTrackingService

# Настройка логирования
logger = logging.getLogger(__name__)


class ServiceDetectionOrchestrator:
    """Главный оркестратор всей системы"""

    def __init__(self):
        # Инициализируем компоненты
        self.spam_filter = AntiSpamFilter()
        self.level1 = PrecisionFunnelLevel1()
        self.level2 = PrecisionFunnelLevel2()
        self.level3 = PrecisionFunnelLevel3()
        self.address_extractor = AddressExtractor()
        self.cost_tracker = AICostTrackingService()

        # Состояния диалогов для мультиступенчатых взаимодействий
        self.dialog_states = {}

    def process_message(self,
                       message_text: str,
                       telegram_user_id: int,
                       telegram_username: str = None,
                       dialog_id: str = None) -> Dict:
        """
        Главный метод обработки сообщения

        Args:
            message_text: Текст сообщения от пользователя
            telegram_user_id: ID пользователя в Telegram
            telegram_username: Имя пользователя в Telegram
            dialog_id: ID диалога (если None, будет создан новый)

        Returns:
            Dict с результатом обработки
        """

        trace_id = str(uuid.uuid4())
        if not dialog_id:
            dialog_id = str(uuid.uuid4())

        # Логируем начало обработки
        self._log_trace_start(trace_id, dialog_id, telegram_user_id, telegram_username, message_text)

        # ===== ЭТАП 1: ANTI-SPAM =====
        spam_check = self.spam_filter.check_message(message_text)
        self._log_span(trace_id, 'SPAM_CHECK', {'input': message_text}, spam_check)

        if spam_check['is_spam']:
            self._log_trace_end(trace_id, 'SPAM_CHECK', 'REJECTED_SPAM')
            return {
                'status': 'REJECTED_SPAM',
                'message': 'К сожалению, это сообщение не похоже на запрос услуги. ' +
                          'Если у вас есть проблема с коммунальными услугами, пожалуйста, опишите её.',
                'trace_id': trace_id,
                'dialog_id': dialog_id
            }

        # Проверяем, не ожидаем ли мы адрес от пользователя
        if dialog_id in self.dialog_states:
            state = self.dialog_states[dialog_id]
            if state.get('stage') == 'AWAITING_ADDRESS':
                return self._process_address_input(trace_id, dialog_id, message_text,
                                                 telegram_user_id, telegram_username, state)

            elif state.get('stage') == 'AWAITING_CONFIRMATION':
                return self._process_confirmation(trace_id, dialog_id, message_text,
                                                 telegram_user_id, telegram_username, state)

        # ===== ЭТАП 2: ВОРОНКА ТОЧНОСТИ (PRECISION FUNNEL) =====
        # Level 1: Fast Python-based Filtering
        level1_result = self.level1.run(message_text)
        self._log_span(trace_id, 'LEVEL1_FILTERING', {'input': message_text}, level1_result)

        service_id = None
        confidence = 0.0
        final_candidates = []

        if level1_result['decision'] == 'PROCEED_TO_ADDRESS':
            service_id = level1_result['service_id']
            confidence = level1_result['confidence']
            final_candidates = level1_result.get('candidates', [])

        # Level 2: Vector Embeddings + Fuzzy Match (если нужно)
        elif level1_result['decision'] == 'ESCALATE_TO_LEVEL_2':
            level2_result = self.level2.run(message_text, level1_result.get('candidates', []))
            self._log_span(trace_id, 'LEVEL2_FUZZY', level1_result, level2_result)

            if level2_result['decision'] == 'PROCEED_TO_ADDRESS':
                service_id = level2_result['service_id']
                confidence = level2_result['confidence']
                final_candidates = level2_result.get('candidates', [])
            elif level2_result['decision'] == 'ESCALATE_TO_LEVEL_3_OR_CLARIFY':
                # Переходим на Level 3
                level3_result = self.level3.run(message_text, level2_result)
                self._log_span(trace_id, 'LEVEL3_LLM', level2_result, level3_result)

                if level3_result['decision'] == 'PROCEED_TO_ADDRESS':
                    service_id = level3_result['service_id']
                    confidence = level3_result['confidence']
                    final_candidates = [(service_id, confidence)]

        # Level 3: LLM-based Search (если Level 1 сразу направил)
        elif level1_result['decision'] == 'ESCALATE_TO_LEVEL_2' and not service_id:
            level3_result = self.level3.run(message_text, level1_result)
            self._log_span(trace_id, 'LEVEL3_LLM_DIRECT', level1_result, level3_result)

            if level3_result['decision'] == 'PROCEED_TO_ADDRESS':
                service_id = level3_result['service_id']
                confidence = level3_result['confidence']
                final_candidates = [(service_id, confidence)]

        if not service_id:
            # Не смогли определить - просим уточнение
            self._log_trace_end(trace_id, 'SERVICE_DETECTION', 'CANNOT_DETERMINE')
            return {
                'status': 'CANNOT_DETERMINE',
                'message': 'К сожалению, не удалось определить услугу. ' +
                          'Пожалуйста, опишите проблему подробнее, например: "протечка воды из потолка" или "нет света в квартире".',
                'trace_id': trace_id,
                'dialog_id': dialog_id,
                'suggestions': self._get_service_suggestions()
            }

        # ===== ЭТАП 3: ИЗВЛЕЧЕНИЕ АДРЕСА =====
        address_components = self.address_extractor.extract_address_components(message_text)
        self._log_span(trace_id, 'ADDRESS_EXTRACTION', {'input': message_text}, address_components)

        # Если адрес не найден в сообщении
        if not address_components.get('street') or not address_components.get('house_number'):
            # Проверяем, можно ли обойтись без адреса для этой услуги
            try:
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT rc.category_name, rl.localization_name
                        FROM services_catalog sc
                        JOIN ref_categories rc ON sc.category_id = rc.category_id
                        JOIN ref_localization rl ON sc.localization_id = rl.localization_id
                        WHERE sc.service_id = %s
                    """, [service_id])
                    result = cursor.fetchone()

                    if result:
                        category_name, localization_name = result

                        # Для общедомовых проблем можно не требовать точный адрес
                        if localization_name == 'Общедомовое':
                            self._log_trace_end(trace_id, 'ADDRESS_NOT_REQUIRED', 'COMMON_AREA')

                            service_name = self._get_service_name(service_id)
                            return {
                                'status': 'PENDING_CONFIRMATION',
                                'message': f"""🔍 Я понял, что у вас общедомовая проблема:

**Услуга:** {service_name}
📍 **Тип:** Общедомовое имущество

Это правильно? Отправьте "Да" для подтверждения или уточните адрес если нужно.""",
                                'trace_id': trace_id,
                                'dialog_id': dialog_id,
                                'service_id': service_id,
                                'service_name': service_name,
                                'building_id': None,
                                'unit_id': None,
                                'confidence': confidence,
                                'expected_next': 'confirmation',
                                'candidates': final_candidates
                            }
            except:
                pass

            # Во всех остальных случаях просим адрес
            self._log_trace_end(trace_id, 'ADDRESS_EXTRACTION', 'INCOMPLETE')

            # Сохраняем состояние диалога
            self.dialog_states[dialog_id] = {
                'stage': 'AWAITING_ADDRESS',
                'service_id': service_id,
                'confidence': confidence,
                'candidates': final_candidates,
                'trace_id': trace_id
            }

            service_name = self._get_service_name(service_id)
            return {
                'status': 'NEED_ADDRESS',
                'message': f' Я определил, что у вас проблема с: **{service_name}**\n\n' +
                          '📍 Теперь, пожалуйста, укажите адрес:\n' +
                          'Улица и номер дома (и квартиры, если нужно)\n\n' +
                          'Например: ул. Ленина, д. 5, кв. 10',
                'trace_id': trace_id,
                'dialog_id': dialog_id,
                'service_id': service_id,
                'service_name': service_name,
                'expected_next': 'address_input',
                'candidates': final_candidates
            }

        # Валидируем адрес в БД
        address_match = self.address_extractor.validate_and_match_to_db(address_components)
        self._log_span(trace_id, 'ADDRESS_VALIDATION', address_components, address_match)

        building_id = None
        unit_id = None
        address_full = None

        if address_match.get('found'):
            # Адрес найден в БД
            building_id = address_match['building_id']
            unit_id = address_match.get('unit_id')
            address_full = address_match.get('address_full')
        else:
            # Адрес не найден в БД, но есть в сообщении - используем его как есть
            self._log_span(trace_id, 'ADDRESS_NOT_IN_DB', address_components, {'message': 'Address found in message but not in KLADR'})
            address_full = self._format_address(address_components)

        # ===== ЭТАП 4: ФИНАЛЬНОЕ ПОДТВЕРЖДЕНИЕ =====
        service_name = self._get_service_name(service_id)

        confirmation_message = f"""🔍 Я понял, что вы обращаетесь по поводу:

**Услуга:** {service_name}
📍 **Адрес:** {address_full}

Это правильно? Отправьте "Да" для подтверждения или "Нет" для исправления."""

        # Сохраняем состояние диалога
        self.dialog_states[dialog_id] = {
            'stage': 'AWAITING_CONFIRMATION',
            'service_id': service_id,
            'building_id': building_id,
            'unit_id': unit_id,
            'address_full': address_full,
            'confidence': confidence,
            'trace_id': trace_id
        }

        self._log_trace_end(trace_id, 'CONFIRMATION', 'PENDING_CONFIRMATION')

        return {
            'status': 'PENDING_CONFIRMATION',
            'message': confirmation_message,
            'trace_id': trace_id,
            'dialog_id': dialog_id,
            'service_id': service_id,
            'service_name': service_name,
            'building_id': building_id,
            'unit_id': unit_id,
            'confidence': confidence,
            'expected_next': 'confirmation'
        }

    def _process_address_input(self, trace_id: str, dialog_id: str, address_text: str,
                             telegram_user_id: int, telegram_username: str, state: Dict) -> Dict:
        """Обработка ввода адреса"""

        service_id = state['service_id']
        confidence = state['confidence']

        # Извлекаем компоненты адреса
        address_components = self.address_extractor.extract_address_components(address_text)
        self._log_span(trace_id, 'ADDRESS_EXTRACTION', {'input': address_text}, address_components)

        # Валидируем адрес
        address_match = self.address_extractor.validate_and_match_to_db(address_components)
        self._log_span(trace_id, 'ADDRESS_VALIDATION', address_components, address_match)

        if not address_match.get('found'):
            clarification = self.address_extractor.ask_clarification_if_needed(
                address_components,
                address_match
            )

            if clarification['need_clarification']:
                return {
                    'status': 'ADDRESS_CLARIFICATION',
                    'message': clarification['message'],
                    'trace_id': trace_id,
                    'dialog_id': dialog_id,
                    'service_id': service_id,
                    'expected_next': 'address_clarification'
                }

        # Адрес найден - переходим к подтверждению
        building_id = address_match['building_id']
        unit_id = address_match.get('unit_id')
        address_full = address_match.get('address_full', self._format_address(address_components))
        service_name = self._get_service_name(service_id)

        confirmation_message = f"""🔍 Отлично! Теперь у нас есть все данные:

**Услуга:** {service_name}
📍 **Адрес:** {address_full}

Все верно? Отправьте "Да" для создания заявки."""

        # Обновляем состояние диалога
        self.dialog_states[dialog_id] = {
            'stage': 'AWAITING_CONFIRMATION',
            'service_id': service_id,
            'building_id': building_id,
            'unit_id': unit_id,
            'address_full': address_full,
            'confidence': confidence,
            'trace_id': trace_id
        }

        return {
            'status': 'PENDING_CONFIRMATION',
            'message': confirmation_message,
            'trace_id': trace_id,
            'dialog_id': dialog_id,
            'service_id': service_id,
            'service_name': service_name,
            'building_id': building_id,
            'unit_id': unit_id,
            'confidence': confidence,
            'expected_next': 'confirmation'
        }

    def _process_confirmation(self, trace_id: str, dialog_id: str, confirmation_text: str,
                            telegram_user_id: int, telegram_username: str, state: Dict) -> Dict:
        """Обработка подтверждения"""

        confirmation_lower = confirmation_text.lower().strip()

        if confirmation_lower in ['да', 'yes', 'y', 'верно', 'правильно']:
            # Подтверждение получено - создаем заявку
            output_json = self._create_output_json(
                trace_id, dialog_id, state,
                telegram_user_id, telegram_username
            )

            # Удаляем состояние диалога
            if dialog_id in self.dialog_states:
                del self.dialog_states[dialog_id]

            self._log_trace_end(trace_id, 'TICKET_CREATION', 'SUCCESS')

            return {
                'status': 'SUCCESS',
                'message': f' Спасибо! Ваша заявка #{trace_id[:8]} зарегистрирована.\n\n' +
                          'Наши специалисты свяжутся с вами в ближайшее время.',
                'trace_id': trace_id,
                'dialog_id': dialog_id,
                'output_json': output_json,
                'ticket_number': trace_id[:8]
            }

        elif confirmation_lower in ['нет', 'no', 'n', 'неверно', 'неправильно']:
            # Отмена или исправление
            if dialog_id in self.dialog_states:
                del self.dialog_states[dialog_id]

            self._log_trace_end(trace_id, 'CONFIRMATION', 'CANCELLED')

            return {
                'status': 'CANCELLED',
                'message': 'Заявка отменена. Пожалуйста, опишите проблему заново.',
                'trace_id': trace_id,
                'dialog_id': dialog_id
            }

        else:
            # Непонятный ответ
            return {
                'status': 'CONFIRMATION_RETRY',
                'message': 'Пожалуйста, ответьте "Да" если всё верно, или "Нет" чтобы отменить заявку.',
                'trace_id': trace_id,
                'dialog_id': dialog_id,
                'expected_next': 'confirmation'
            }

    def _create_output_json(self, trace_id: str, dialog_id: str, state: Dict,
                          telegram_user_id: int, telegram_username: str) -> Dict:
        """Создаем финальный JSON вывод"""

        service_id = state['service_id']
        scenario_id = self._get_scenario_id(service_id)
        service_name = self._get_service_name(service_id)
        building_id = state.get('building_id')
        unit_id = state.get('unit_id')
        address_full = state.get('address_full')
        confidence = state.get('confidence', 0.0)

        output_json = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'telegram_user_id': telegram_user_id,
            'telegram_username': telegram_username,
            'dialog_id': dialog_id,
            'service_id': service_id,
            'scenario_id': scenario_id,
            'service_name': service_name,
            'building_id': building_id,
            'unit_id': unit_id,
            'address_full': address_full,
            'confidence': confidence,
            'trace_id': trace_id
        }

        # Сохраняем в БД
        self._save_final_ticket(output_json)

        return output_json

    def _save_final_ticket(self, output_json: Dict):
        """Сохраняем финальную заявку в базу данных"""
        try:
            from django.db import connection

            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO debug_trace_log
                    (trace_id, dialog_id, telegram_user_id, telegram_username,
                     incoming_message, incoming_message_datetime,
                     service_id, service_detected, service_confidence_score,
                     detected_address, address_building_id, address_unit_id,
                     processing_stage, final_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, [
                    output_json['trace_id'],
                    output_json['dialog_id'],
                    output_json['telegram_user_id'],
                    output_json['telegram_username'],
                    f"Услуга: {output_json['service_name']}, Адрес: {output_json['address_full']}",
                    datetime.utcnow(),
                    output_json['service_id'],
                    True,
                    output_json['confidence'],
                    output_json['address_full'],
                    output_json['building_id'],
                    output_json['unit_id'],
                    'COMPLETE',
                    'SUCCESS'
                ])

                logger.info(f"Заявка {output_json['trace_id']} успешно сохранена в БД")
        except Exception as e:
            logger.error(f"Ошибка сохранения заявки в БД: {e}")

    def _get_service_name(self, service_id: int) -> str:
        """Получить название услуги по ID (временно упрощен)"""
        # Временное соответствие service_id -> названию на основе реальных данных
        service_names = {
            1: "Упало дерево/ветка на провода/дом/дорогу",
            2: "Уход за зелёными зонами, газонами, деревьями и кустарниками",
            3: "Разрушение асфальта, ямы, покрытий дворовых территорий",
            4: "Сломаны малые архитектурные формы",
            5: "Отмостка",
            6: "Очистка лотков и приямков водоотведения",
            7: "Мусорные контейнеры переполнены",
            8: "Снег и наледь на территории",
            9: "Дезинсекция/дератизация",
            10: "Засор ливнёвой канализации/дренажных систем"
        }
        return service_names.get(service_id, f"Услуга #{service_id}")

    def _get_scenario_id(self, service_id: int) -> str:
        """Получить ID сценария по ID услуги"""
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT scenario_id FROM services_catalog WHERE service_id = %s
                """, [service_id])
                result = cursor.fetchone()
                return result[0] if result else None
        except:
            return None

    def _format_address(self, address_components: Dict) -> str:
        """Отформатировать адрес из компонентов"""
        parts = []
        if address_components.get('street'):
            parts.append(f"ул. {address_components['street']}")
        if address_components.get('house_number'):
            parts.append(f"д. {address_components['house_number']}")
        if address_components.get('apartment_number'):
            parts.append(f"кв. {address_components['apartment_number']}")
        return ", ".join(parts)

    def _get_service_suggestions(self) -> List[str]:
        """Получить подсказки по услугам"""
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT scenario_name FROM services_catalog
                    WHERE is_active = TRUE
                    ORDER BY scenario_id
                    LIMIT 10
                """)
                results = cursor.fetchall()
                return [result[0] for result in results]
        except:
            return [
                "протечка воды",
                "отсутствие света",
                "проблемы с отоплением",
                "засор канализации",
                "поломка лифта"
            ]

    def _log_trace_start(self, trace_id: str, dialog_id: str,
                        telegram_user_id: int, telegram_username: str,
                        message_text: str):
        """Логировать начало трассировки"""
        try:
            logger.info(f"TRACE START: {trace_id} | User: {telegram_user_id} | Message: {message_text[:50]}...")
        except Exception as e:
            logger.error(f"Ошибка логирования трассировки: {e}")

    def _log_trace_end(self, trace_id: str, stage: str, status: str):
        """Завершить лог трассировки"""
        try:
            logger.info(f"TRACE END: {trace_id} | Stage: {stage} | Status: {status}")
        except Exception as e:
            logger.error(f"Ошибка завершения трассировки: {e}")

    def _log_span(self, trace_id: str, span_name: str,
                  input_data: Dict, output_data: Dict):
        """Логировать span для отладки"""
        try:
            logger.info(f"SPAN: {trace_id} | {span_name} | Input: {str(input_data)[:50]}... | Output: {str(output_data)[:50]}...")
        except Exception as e:
            logger.error(f"Ошибка логирования span: {e}")

    # =====================================================
    # Часть 6: Методы для финального JSON
    # =====================================================

    def create_output_json(self,
                          service_id: int,
                          service_name: str,
                          service_confidence: float,
                          address_components: Dict,
                          user_name: str = None,
                          user_phone: str = None,
                          user_email: str = None,
                          description: str = None,
                          urgency_level: str = None,
                          trace_id: str = None) -> Dict[str, Any]:
        """
        Создать финальный JSON для отправки пользователю.

        Args:
            service_id: ID услуги из services_catalog
            service_name: Название услуги
            service_confidence: Уверенность в услуге (0-1)
            address_components: Dict с адресом {street, house_number, apartment_number, entrance}
            user_name: Имя пользователя
            user_phone: Телефон пользователя
            user_email: Email пользователя
            description: Описание проблемы из сообщения
            urgency_level: Уровень срочности (S0, S1, S2, S3)
            trace_id: ID трассировки для логирования

        Returns:
            Dict с финальным JSON для пользователя
        """
        try:
            # Рассчитываем срочность по услуге
            if urgency_level is None:
                urgency_level = self._get_urgency_by_service(service_id)

            # Восстанавливаем полный адрес из компонентов
            full_address = self._build_full_address(address_components)

            # Получаем код объекта из address_lookup_table
            building_code = self._get_building_code_by_address(full_address)

            # Создаем базовый JSON
            output_json = {
                'кодУслуги': str(service_id),
                'срочность': urgency_level,
                'описание': description or service_name,
                'адрес': full_address,
                'кодОбъектаОбслуживания': building_code,
                'имя': user_name or 'Не указано',
                'телефон': user_phone or 'Не указан',
                'email': user_email,
                'уверенность': round(service_confidence, 2),
                'дата': datetime.now(timezone.utc).isoformat() + 'Z',
                'статус': 'к_подтверждению',
                'trace_id': trace_id
            }

            # Добавляем номер квартиры если есть
            if address_components.get('apartment_number'):
                output_json['номерКвартиры'] = address_components['apartment_number']

            # Добавляем подъезд если есть
            if address_components.get('entrance'):
                output_json['подъезд'] = address_components['entrance']

            # Добавляем адресные компоненты для внутреннего использования
            output_json['адресныеКомпоненты'] = address_components

            # Рассчитаем примерное время выполнения
            output_json['предварительноеВремяВыполнения'] = self._get_estimated_time(urgency_level)

            # Добавляем служебные поля
            output_json['созданВ'] = 'telegram_bot'
            output_json['версияСистемы'] = '1.0'

            logger.info(f"Created output JSON for service {service_id}: {output_json}")
            return output_json

        except Exception as e:
            logger.error(f"Error creating output JSON: {e}")
            return {
                'кодУслуги': str(service_id),
                'срочность': urgency_level or 'S2',
                'описание': description or service_name,
                'адрес': self._build_full_address(address_components),
                'кодОбъектаОбслуживания': 'unknown',
                'имя': user_name or 'Не указано',
                'телефон': user_phone or 'Не указан',
                'уверенность': round(service_confidence, 2),
                'дата': datetime.now(timezone.utc).isoformat() + 'Z',
                'статус': 'к_подтверждению',
                'ошибка': str(e)
            }

    def _get_urgency_by_service(self, service_id: int) -> str:
        """
        Рассчитать срочность по типу услуги.

        S0 - Критическая (прорыв трубы, затопление)
        S1 - Срочная (протечка, отсутствие воды/газа)
        S2 - Обычная (поломка, шум)
        S3 - Плановая (консультация, проверка)
        """
        try:
            with connection.cursor() as cursor:
                # Получаем информацию об услуге
                cursor.execute("""
                    SELECT s.urgency_id, s.scenario_name, u.urgency_name
                    FROM services_catalog s
                    LEFT JOIN ref_urgency u ON s.urgency_id = u.urgency_id
                    WHERE s.service_id = %s
                """, [service_id])

                result = cursor.fetchone()
                if result and result[0]:
                    urgency_id = result[0]
                    scenario_name = result[1].lower()

                    # Определяем срочность на основе ID и сценария
                    if urgency_id in [1, 2]:  # Критический и срочный
                        return 'S0' if 'авар' in scenario_name or 'прорыв' in scenario_name else 'S1'
                    elif urgency_id == 3:  # Обычный
                        return 'S2'
                    elif urgency_id == 4:  # Плановый
                        return 'S3'
                    else:
                        return 'S2'
                else:
                    # Анализ по названию сценария
                    scenario_name = result[1].lower() if result and result[1] else ''

                    if any(keyword in scenario_name for keyword in ['авар', 'прорыв', 'затоп', 'пожар']):
                        return 'S0'
                    elif any(keyword in scenario_name for keyword in ['протечк', 'отсутств', 'не работ', 'перебой']):
                        return 'S1'
                    elif any(keyword in scenario_name for keyword in ['консульт', 'проверк', 'осмотр']):
                        return 'S3'
                    else:
                        return 'S2'

        except Exception as e:
            logger.error(f"Error getting urgency for service {service_id}: {e}")
            return 'S2'  # По умолчанию обычная срочность

    def _build_full_address(self, address_components: Dict) -> str:
        """Построить полный адрес из компонентов"""
        try:
            parts = []

            if address_components.get('street'):
                street = address_components['street'].strip()
                if not street.startswith(('ул.', 'проспект', 'пер.', 'бул.')):
                    street = f"ул. {street}"
                parts.append(street)

            if address_components.get('house_number'):
                parts.append(f"д. {address_components['house_number']}")

            if address_components.get('apartment_number'):
                parts.append(f"кв. {address_components['apartment_number']}")

            if address_components.get('entrance'):
                parts.append(f"подъезд {address_components['entrance']}")

            return ", ".join(parts) if parts else "Адрес не указан"

        except Exception as e:
            logger.error(f"Error building full address: {e}")
            return "Адрес не указан"

    def _get_building_code_by_address(self, address: str) -> str:
        """Получить код объекта из базы адресов (временно упрощен)"""
        # Временно возвращаем простой код на основе адреса
        if address and address != "Адрес не указан":
            # Создаем простой hash адреса для кода объекта
            import hashlib
            address_hash = hashlib.md5(address.encode()).hexdigest()[:8]
            return f"addr_{address_hash}"
        return "unknown"

    def _get_estimated_time(self, urgency_level: str) -> str:
        """Получить примерное время выполнения услуги"""
        time_estimates = {
            'S0': '1-2 часа',
            'S1': '2-4 часа',
            'S2': '4-8 часов',
            'S3': '1-3 дня'
        }
        return time_estimates.get(urgency_level, '4-8 часов')

    def save_final_ticket(self, output_json: Dict, dialog_id: str = None) -> str:
        """
        Сохранить финальную заявку в базу данных (временно упрощен).

        Args:
            output_json: JSON с данными заявки
            dialog_id: ID диалога

        Returns:
            ID созданной заявки
        """
        try:
            ticket_id = str(uuid.uuid4())

            # Временно сохраняем только в лог вместо БД
            logger.info(f"TICKET SAVED (DB disabled): {ticket_id[:8]}")
            logger.info(f"Service: {output_json.get('описание', 'Unknown')}")
            logger.info(f"User: {output_json.get('имя', 'Unknown')}")
            logger.info(f"Address: {output_json.get('адресныеКомпоненты', {})}")

            return ticket_id[:8]  # Возвращаем короткий ID

        except Exception as e:
            logger.error(f"Error saving final ticket: {e}")
            return "ERROR"  # Возвращаем ошибочный ID

    def format_json_for_display(self, output_json: Dict) -> str:
        """
        Отформатировать JSON для красивого отображения в Telegram.

        Args:
            output_json: JSON с данными заявки

        Returns:
            Отформатированная строка для отправки в чат
        """
        try:
            # Создаем красивое представление заявки
            message_parts = [
                " *Заявка создана*",
                "",
                f"🔍 *Услуга:* {output_json.get('описание', 'Не указано')}",
                f"📍 *Адрес:* {output_json.get('адрес', 'Не указан')}",
            ]

            if output_json.get('номерКвартиры'):
                message_parts.append(f"🏠 *Квартира:* {output_json['номерКвартиры']}")

            if output_json.get('подъезд'):
                message_parts.append(f"🚪 *Подъезд:* {output_json['подъезд']}")

            message_parts.extend([
                f"👤 *Имя:* {output_json.get('имя', 'Не указано')}",
                f"📞 *Телефон:* {output_json.get('телефон', 'Не указан')}",
                f"🚨 *Срочность:* {output_json.get('срочность', 'S2')}",
                f"⏱ *Примерное время:* {output_json.get('предварительноеВремяВыполнения', '4-8 часов')}",
                f"🔢 *Уверенность:* {output_json.get('уверенность', 0):.0%}",
            ])

            # Добавляем ID заявки если есть
            if 'request_uuid' in output_json:
                message_parts.append(f"*ID заявки:* {output_json['request_uuid'][:8]}...")

            return "\n".join(message_parts)

        except Exception as e:
            logger.error(f"Error formatting JSON for display: {e}")
            return " Заявка создана! Данные отправлены в систему."

    def generate_confirmation_buttons(self, output_json: Dict) -> List[List[Dict]]:
        """
        Сгенерировать кнопки подтверждения заявки.

        Args:
            output_json: JSON с данными заявки

        Returns:
            Список кнопок для inline клавиатуры
        """
        try:
            return [
                [
                    {"text": " Всё верно", "callback_data": "confirm_yes"},
                    {"text": "❌ Изменить", "callback_data": "confirm_no"}
                ]
            ]

        except Exception as e:
            logger.error(f"Error generating confirmation buttons: {e}")
            return []