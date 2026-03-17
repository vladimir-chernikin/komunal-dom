#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AddressExtractor Service - Извлечение и валидация адреса

НОВАЯ РЕАЛИЗАЦИЯ (2026-03-13):
- Использует Django ORM вместо прямых SQL запросов
- Работает с новой моделью KLADR (kladr.models)
- Поддерживает накопление адреса по частям для голосового интерфейса

ЗАМЕНА: old/service_detection_modules.py → AddressExtractor
"""

import logging
import re
from typing import Dict, Optional
from django.db.models import Q, Count

from kladr.models import KladrAddressObject, Building

logger = logging.getLogger(__name__)


class AddressExtractor:
    """
    Извлечение и валидация адреса с использованием Django ORM

    Основные методы:
    - extract_address_components() - извлечь компоненты из текста + объединить с памятью
    - validate_and_match_to_db() - валидировать и найти в БД
    """

    def __init__(self):
        """Инициализация"""
        logger.info("AddressExtractor initialized with Django ORM")

    def extract_address_components(
        self,
        text: str,
        context_memory: Dict = None
    ) -> Dict:
        """
        Извлечь компоненты адреса из текста И объединить с памятью.

        КЛЮЧЕВОЙ МЕТОД для восстановления адреса из кусков!

        Args:
            text: Текущее сообщение
            context_memory: Dict с компонентами из предыдущих сообщений
                       {city, street, house_number, apartment_number, entrance}

        Returns:
            Dict с адресными компонентами + confidence

        Пример:
        --------
        Message 1: "на Мира"
        → {street: 'Мира', house: None, ...}

        Message 2: "дом 25"
        → {street: 'Мира', house: '25', ...}  # ОБЪЕДИНЕНО!

        Message 3: "кв. 5"
        → {street: 'Мира', house: '25', apartment: '5', ...}  # ПОЛНЫЙ АДРЕС!
        """
        # ШАГ 1: Парсить текущее сообщение
        current_components = self._parse_address_text(text, context_memory=context_memory)

        # ШАГ 2: Объединить с памятью
        if context_memory:
            result = self._merge_with_memory(current_components, context_memory)
        else:
            result = current_components

        # ШАГ 3: Нормализовать
        result = self._normalize_components(result)

        # ШАГ 4: Рассчитать confidence (0-1)
        parts = sum(1 for v in [
            result.get('city'),
            result.get('street'),
            result.get('house_number'),
            result.get('apartment_number')
        ] if v)
        result['confidence'] = min(1.0, parts / 4.0)

        return result

    def _parse_address_text(self, text: str, context_memory: Dict = None) -> Dict:
        """
        Парсит текущее сообщение на предмет адресных компонентов.

        Args:
            text: Текст сообщения
            context_memory: Dict с предыдущими компонентами (для умного парсинга)

        Returns:
            Dict: Компоненты адреса из ТЕКУЩЕГО сообщения только
        """
        result = {
            'city': None,
            'street': None,
            'house_number': None,
            'apartment_number': None,
            'entrance': None
        }

        try:
            text_lower = text.lower()

            # 0. ГОРОД - распознаем ПЕРВЫМ!
            city_patterns = [
                r'(?:город|г\.?)\s+([А-Яа-яЁё-]{2,})(?:\s+|,|$)',
                r'^([А-Яа-яЁё-]{2,})\s+(?:ул\.?|улица|пр\.?|проспект|пер\.?|переулок)',
            ]

            for pattern in city_patterns:
                match = re.search(pattern, text_lower, re.IGNORECASE)
                if match:
                    city_candidate = match.group(1).strip().capitalize()

                    not_city_keywords = [
                        'теч', 'прорыв', 'сломал', 'засор', 'нет', 'горяч', 'холодн',
                        'батар', 'кран', 'труба', 'унитаз', 'смесит', 'раковин',
                        'дом', 'дома', 'доме', 'квартира', 'подъезд', 'этаж'
                    ]
                    is_not_city = any(kw in city_candidate.lower() for kw in not_city_keywords)

                    if not is_not_city:
                        result['city'] = city_candidate
                        logger.debug(f"Found city: {city_candidate}")
                        break

            # Если город НЕ найден - проверяем первое слово
            if not result.get('city'):
                words = text_lower.strip().split()

                if len(words) == 1 and not context_memory:
                    first_word = words[0].capitalize()

                    not_city_keywords = [
                        'теч', 'прорыв', 'сломал', 'засор', 'нет', 'горяч', 'холодн',
                        'батар', 'кран', 'труба', 'унитаз', 'смесит', 'раковин',
                        'дом', 'дома', 'доме', 'квартира', 'подъезд', 'этаж',
                        'на', 'в', 'у', 'от', 'из', 'с', 'по', 'к', 'для',
                        'улица', 'ул', 'проспект', 'пр', 'переулок', 'пер'
                    ]
                    is_not_city = first_word.lower() in not_city_keywords
                    is_number = bool(re.match(r'^\d+[а-яА-Я/]?$', first_word))

                    if not is_not_city and not is_number and len(first_word) >= 3:
                        result['city'] = first_word
                        logger.debug(f"Found city (single word): {first_word}")

                elif len(words) >= 2:
                    first_word = words[0].capitalize()

                    not_city_keywords = [
                        'теч', 'прорыв', 'сломал', 'засор', 'нет', 'горяч', 'холодн',
                        'батар', 'кран', 'труба', 'унитаз', 'смесит', 'раковин',
                        'дом', 'дома', 'доме', 'квартира', 'подъезд', 'этаж',
                        'на', 'в', 'у', 'от', 'из', 'с', 'по', 'к', 'для'
                    ]
                    is_not_city = first_word.lower() in not_city_keywords
                    is_number = bool(re.match(r'^\d+[а-яА-Я/]?$', first_word))

                    second_word = words[1] if len(words) > 1 else ''
                    is_street_like = (
                        second_word.endswith('а') or
                        second_word.endswith('я') or
                        second_word.endswith('ая') or
                        (len(words) >= 3 and words[2].isdigit())
                    )

                    if not is_not_city and not is_number and is_street_like:
                        result['city'] = first_word
                        logger.debug(f"Found city (first word): {first_word}")

            # 1. УЛИЦА - регулярные выражения
            street_patterns = [
                r'(?:улица|ул\.?|ул|пр\.|проспект|пер\.|переулок|бул\.|бульвар)\s+([^,\d]+?)(?=\s+д\.|,|\s*$|\s+\d)',
                r'(?:на|в)\s+(?:улице|ул\.?)\s+([^,]+?)(?=\s+д\.|,|\s*$|\s+\d)',
                r'([^,\s]+(?:ая|ое|ий|ые|ая))\s+(?:улица|ул\.?)',
                r'(?:пр\.?|проспект)\s+([А-Яа-я-]+)(?=\s+|$|,|\d)',
                r'(?:пер\.?|переулок)\s+([А-Яа-я-]+)(?=\s+|$|,|\d)',
                r'(?:бул\.?|бульвар)\s+([А-Яа-я-]+)(?=\s+|$|,|\d)',
            ]

            # Паттерн 1: "на + название улицы"
            on_match = re.match(
                r'^\s*(?:на|в)\s+([А-Яа-яЁё-]{2,}(?:\s+[А-Яа-яЁё-]+)*)\s*$',
                text_lower.strip()
            )
            if on_match and not result.get('street'):
                street_candidate = on_match.group(1).strip()

                problem_keywords = [
                    'теч', 'прорыв', 'сломал', 'засор', 'нет', 'горяч', 'холодн',
                    'батар', 'кран', 'труба', 'унитаз', 'смесит', 'раковин',
                    'дом', 'дома', 'доме'
                ]
                is_problem = any(kw in street_candidate.lower() for kw in problem_keywords)

                if not is_problem:
                    result['street'] = street_candidate.capitalize()
                    logger.debug(f"Found street (on pattern): {result['street']}")

            # Паттерн 2: название улицы + номер дома
            text_for_street = text_lower
            if result.get('city'):
                city_prefix = result['city'].lower() + r'\s*'
                text_for_street = re.sub(f'^{city_prefix}', '', text_lower).strip()

            full_match = re.match(
                r'^\s*([А-Яа-яЁё-]{2,}(?:\s+[А-Яа-яЁё-]+)*)\s+(\d{1,3}[а-яА-Я/]?)\s*(?:кв\.?\s*\d+)?\s*$',
                text_for_street.strip()
            )
            if full_match and not result.get('street'):
                street_candidate = full_match.group(1).strip()
                house_candidate = full_match.group(2)

                problem_keywords = [
                    'теч', 'прорыв', 'сломал', 'засор', 'нет', 'горяч', 'холодн',
                    'батар', 'кран', 'труба', 'унитаз', 'смесит', 'раковин',
                    'дом', 'дома', 'доме'
                ]
                is_problem = any(kw in street_candidate.lower() for kw in problem_keywords)

                if not is_problem:
                    result['street'] = street_candidate.capitalize()
                    result['house_number'] = house_candidate
                    logger.debug(f"Found full address: street={result['street']}, house={result['house_number']}")

            # Паттерн 3: Просто название улицы (если есть context_memory)
            if context_memory and context_memory.get('house_number') and not result.get('street'):
                street_only_match = re.match(
                    r'^\s*([А-Яа-яЁё-]{2,}(?:\s+[А-Яа-яЁё-]+)*)\s*$',
                    text_lower.strip()
                )
                if street_only_match:
                    street_candidate = street_only_match.group(1).strip()

                    problem_keywords = [
                        'теч', 'прорыв', 'сломал', 'засор', 'нет', 'горяч', 'холодн',
                        'батар', 'кран', 'труба', 'унитаз', 'смесит', 'раковин',
                        'дом', 'дома', 'доме'
                    ]
                    is_problem = any(kw in street_candidate.lower() for kw in problem_keywords)

                    if not is_problem:
                        result['street'] = street_candidate.capitalize()
                        logger.debug(f"Found street (only): {result['street']}")

            for pattern in street_patterns:
                match = re.search(pattern, text_lower, re.IGNORECASE)
                if match:
                    street = match.group(1).strip()
                    street = re.sub(r'\b(?:улица|ул|проспект)\b', '', street).strip()
                    if street:
                        result['street'] = street.capitalize()
                        logger.debug(f"Found street: {street}")
                        break

            # 2. ДОМ - регулярные выражения
            house_patterns = [
                r'(?:дом|д\.?|строение)\s+(\d+[а-яА-Я/]*)',
                r'(?:улица|ул\.?|проспект|пр\.?|пер\.?|переулок|бул\.?|бульвар)\s+[^,]+?\s+(\d+[а-яА-Я/]*)',
                r'(?:№\s*|номер\s+)(\d+[а-яА-Я/]*)',
                r'(\d+[а-яА-Я/]+)(?=\s*$|\s+кв|\s*[,;])',
                r'(?:д\.?|дом)\s+(\d+[а-яА-Я/]*)',
                r'(?:пр\.?|проспект)\s+([А-Яа-я-]+)\s+(\d+[а-яА-Я/]*)',
                r'\b(\d+[а-яА-Я/]+)\b(?=\s*$|\s+кв|\s*[,;])',
            ]

            for pattern in house_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    result['house_number'] = match.group(1)
                    logger.debug(f"Found house number: {result['house_number']}")
                    break

            # 3. КВАРТИРА - регулярное выражение
            apt_match = re.search(r'(?:кв\.?|квартира)\s+(\d+)', text, re.IGNORECASE)
            if apt_match:
                result['apartment_number'] = apt_match.group(1)
                logger.debug(f"Found apartment: {result['apartment_number']}")

            # 4. ПОДЪЕЗД - регулярное выражение
            entrance_match = re.search(r'(?:подъезд|подъ\.?|выход)\s+(\d+)', text, re.IGNORECASE)
            if entrance_match:
                result['entrance'] = entrance_match.group(1)
                logger.debug(f"Found entrance: {result['entrance']}")

        except Exception as e:
            logger.error(f"Error parsing address text '{text}': {e}")

        return result

    def _merge_with_memory(self, current: Dict, memory: Dict) -> Dict:
        """
        КЛЮЧЕВОЙ МЕТОД! Объединить компоненты адреса с памятью.

        Args:
            current: Компоненты из текущего сообщения
            memory: Компоненты из предыдущих сообщений

        Returns:
            Dict: Объединенные компоненты

        Пример:
        --------
        Message 1: "ул. Ленина"
        current = {street: 'Ленина', house: None}
        memory = {street: None, house: None}
        → result = {street: 'Ленина', house: None}

        Message 2: "дом 5"
        current = {street: None, house: '5'}
        memory = {street: 'Ленина', house: None}
        → result = {street: 'Ленина', house: '5'}  # ОБЪЕДИНЕНО!
        """
        try:
            result = {}

            # Приоритет: текущее сообщение ИЛИ память
            for key in ['city', 'street', 'house_number', 'apartment_number', 'entrance']:
                result[key] = current.get(key) or memory.get(key)

            # Отметить, восстановлено ли из памяти
            result['from_memory'] = any(
                not current.get(k) and memory.get(k)
                for k in ['city', 'street', 'house_number', 'apartment_number', 'entrance']
            )

            logger.info(f"Merged address components: {result}")
            return result

        except Exception as e:
            logger.error(f"Error merging address components: {e}")
            return current or memory

    def _normalize_components(self, components: Dict) -> Dict:
        """
        Нормализует компоненты адреса.

        Args:
            components: Сырые компоненты адреса

        Returns:
            Dict: Нормализованные компоненты
        """
        try:
            normalized = components.copy()

            if normalized.get('street'):
                street = normalized['street']
                street = street.strip()
                street = re.sub(r'["\']', '', street)
                street = re.sub(r'\s+', ' ', street)
                street = street.strip()
                normalized['street'] = street

            if normalized.get('house_number'):
                house = normalized['house_number']
                house = re.sub(r'^№\s*', '', house)
                house = house.strip()
                normalized['house_number'] = house

            if normalized.get('apartment_number'):
                apt = normalized['apartment_number'].strip()
                normalized['apartment_number'] = apt

            if normalized.get('entrance'):
                entrance = normalized['entrance'].strip()
                normalized['entrance'] = entrance

            return normalized

        except Exception as e:
            logger.error(f"Error normalizing address components: {e}")
            return components

    def validate_and_match_to_db(self, address_components: Dict) -> Dict:
        """
        Валидируем адрес и ищем в БД с помощью Django ORM.

        НОВАЯ РЕАЛИЗАЦИЯ (2026-03-13):
        - Использует Django ORM вместо прямых SQL
        - Работает с новой моделью (kladr.models)

        Args:
            address_components: Dict с компонентами адреса
                {street, house_number, apartment_number}

        Returns:
            Dict с результатом валидации:
                {found, building_id, unit_id, confidence, reason, ...}
        """
        street = address_components.get('street')
        house_number = address_components.get('house_number')
        apartment_number = address_components.get('apartment_number')

        if not street or not house_number:
            return {
                'found': False,
                'building_id': None,
                'unit_id': None,
                'confidence': 0.0,
                'reason': 'Отсутствует улица или номер дома'
            }

        try:
            # НОВАЯ МОДЕЛЬ: Ищем улицу через Django ORM
            street_qs = KladrAddressObject.objects.filter(
                type__level=5,  # Только улицы
                name__icontains=street
            ).annotate(
                building_count=Count('building')
            ).order_by('-building_count', 'name')[:3]

            if not street_qs.exists():
                return {
                    'found': False,
                    'building_id': None,
                    'unit_id': None,
                    'reason': f'Улица "{street}" не найдена',
                    'confidence': 0.0
                }

            # Берем первую найденную улицу
            street_obj = street_qs.first()
            street_name = street_obj.name

            # НОВАЯ МОДЕЛЬ: Ищем здание через Django ORM
            building_qs = Building.objects.filter(
                address_object=street_obj,
                house_number__iexact=house_number
            )

            if not building_qs.exists():
                return {
                    'found': False,
                    'building_id': None,
                    'unit_id': None,
                    'reason': f'Дом "{house_number}" на улице "{street}" не найден',
                    'confidence': 0.5
                }

            building_obj = building_qs.first()
            building_id = building_obj.id

            # НОВАЯ МОДЕЛЬ: Ищем квартиру через Django ORM
            unit_id = None
            if apartment_number:
                from portal.models import Unit
                try:
                    unit_obj = Unit.objects.get(
                        building_id=building_id,
                        unit_number=apartment_number
                    )
                    unit_id = unit_obj.unit_id
                except Unit.DoesNotExist:
                    unit_id = None

            confidence = 0.9 if unit_id else 0.7

            return {
                'found': True,
                'building_id': building_id,
                'unit_id': unit_id,
                'street_name': street_name,
                'address_full': f"ул. {street_name}, д. {house_number}" +
                              (f", кв. {apartment_number}" if apartment_number else ""),
                'confidence': confidence
            }

        except Exception as e:
            logger.error(f"Ошибка в validate_and_match_to_db: {e}")
            return {
                'found': False,
                'building_id': None,
                'unit_id': None,
                'reason': f'Ошибка базы данных: {str(e)}',
                'confidence': 0.0
            }

    def ask_clarification_if_needed(self, address_components: Dict, validation_result: Dict) -> Dict:
        """
        Если confidence < 0.8, просим уточнить адрес

        Args:
            address_components: Компоненты адреса
            validation_result: Результат валидации

        Returns:
            Dict: {need_clarification, message, missing_parts}
        """
        confidence = validation_result.get('confidence', 0.0)

        if confidence >= 0.8:
            return {
                'need_clarification': False,
                'message': None
            }

        missing_parts = []
        if not address_components.get('street'):
            missing_parts.append('название улицы')
        if not address_components.get('house_number'):
            missing_parts.append('номер дома')

        if missing_parts:
            message = f"Пожалуйста, укажите: {', '.join(missing_parts)}"
        elif validation_result.get('reason'):
            message = f"Адрес не найден: {validation_result['reason']}. Пожалуйста, проверьте правильность написания."
        else:
            message = "Пожалуйста, уточните адрес (улица и номер дома)"

        return {
            'need_clarification': True,
            'message': message,
            'missing_parts': missing_parts
        }
